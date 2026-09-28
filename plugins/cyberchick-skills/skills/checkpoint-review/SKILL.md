---
name: checkpoint-review
description: "Extract memory candidates from conversation and present for user approval before writing. Shows a numbered table of proposed memories with type, filename, summary, and action. Nothing is written until user confirms. Triggers on: '/checkpoint-review', 'review memory', 'check memory', 'checkpoint review'."
license: MIT
---

# Checkpoint: Review

Scan the conversation and show candidates for memory persistence. Do NOT write anything until user confirms.

## Instructions

1. **Extract**: Same as `/checkpoint-save` — scan for findings, decisions, insights.

2. **Deduplicate**: Read `~/.claude/projects/{current-project}/memory/MEMORY.md`. Filter out already recorded items.

3. **Present**: Output a numbered table of candidates:

| # | Type | Filename | Content Summary | Action |
|---|------|----------|----------------|--------|
| 1 | feedback | feedback_xxx.md | ... | new |
| 2 | project | project_xxx.md | ... | update existing |
| ... | | | | |

4. **Wait**: Ask user:
   > "确认全部写入？或告诉我编号来调整。"

   User responses:
   - "全部写入" / "ok" / "yes" → write all
   - "删 2, 改 3 为 ..." → adjust then write
   - "算了" / "cancel" → abort, write nothing

5. **Execute**: Only after explicit confirmation, write files and update MEMORY.md index.

## Rules

- NEVER write memory files before user confirms
- Show enough detail in summary for user to judge relevance
- Same exclusion rules as `/checkpoint-save`
