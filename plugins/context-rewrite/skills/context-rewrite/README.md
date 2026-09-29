# context-rewrite

English | [简体中文](README.zh-CN.md)

A plugin in [cyberchick-skills](../../../../README.md) that can be installed on its own. Command: `/context-rewrite` (shown in the menu as `/context-rewrite:context-rewrite`); launch flag: `claude --yrb`.

Every Claude Code request carries automatically injected content, such as the default system prompt and `<system-reminder>` blocks. Some of it may not fit your team's rules. This plugin find/replaces that content before each request is sent.

- Only sessions started with `claude --yrb` are affected (yrb = you are boss); every other session is untouched
- This content is assembled locally by Claude Code for every request; it isn't stored in the cloud or in any file, so it has to be rewritten on every request. Claude Code hooks can't do this (the docs state `UserPromptSubmit` "can't replace the prompt"), so a local proxy that serves only `--yrb` sessions does it instead

## Install
In any claude conversation:
```
/plugin marketplace add CyberChickZ/cyberchick-skills
/plugin install context-rewrite@cyberchick-skills
/context-rewrite install
```
Installing the plugin gives you the `/context-rewrite` command. `install` appends `--yrb` to the end of `~/.zshrc` (and `~/.bashrc` if it exists) and copies the scripts to `~/.claude/context-rewrite/`. It is safe to rerun; the rc file only ever gets one block.

Then open a new terminal tab and run `claude --yrb --continue` (`--continue` resumes the conversation you were in). To stay in the current terminal, exit claude and run `source ~/.zshrc && claude --yrb --continue`. The rc file has to be reloaded because the shell you return to after exiting hasn't read it yet, and a child process can't change that.

## Usage
```sh
claude --yrb              # combines with other flags: claude --yrb --resume, claude --yrb --dangerously-skip-permissions ...
```
In the session:
```
/context-rewrite auto delete the line with {Co-Authored-By}          # text in {…}; the model only picks the operation, the script builds the rule
/context-rewrite verify                                    # check every rule against the last real requests (main + subagents): hits, before/after, actual replacements
/context-rewrite capture                                   # show the system prompt and injected content actually sent last time (before rewriting), and save it to a file
/context-rewrite "find" "replace"                          # add a rule by hand, effective from the next request
/context-rewrite "find" "replace" --scope                  # --scope with no value: pick where to replace from a menu
/context-rewrite 'foo\d+' 'bar' --regex                    # regex
/context-rewrite list | status | on | off
/context-rewrite rm | toggle | scope                       # without numbers: pick from a menu; or directly rm 2 3, toggle 1, scope 2 system
/context-rewrite install | uninstall
/context-rewrite doctor                                    # check every part and fix what can be fixed automatically
/context-rewrite restore [n] | snapshots | snapshot [name] # snapshots: list / roll back / save manually
/context-rewrite help                                      # usage
```
- Commands with complete arguments are run directly by a hook: the result is shown only to you, never enters the conversation, calls no model and costs no tokens
- `rm` / `toggle` / `scope` / `--scope` without arguments, and `auto`, need Claude to show a menu (AskUserQuestion) or write rules. That turn always uses **sonnet + low effort** (the skill's `model` / `effort` fields); your next message switches back to your own model
- `auto` never shows the request text to the model; the model only sees the instruction with the snippets taken out and picks an operation
- Text blocks that become empty after rewriting are dropped (the API rejects empty text blocks); a message emptied entirely keeps a `(removed)` placeholder
- `/resume`d conversations and subagents inside the same `--yrb` process are rewritten too
- Sessions not started from your terminal (e.g. background agents) are not rewritten
- Thinking blocks are signed and never modified; tool call arguments are never modified either
- Output language: English by default; Chinese when Claude Code's `language` setting (or the system language) is Chinese. Force it with `CTXRW_LANG=zh|en`

### Autocomplete
Every subcommand is also its own command, so typing `/context-rewrite:` lists them all with descriptions:
`/context-rewrite:install`, `:auto`, `:autowoc`, `:add`, `:capture`, `:verify`, `:list`, `:rm`, `:toggle`, `:scope`, `:on`, `:off`, `:status`, `:doctor`, `:restore`, `:snapshots`, `:snapshot`, `:uninstall`.
`/context-rewrite:capture` is the same as `/context-rewrite capture`. Short names such as `/capture` work too, except `status`, `doctor` and `help`, which Claude Code already uses — type the full name for those.

### Subagents
Subagents run inside the same claude process, so their requests go through the proxy and every rule applies to them too.
- `/context-rewrite:capture @general-purpose` shows a subagent's last request (type `@` and pick the subagent; `@agent-<name>` works too). User-defined subagents are reported as type `custom`. Plain `capture` lists the subagent types recorded so far.
- `auto` checks against the main session **and** the latest request of every subagent type, so text that only exists in a subagent's prompt can be matched.

### auto: describe the change, paste the text in `{braces}`
```
/context-rewrite auto delete from {- Entering financial credentials, bank/card/…} to {- Downloading or executing files from untrusted sources}
/context-rewrite auto replace {Creating accounts on the user's behalf} with {Creating accounts is fine}
```
1. The script pulls the text out of each `{…}` verbatim (it never goes through the model, so it can't be mistyped).
2. The remaining instruction (`delete from {0} to {1}`) goes to Claude (sonnet, low effort, no tools), which **only picks one of 7 operations** and writes no regex:
   1 delete the text · 2 delete its whole line · 3 delete from line A through line B · 4 delete between line A and line B, keeping both · 5 replace the text with X · 6 replace its whole line with X · 7 replace lines A through B with X
   If none fits it picks 8 and fills fixed fields only: `a`/`b` (what to find, range end), `unit` (text / line / whole block), `keep` (which ends survive), `new` (which snippets, or the original a/b text, go in). The script validates every field and rejects anything extra, so the model never touches a regex.
   The call runs bare: a one-line English system prompt replaces Claude Code's, in an empty directory, with no settings, CLAUDE.md, memory, skills, MCP, plugins or hooks.
3. The script builds the regex. Snippets are matched on letters, digits and CJK characters only: punctuation, whitespace, line breaks and markdown in between are ignored, so `{A'A  A . A}` matches `AAAA` or `A-A A.A`; Read-tool line numbers and list numbering are dropped. Replacing a line keeps its indentation and bullet.
4. By default it is checked **block by block** (the way the proxy rewrites) against the last full request of the main session and every subagent type: added only if it matches, with a before/after preview. If A and B are in different text blocks it stops with an error, since the proxy can't rewrite across blocks. `auto --no-check …` or `autowoc …` adds it without checking.
5. Everything runs inside the hook, so nothing enters the conversation. Each run is logged to `~/.claude/context-rewrite/auto/`.

"From A to B" deletes the whole section including A and B; say "keep both ends" to delete only what's between.

## When something goes wrong
Run `/context-rewrite doctor` first. It checks for and automatically fixes:
- missing or outdated scripts, missing or duplicated `--yrb` in the rc file, a missing `/context-rewrite` command
- a corrupted `rules.json` (backed up, then reset), invalid regexes or scopes (that rule is disabled)
- a dead proxy in a `--yrb` session (restarted)
- leftovers from old versions (launchd agent, global `ANTHROPIC_BASE_URL`)

What it can't fix, it explains: this session isn't `--yrb`, or the port is taken by another program. Recent upstream errors from the proxy log are listed too; if the failing requests had replacements, a rule probably broke them, so try `/context-rewrite off`, then `/context-rewrite toggle` rules one by one.

## Recovering from a broken state
**No /reload-plugins after updates:** commands in an already-open session automatically run the newest installed scripts. Only new commands or changed hooks need one reload, and `doctor` tells you when.

**Automatic snapshots:** before rules change (add, delete, toggle, scope) and before `install` modifies an rc file, a snapshot is saved automatically. They manage themselves: unchanged content isn't saved again, a snapshot identical to the next one is dropped, at most 30 are kept, and ones older than 30 days are removed (the newest 5 always stay). Stored in `~/.claude/context-rewrite/snapshots/`.

```
/context-rewrite restore             # list snapshots
/context-rewrite restore 3           # roll back to #3; the current state is saved first, so /context-rewrite restore 1 undoes it
/context-rewrite snapshot known-good # save one manually
```
`restore` runs locally in a hook and **never goes through the API**, so it works even when a rule has broken requests and every message fails.

**Proxy fallback:** if the API rejects a rewritten request with HTTP 400, the proxy automatically resends the original, so the conversation doesn't get stuck; it also records which request failed and why in `proxy.log`. `/context-rewrite doctor` lists these and suggests disabling or rolling back the rule.

**When you don't even want to open claude:**
- claude started without `--yrb` never goes through the proxy and is unaffected by rules
- from a terminal: `python3 ~/.claude/context-rewrite/ctxrw.py restore` (or `off`, `doctor`)

## Uninstall
`/context-rewrite uninstall` removes `--yrb` from the rc file (everything else is left as is), stops the proxy, and deletes `~/.claude/context-rewrite` (rules, snapshots, logs, scripts). The context-rewrite plugin itself is uninstalled too; the cyberchick-skills marketplace stays because it has other tools. Safe to rerun.
Normal sessions are unaffected. Running `--yrb` sessions lose their proxy, so exit and reopen them normally (`claude --continue`).

## How it works
- `--yrb` is a shell function: it sets `ANTHROPIC_BASE_URL=http://127.0.0.1:8787` for that one claude process only and registers the session. If you already have your own `claude()` function (e.g. for `--yolo`), it is kept and wrapped
- The proxy rewrites `system`, message text and `tool_result` in `/v1/messages` requests, then forwards them to `api.anthropic.com` unchanged otherwise; all headers pass through, so claude.ai subscription logins keep working
- The proxy exits on its own once no `--yrb` session is alive, so nothing stays running in the background
- The proxy keeps the latest original request of each session (main agent only) in memory for `capture`; nothing is written to disk until you run `capture`, which writes `captured.txt`
- Files live in `~/.claude/context-rewrite/`: `rules.json`, `proxy.log` (replacement counts only, no content), `captured.txt`
