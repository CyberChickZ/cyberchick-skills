import json
import os
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CLAUDE_DIR = Path(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"))
DATA = Path(os.path.expanduser(os.environ.get("AI_JOB_SEARCH_DATA") or CLAUDE_DIR / "cyberchick-skills" / "ai-job-search"))

DEFAULTS = {
    "jobdir": "~/git/job-search",
    "resume_repo": "~/git/resume",
    "resume_out": "~/Downloads/Resume{suffix}.pdf",
    "resume_variants": {"default": "resume:"},
}


def config():
    cfg = dict(DEFAULTS)
    p = DATA / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text()))
    return cfg


def path(key):
    return Path(os.path.expanduser(config()[key]))


def data_file(name):
    """本机数据优先，没有就用仓库自带的初始版。"""
    p = DATA / name
    return p if p.exists() else SKILL / name
