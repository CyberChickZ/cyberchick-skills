---
name: read
description: "RAG-style memory recall — analyze current conversation topics and load only relevant memories from project memory. Scores each memory by relevance, reads full content of matches, skips unrelated ones. Triggers on: '/checkpoint:read', 'recall memory', 'load context', 'checkpoint read', 'what do I have saved'."
license: MIT
---

# Checkpoint: Read

RAG-style memory recall — load only memories relevant to the current conversation topic.

## Instructions

1. **Identify topics**: Analyze the current conversation's main themes (2-5 keywords).

2. **Scan index**: Read `~/.claude/projects/{current-project}/memory/MEMORY.md`. Score each entry's relevance to current topics: high / medium / low / none.

3. **Load relevant**: Read the FULL content of high and medium relevance memory files only. Skip low/none.

4. **Report**:
   ```
   Loaded N memories relevant to [topics]:
   - memory_name.md — one-line summary
   - ...

   Skipped M unrelated memories.
   ```

5. The loaded content is now in context. Use it to inform subsequent responses without user needing to point to specific files.

If NO memories are relevant, say so and suggest `/checkpoint:save` if there are save-worthy findings in the current conversation.

## Rules

- Do NOT load all memories — that defeats the purpose
- Score relevance based on semantic match, not just keyword overlap
- If unsure about relevance, lean toward loading (false negative worse than false positive)
- Keep the report concise
