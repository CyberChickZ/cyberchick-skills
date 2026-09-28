#!/usr/bin/env python3
"""初始化本机数据目录（不会覆盖已有文件）。用法: init_data.py [--from <旧的 skill 目录>]"""
import shutil
import sys
from pathlib import Path

from _config import DATA, SKILL

SEEDS = {"profile.md": "templates/profile.example.md", "quotas.md": "templates/quotas.example.md",
         "local.md": "templates/local.example.md", "config.json": "templates/config.example.json",
         "ats_playbook.md": "ats_playbook.md", "watchlist.json": "watchlist.json"}

src = Path(sys.argv[sys.argv.index("--from") + 1]).expanduser() if "--from" in sys.argv else None
DATA.mkdir(parents=True, exist_ok=True)
for name, seed in SEEDS.items():
    dst = DATA / name
    if dst.exists():
        print(f"· {dst} 已存在，跳过")
        continue
    origin = src / name if src and (src / name).exists() else SKILL / seed
    shutil.copy2(origin, dst)
    print(f"✓ {dst}  ←  {origin}")
print(f"\n数据目录: {DATA}\n先填 profile.md / local.md / config.json，再用 /ai-job-search。")
