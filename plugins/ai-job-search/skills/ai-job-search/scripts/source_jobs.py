#!/usr/bin/env python3
"""Pull fresh postings straight from Greenhouse / Ashby / Lever public APIs,
pre-screen the JD text, dedup against the tracker, and write today's queue.

  python3 source_jobs.py                 # last 14 days, all tracks
  python3 source_jobs.py --days 3 --track MLE,Robotics
  python3 source_jobs.py --probe ashby:somecompany
"""
import argparse, concurrent.futures as cf, csv, datetime as dt, html, json, re, sys, time, urllib.request
from pathlib import Path

from _config import config, path, data_file
JOBDIR = path("jobdir")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) job-sourcer"}

URL = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
}

TRACKS = [
    ("FDE", r"forward[- ]deployed|deployed engineer|solutions? engineer|applied ai (engineer|architect)|customer engineer|field engineer"),
    ("Robotics", r"robot|embodied|\bvla\b|manipulation|locomotion|humanoid|simulation|autonomy|autonomous|perception|motion planning"),
    ("MLE", r"machine learning|\bml\b|\bai\b|artificial intelligence|applied scientist|\bllm|genai|generative|research (engineer|scientist)|computer vision|deep learning|inference|training|post-training|pretraining|model"),
    ("SDE", r"software (development )?engineer|\bsde\b|\bswe\b|developer|full[- ]?stack|back[- ]?end|front[- ]?end|platform engineer|infrastructure engineer"),
]
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head of|vp|vice president|distinguished|fellow|iii|iv|v)\b", re.I)
JUNIOR_BASE = r"new grad|university grad|graduate|early career|entry|junior|intern|co-?op|\bi\b|residency|apprentice"
NON_ENG = re.compile(r"account (executive|manager)|\bsales\b|strategist|creative|technician|recruit|talent|marketing|designer|counsel|legal|operations|partnerships?|success|support|business development|\bgtm\b|evangelist|advocate|writer\b|analyst|program manager|product manager|assembly", re.I)
PHD_TITLE = re.compile(r"ph\.?d", re.I)
BAD_TYPE = re.compile(r"contract|temporary|temp\b|part[- ]?time|freelance|seasonal", re.I)

FLAGS = [
    ("NO_SPONSOR", r"(not|unable to|will not|won'?t|cannot|can'?t|do(es)? not) (be able to )?(provide |offer )?(visa )?sponsor|no (visa )?sponsorship|sponsorship (is )?not (available|provided|offered)|without (the need for )?(current or future |any )?(visa |employer )?sponsorship|not eligible for (visa )?sponsorship"),
    ("CITIZEN", r"u\.?s\.? citizen(ship)? (is )?(required|only)|must be a u\.?s\.? citizen|u\.?s\.? person|\bitar\b|export[- ]control|security clearance|clearance (is )?required|top secret|ts/sci|secret clearance"),
    ("PHD", r"(currently )?(pursuing|enrolled in) a ph\.?d|ph\.?d\.? (is |degree )?(required|in progress)|must (have|hold) a ph\.?d|ph\.?d\.? (students?|candidates?) only"),
]
GRAD_LATE_RX = r"graduat\w*[^.]{{0,40}}\b(december|dec\.?|fall|winter|spring|may|june|summer)?\s*({years})\b[^.]{{0,20}}(or later|or after|through|and|or)|returning to (school|your studies)|must be (currently )?enrolled[^.]{{0,60}}(after|following) the internship|at least one (more )?(semester|quarter|term)[^.]{{0,30}}(remaining|after)"

# 个人偏好全部来自本机 config.json 的 filters，这里的默认值是「不过滤」
F = {"skip": {}, "hard_flags": [], "soft_flags": [], "grad_late_years": [], "junior_years": [],
     "location_allow": None, "location_deny": None, "amazon_country": "USA",
     "amazon_queries": ["software development engineer new grad", "sde intern", "applied scientist", "machine learning engineer"], "track_order": [t for t, _ in TRACKS], "notes": {}}
F.update(config().get("filters", {}))
if F["grad_late_years"]:
    FLAGS.append(("GRAD_LATE", GRAD_LATE_RX.format(years="|".join(map(str, F["grad_late_years"])))))
JUNIOR = re.compile(JUNIOR_BASE + "".join(f"|\\b{y}\\b" for y in F["junior_years"]), re.I)
LOC_ALLOW = re.compile(F["location_allow"], re.I) if F["location_allow"] else None
LOC_DENY = re.compile(F["location_deny"], re.I) if F["location_deny"] else None

SPONSOR_OK = re.compile(r"(visa|h-?1b) sponsorship (is )?(available|provided|offered)|we (will |do )?sponsor|able to sponsor", re.I)
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d+\s*)?years?(?:'| of)?\s+(?:of\s+)?(?:relevant |professional |industry |hands-on |work )*experience", re.I)


def fetch(ats, slug, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(URL[ats].format(slug), headers=UA)
            d = json.load(urllib.request.urlopen(req, timeout=40))
            return d["jobs"] if isinstance(d, dict) else d
        except Exception as e:
            err = e
            time.sleep(1.5 * (i + 1))
    print(f"  ! {ats}:{slug} failed: {err}", file=sys.stderr)
    return []


def text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(html.unescape(h or "")))).strip()




def fetch_amazon():
    import urllib.parse
    out = {}
    for q in F["amazon_queries"]:
        for off in (0, 100):
            u = "https://www.amazon.jobs/en/search.json?" + urllib.parse.urlencode(
                {"base_query": q, "country": F["amazon_country"], "result_limit": 100, "offset": off, "sort": "recent"})
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40))
            except Exception as e:
                print(f"  ! amazon {q}: {e}", file=sys.stderr); continue
            for j in d.get("jobs", []):
                out[j["id_icims"]] = j
    return list(out.values())


def norm(ats, slug, j):
    if ats == "amazon":
        try:
            posted = dt.datetime.strptime(j.get("posted_date", ""), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            posted = ""
        bq = text(j.get("basic_qualifications"))
        return dict(company="Amazon", title=j["title"], location=j.get("normalized_location") or j.get("location") or "",
                    url="https://www.amazon.jobs" + j.get("job_path", f"/en/jobs/{j['id_icims']}"), posted=posted,
                    etype=j.get("job_schedule_type") or "", jd=bq + " " + text(j.get("preferred_qualifications")), bq=bq)
    if ats == "greenhouse":
        return dict(company=j.get("company_name") or slug, title=j["title"], location=(j.get("location") or {}).get("name", ""),
                    url=j["absolute_url"], posted=(j.get("first_published") or j.get("updated_at") or "")[:10],
                    etype="", jd=text(j.get("content")))
    if ats == "ashby":
        locs = [j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or []]
        return dict(company=slug, title=j["title"], location=" / ".join(filter(None, locs)) + (" (Remote)" if j.get("isRemote") else ""),
                    url=j.get("jobUrl") or j.get("applyUrl"), posted=(j.get("publishedAt") or "")[:10],
                    etype=j.get("employmentType") or "", jd=j.get("descriptionPlain") or text(j.get("descriptionHtml")))
    c = j.get("categories") or {}
    jd = " ".join([j.get("descriptionPlain") or ""] + [text(l.get("content")) + " " + l.get("text", "") for l in j.get("lists") or []] + [j.get("additionalPlain") or ""])
    return dict(company=slug, title=j["text"], location=c.get("location") or "", url=j["hostedUrl"],
                posted=dt.datetime.fromtimestamp(j.get("createdAt", 0) / 1000).strftime("%Y-%m-%d"),
                etype=c.get("commitment") or "", jd=jd)


def track_of(title):
    for name, rx in TRACKS:
        if re.search(rx, title, re.I):
            return name
    return None


def screen(p):
    jd = p["jd"].lower()
    if p.get("bq") is not None:
        bq = p["bq"].lower().replace("18 years of age", "")
        flags = [n for n, rx in FLAGS if n != "PHD" and re.search(rx, jd)]
        if re.search(r"ph\.?d", bq) and not re.search(r"master'?s?( degree)? (in|or above|,|$)|master'?s degree\b(?! and)", bq):
            flags.append("PHD")
        yrs = [int(m) for m in re.findall(r"(\d{1,2})\+ years", bq)]
        if yrs and max(yrs) >= 3:  # basic quals 每条都是硬性要求，取最大
            flags.append(f"YOE{max(yrs)}+")
        return flags
    flags = [n for n, rx in FLAGS if re.search(rx, jd)]
    yrs = [int(m.group(1)) for m in YEARS.finditer(jd) if int(m.group(1)) < 20]
    if yrs and min(yrs) >= 3:
        flags.append(f"YOE{min(yrs)}+")
    if SPONSOR_OK.search(jd):
        flags.append("sponsor_ok")
    return flags


def load_seen():
    seen_urls, seen_keys = set(), set()
    f = JOBDIR / "applications.csv"
    if f.exists():
        for r in csv.DictReader(f.open()):
            if r.get("link"):
                seen_urls.add(re.sub(r"^https?://(www\.)?", "", r["link"]).rstrip("/"))
            seen_keys.add((r.get("company", "").lower()[:12], re.sub(r"\W+", "", r.get("role", "").lower())[:40]))
    md = JOBDIR / "application_tracker.md"
    blob = (md.read_text() if md.exists() else "") + (f.read_text() if f.exists() else "")  # job id 也查 CSV
    return seen_urls, seen_keys, blob


def is_dup(p, seen):
    urls, keys, blob = seen
    u = re.sub(r"^https?://(www\.)?", "", p["url"] or "").rstrip("/")
    if u in urls:
        return True
    jid = re.findall(r"(\d{6,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", p["url"] or "")
    if jid and jid[-1] in blob:
        return True
    return (p["company"].lower()[:12], re.sub(r"\W+", "", p["title"].lower())[:40]) in keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--track", default="SDE,FDE,Robotics,MLE")
    ap.add_argument("--all-levels", action="store_true", help="keep senior titles too")
    ap.add_argument("--probe")
    a = ap.parse_args()

    if a.probe:
        ats, slug = a.probe.split(":")
        js = fetch(ats, slug)
        print(f"{a.probe}: {len(js)} jobs")
        return

    wl = json.loads(data_file("watchlist.json").read_text())
    skip = {**wl.get("skip", {}), **F["skip"]}
    want = set(a.track.split(","))
    cutoff = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()

    raw = []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(fetch, "greenhouse", s): ("greenhouse", s) for s in wl["greenhouse"]}
        futs.update({ex.submit(fetch, "lever", s): ("lever", s) for s in wl["lever"]})
        for f in cf.as_completed(futs):
            ats, s = futs[f]
            raw += [(ats, s, j) for j in f.result()]
    raw += [("amazon", "amazon", j) for j in fetch_amazon()]
    for s in wl["ashby"]:  # Ashby rate-limits parallel calls
        raw += [("ashby", s, j) for j in fetch("ashby", s)]
        time.sleep(0.4)

    seen = load_seen()
    out, stats = [], dict(fetched=len(raw), old=0, track=0, senior=0, loc=0, etype=0, dup=0)
    for ats, slug, j in raw:
        p = norm(ats, slug, j)
        if p["posted"] and p["posted"] < cutoff:
            stats["old"] += 1; continue
        t = track_of(p["title"])
        if t not in want:
            stats["track"] += 1; continue
        if not a.all_levels and SENIOR.search(p["title"]):
            stats["senior"] += 1; continue
        if NON_ENG.search(p["title"]):
            stats["track"] += 1; continue
        if PHD_TITLE.search(p["title"]):
            stats["senior"] += 1; continue
        if LOC_ALLOW and p["location"] and not LOC_ALLOW.search(p["location"]) and ((LOC_DENY and LOC_DENY.search(p["location"])) or not re.search(r"remote|anywhere", p["location"], re.I)):
            stats["loc"] += 1; continue
        if BAD_TYPE.search(p["etype"]) or BAD_TYPE.search(p["title"]):
            stats["etype"] += 1; continue
        if is_dup(p, seen):
            stats["dup"] += 1; continue
        p.update(ats=ats, slug=slug, track=t, flags=screen(p), junior=bool(JUNIOR.search(p["title"])))
        p.pop("bq", None)
        if slug in skip:
            p["flags"].insert(0, "QUOTA")
        out.append(p)

    hard = set(F["hard_flags"]) | {"QUOTA"}
    soft = set(F["soft_flags"]) | {"GRAD_LATE"}
    ready = [p for p in out if not hard & set(p["flags"]) and not any(f.startswith("YOE") or f in soft for f in p["flags"])]
    maybe = [p for p in out if p not in ready and not hard & set(p["flags"])]
    dead = [p for p in out if hard & set(p["flags"])]
    order = F["track_order"] + [t for t, _ in TRACKS if t not in F["track_order"]]
    key = lambda p: (not p["junior"], order.index(p["track"]), p["posted"] or "")
    for L in (ready, maybe, dead):
        L.sort(key=key)

    today = dt.date.today().strftime("%Y%m%d")
    md = JOBDIR / f"queue_{today}.md"
    def row(p):
        fl = " ".join(p["flags"]) or "—"
        return f"| {p['track']} | {p['company']} | {p['title'].replace('|','/')} | {p['location'][:40].replace('|','/')} | {p['posted']} | {'NG/Intern' if p['junior'] else ''} | {fl} | {p['url']} |"
    hdr = "| track | company | title | location | posted | level | flags | link |\n|---|---|---|---|---|---|---|---|"
    lines = [f"# 待投队列 {dt.date.today()}（最近 {a.days} 天，{a.track}）", "",
             f"抓取 {stats['fetched']} 条 → 过旧 {stats['old']} / 方向不符 {stats['track']} / 资深 {stats['senior']} / 地点 {stats['loc']} / 合同工 {stats['etype']} / 已投 {stats['dup']} → **剩 {len(out)}**", "",
             f"## ✅ 可直接投（{len(ready)}）— JD 没扫到硬排除项", "", hdr] + [row(p) for p in ready] + [
             "", f"## ⚠️ 要看一眼（{len(maybe)}）— " + F["notes"].get("maybe", "YOE3+：读 JD 判断是否硬门槛；其余 flag 按 local.md 的偏好判断"), "", hdr] + [row(p) for p in maybe] + [
             "", f"## ⛔ 已排除（{len(dead)}）— " + F["notes"].get("excluded", " / ".join(sorted(hard))), "", hdr] + [row(p) for p in dead]
    md.write_text("\n".join(lines) + "\n")
    (JOBDIR / f"queue_{today}.json").write_text(json.dumps([{k: v for k, v in p.items() if k != "jd"} for p in ready + maybe], indent=1))
    print(lines[2])
    print(f"ready={len(ready)} maybe={len(maybe)} excluded={len(dead)} -> {md}")


if __name__ == "__main__":
    main()
