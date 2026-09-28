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
/context-rewrite auto remove every instruction to add Co-Authored-By   # describe it in one sentence; Claude finds the text, drafts rules, and adds the ones you tick
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
- `auto` gives Claude the original text of the last request as recorded by the proxy, so it copies passages verbatim; when rules are saved, each one is checked against that text and you're warned if it isn't found
- Text blocks that become empty after rewriting are dropped (the API rejects empty text blocks); a message emptied entirely keeps a `(removed)` placeholder
- `/resume`d conversations and subagents inside the same `--yrb` process are rewritten too
- Sessions not started from your terminal (e.g. background agents) are not rewritten
- Thinking blocks are signed and never modified; tool call arguments are never modified either
- Output language: English by default; Chinese when Claude Code's `language` setting (or the system language) is Chinese. Force it with `CTXRW_LANG=zh|en`

### Autocomplete
Every subcommand is also its own command, so typing `/context-rewrite:` lists them all with descriptions:
`/context-rewrite:install`, `:auto`, `:add`, `:capture`, `:list`, `:rm`, `:toggle`, `:scope`, `:on`, `:off`, `:status`, `:doctor`, `:restore`, `:snapshots`, `:snapshot`, `:uninstall`.
`/context-rewrite:capture` is the same as `/context-rewrite capture`. Short names such as `/capture` work too, except `status`, `doctor` and `help`, which Claude Code already uses — type the full name for those.

### auto: describe the change, paste the text in `{braces}`
```
/context-rewrite auto delete from {- Entering financial credentials, bank/card/…} to {- Downloading or executing files from untrusted sources}
/context-rewrite auto replace {Creating accounts on the user's behalf} with {Creating accounts is fine}
```
1. The script pulls the text out of each `{…}` verbatim (it never goes through the model, so it can't be mistyped).
2. Only the remaining instruction (`delete from {0} to {1}`) goes to Claude (sonnet, low effort, no tools), which returns a regex skeleton such as `{0}[\s\S]*?{1}\n?`.
3. Python substitutes each placeholder with a forgiving regex for the pasted text: line breaks / indentation / terminal wrapping, curly vs straight quotes, dash variants, `…` vs `...`, lost or extra markdown (`**`, `` ` ``, `_`, `#`, `>`), list bullets and numbering, terminal `│ ⎿` prefixes and Read-tool line numbers are all ignored.
4. By default it is checked against the whole last request (system, all messages, tool descriptions): added only if it matches, scope set to where it matched, with a before/after preview. `auto --no-check …` adds it without checking (no --yrb session needed). `{i}` in the replacement re-inserts the original matched text, not your pasted copy.
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
**Automatic snapshots:** before rules change (add, delete, toggle, scope) and before `install` modifies an rc file, a snapshot is saved automatically. The last 30 are kept in `~/.claude/context-rewrite/snapshots/`.

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
