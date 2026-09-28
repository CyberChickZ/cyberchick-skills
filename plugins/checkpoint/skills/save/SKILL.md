---
name: save
description: "Extract key findings from conversation and persist to project memory. Deduplicates against existing memories, writes with proper frontmatter, updates MEMORY.md index. Use before context compaction or when important decisions/findings should be preserved. Triggers on: '/checkpoint:save', 'save memory', 'persist findings', 'checkpoint save'."
license: MIT
---

# Checkpoint: Save

Scan the current conversation and persist key findings to project memory.

## Instructions

1. **Extract**: Scan the full conversation. Identify:
   - Key research findings, conclusions, or decisions
   - Important file paths, commands, or configurations discovered
   - Hypotheses confirmed or ruled out
   - Architectural decisions or trade-offs discussed
   - Non-obvious insights ("aha moments")

2. **Deduplicate**: Read `~/.claude/projects/{current-project}/memory/MEMORY.md`. Skip anything already recorded.

3. **Write**: For each NEW finding, create or update a memory file in the memory directory:
   - Use type `project` for findings about ongoing work
   - Use type `reference` for external resources/links discovered
   - Use type `feedback` for workflow lessons learned
   - Use type `user` for new info about user preferences/context
   - Standard frontmatter format:
     ```yaml
     ---
     name: descriptive name
     description: one-line description for relevance matching
     type: project|reference|feedback|user
     ---
     ```
   - For project/feedback types, include **Why:** and **How to apply:** lines

4. **Update Index**: Append new entries to MEMORY.md (one-line pointers, under 150 chars each):
   `- [Title](filename.md) — one-line hook`

5. **Report**: Brief summary of what was saved (bullet list).

## Rules

- Do NOT save ephemeral task details or temporary state
- Do NOT save things derivable from code or git history
- Do NOT duplicate what's already in CLAUDE.md files
- DO save non-obvious insights that would be lost after compaction
- Keep each memory file focused on one topic
- Convert relative dates to absolute dates
