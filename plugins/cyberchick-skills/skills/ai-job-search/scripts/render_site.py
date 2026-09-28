#!/usr/bin/env python3
"""applications.csv + 最新 queue_*.json → <jobdir>/site/index.html（再用 Artifact 工具发布）"""
import csv, datetime as dt, json
from pathlib import Path
from _config import SKILL, path
J = path("jobdir")
apps = list(csv.DictReader((J / "applications.csv").open()))
qs = sorted(J.glob("queue_*.json"))
queue = json.loads(qs[-1].read_text()) if qs else []
qdate = qs[-1].stem.split("_")[1] if qs else ""
data = dict(apps=apps, queue=queue, queue_date=f"{qdate[:4]}-{qdate[4:6]}-{qdate[6:]}" if qdate else "",
            generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
html = (SKILL / "site_template.html").read_text().replace(
    '/*__DATA__*/{"apps":[],"queue":[],"generated":""}', json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
out = J / "site/index.html"; out.parent.mkdir(exist_ok=True); out.write_text(html)
print(f"{out}  ({len(apps)} apps, {len(queue)} queued, {len(html)//1024} KB)")
