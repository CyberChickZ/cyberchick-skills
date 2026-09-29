#!/usr/bin/env python3
"""Keep ats_playbook.md and local.md structured: fixed sections, capped size, no dated "new/added" sections,
no duplicates. Usage: lint_data.py [--seed]   (--seed checks the copies shipped in the plugin instead of DATA)
Exit code 1 with a list of problems if anything is off; fix by merging/condensing, never by adding sections."""
import re
import sys

from _config import DATA, SKILL

PLAYBOOK_H2 = ["1. 通用流程", "2. 表单技巧", "3. 账号、登录、验证码", "4. 各 ATS 系统", "5. 公司特例"]
PLAYBOOK_ATS = ["Greenhouse", "Ashby", "Lever", "Workday", "iCIMS", "SmartRecruiters", "其他"]
LOCAL_H2 = ["授权", "看板", "数据", "方向优先级", "简历怎么选", "其他偏好"]
BAD_HEADING = re.compile(r"新增|补充|续|更新|update|added|new\b|\d{1,2}[-/月]\d{1,2}|20\d\d", re.I)
LIMITS = {"playbook_lines": 220, "local_lines": 70, "bullets_per_section": 12, "company_bullets": 30, "bullet_chars": 450}


def sections(lines):
    """Yield (h2, h3, [bullet lines], [stray prose lines]) per leaf section."""
    h2 = h3 = None
    bullets, stray, in_code = [], [], False
    out = []
    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.startswith("## ") or line.startswith("### "):
            out.append((h2, h3, bullets, stray))
            bullets, stray = [], []
            if line.startswith("## "):
                h2, h3 = line[3:].strip(), None
            else:
                h3 = line[4:].strip()
            continue
        if line.startswith("- "):
            bullets.append(line)
        elif line.strip() and not line.startswith((" ", "\t", ">", "#", "|")):
            stray.append(line)
    out.append((h2, h3, bullets, stray))
    return [s for s in out if s[0] is not None]


def norm(bullet):
    b = re.sub(r"[*`\s]", "", bullet[2:]).lower()
    lead = re.match(r"\*\*(.+?)\*\*", bullet[2:])
    return (re.sub(r"\s", "", lead.group(1)).lower() if lead else b[:30])


def lint_playbook(path):
    errs = []
    lines = open(path, encoding="utf-8").read().splitlines()
    if len(lines) > LIMITS["playbook_lines"]:
        errs.append(f"整份 {len(lines)} 行，超过 {LIMITS['playbook_lines']} 行：合并同类条目、删掉过时的")
    heads = [l for l in lines if l.startswith("#")]
    h2s = [l[3:].strip() for l in heads if l.startswith("## ")]
    if h2s != PLAYBOOK_H2:
        errs.append(f"二级标题必须依次是 {PLAYBOOK_H2}，现在是 {h2s}")
    for h in heads:
        if h.startswith("####"):
            errs.append(f"不允许四级及以下标题: {h}")
        if BAD_HEADING.search(h):
            errs.append(f"标题里不能有日期或「新增/补充/续」: {h}")
    seen = {}
    for h2, h3, bullets, stray in sections(lines):
        where = f"{h2} / {h3}" if h3 else h2
        if h3:
            if h2 == PLAYBOOK_H2[1] and not re.match(r"^2\.\d+ ", h3):
                errs.append(f"第 2 章的小节要写成「2.x 名称」: {h3}")
            elif h2 == PLAYBOOK_H2[3] and h3 not in PLAYBOOK_ATS:
                errs.append(f"第 4 章只允许这些小节 {PLAYBOOK_ATS}: {h3}")
            elif h2 not in (PLAYBOOK_H2[1], PLAYBOOK_H2[3]):
                errs.append(f"「{h2}」下面不允许小节: {h3}")
        cap = LIMITS["company_bullets"] if h2 == PLAYBOOK_H2[4] else LIMITS["bullets_per_section"]
        if len(bullets) > cap:
            errs.append(f"「{where}」有 {len(bullets)} 条，超过 {cap} 条：合并同类的")
        for s in stray:
            errs.append(f"「{where}」有条目之外的段落（要写成「- 」开头的条目）: {s[:60]}")
        for b in bullets:
            if len(b) > LIMITS["bullet_chars"]:
                errs.append(f"「{where}」有一条 {len(b)} 字，超过 {LIMITS['bullet_chars']} 字: {b[:40]}…")
            k = norm(b)
            if k in seen:
                errs.append(f"重复条目:「{b[:40]}…」和「{seen[k]}」下的一条相同")
            seen[k] = where
    return errs


def lint_local(path):
    errs = []
    lines = open(path, encoding="utf-8").read().splitlines()
    if len(lines) > LIMITS["local_lines"]:
        errs.append(f"整份 {len(lines)} 行，超过 {LIMITS['local_lines']} 行")
    h2s = [l[3:].strip() for l in lines if l.startswith("## ")]
    if h2s != LOCAL_H2:
        errs.append(f"二级标题必须依次是 {LOCAL_H2}，现在是 {h2s}")
    for l in lines:
        if l.startswith("###"):
            errs.append(f"local.md 不允许小节: {l}")
        if l.startswith("#") and BAD_HEADING.search(l):
            errs.append(f"标题里不能有日期或「新增/补充/续」: {l}")
    return errs


def main():
    seed = "--seed" in sys.argv
    base = SKILL if seed else DATA
    targets = [(base / "ats_playbook.md", lint_playbook),
               ((SKILL / "templates" / "local.example.md") if seed else (DATA / "local.md"), lint_local)]
    bad = 0
    for path, fn in targets:
        if not path.exists():
            print(f"· 跳过（不存在）: {path}")
            continue
        errs = fn(path)
        if errs:
            bad += len(errs)
            print(f"✗ {path}")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"✓ {path}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
