---
name: reload
description: "Manually trigger full memory reload — same as what happens automatically after compact. Reads ALL project memory files into context. Use when you want to force-load all saved memories without waiting for compaction. Triggers on: '/checkpoint:reload', 'reload memory', 'load all memories', 'full memory load'."
license: MIT
---

# Checkpoint: Reload

Force a full memory reload into the current conversation context.

This is the same operation that runs automatically after compaction, but triggered manually.

## Instructions

1. Read `~/.claude/projects/{current-project}/memory/MEMORY.md` index.

2. Read the FULL content of EVERY memory file listed in the index.

3. Report what was loaded:
   ```
   Loaded N memories:
   - filename.md — description
   - ...
   ```

4. All memory content is now in context for this conversation.

## When to use

- Starting a new session that continues previous work
- When you realize saved memories would help but none were auto-loaded
- After manually editing memory files and wanting to refresh context
