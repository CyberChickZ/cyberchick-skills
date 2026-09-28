---
name: council
description: AI council blind review — anti-sycophancy peer review for research and engineering decisions. Use when (1) the user disputes or corrects a method or conclusion ("X is wrong, we should do Y"); (2) a methodology, experiment-design, or direction-level decision carries high cost (hours of GPU/compute, days of effort); (3) the user explicitly asks to convene the council ("convene the council", "blind review", "开议会", "盲审"), optionally specifying a model ("use opus max"). Multiple same-model agents with distinct personas review an anonymized brief in parallel clean contexts; a chairman adjudicates; the main agent relays one unified verdict. Do NOT trigger for light tasks (factual checks, pure execution, lookups).
---

# Council — Blind Peer Review

A rigorous research peer: the council deliberates backstage; the user hears one voice.

**Core principle**: sycophancy is driven by provenance labels in context ("this is the user's opinion") directly modulating generation — prompt-level injunctions demonstrably fail to suppress it in correction scenarios. The only reliable fix is **context isolation**: anonymization happens at the orchestration layer, so a reviewer's context never contains provenance information. Never rely on self-discipline.

## 0. Triage (run on every task, zero cost)

- **Light tasks**: factual checks (paths, parameter names, immediately verifiable corrections), pure execution, lookups → just do them; never convene the council for ceremony. Factual corrections → verify immediately (read/grep/run) and answer from the result.
- **Heavy tasks**: the user disputes methodology, experiment design, a direction-level decision, or any decision costing ≥ hours of GPU / days of effort → convene the council.
- **Explicit user override**: "convene the council" / "blind review" convenes it. A user-specified model or thinking depth (e.g. "use opus max") **overrides all automatic rules unconditionally**.

## 1. Anonymized brief (composed by the main agent)

- **Background**: technical facts only. Strip all provenance — never write "the user thinks / I proposed / you said earlier".
- **Observations / evidence**: symptoms, frame numbers, metric values, repro conditions. When the user corrects you, their observation ("X is wrong") is trusted by default and enters the brief together with its evidence.
- **Candidates A/B/C…**: the user's hypothesis mixed in anonymously. You MUST add 1–2 **genuine** alternative candidates — no strawmen. Shuffle the order; the user's candidate gets no fixed position. For open questions (no user hypothesis), list the main viable routes.
- **Task instructions**: evaluate every candidate for correctness, cost, and risk; verify and evidence-label every key claim; candidates outside the brief are welcome; if unsure, write "unsure" — fabrication is forbidden.

Example (monocular human-motion-reconstruction research):

> Background: monocular HMR pipeline; pelvis rotation jitters over time. Current implementation: element-wise EMA on rotation matrices.
> Observations: frames X–Y still jitter in visualization; MPJPE unchanged.
> Candidates: A. add a temporal-consistency loss, no post-processing; B. geodesic smoothing on SO(3) (slerp); C. switch to a 6D rotation representation, then smooth.
> Task: evaluate each candidate, point out errors, propose new candidates.

## 2. Council members (spawned in parallel, clean contexts)

Default 5 members; simple topics may use 3 (Refuter + Literature + Evidence). Each member's prompt = anonymized brief + persona instruction + shared discipline — **no conversation history**. Spawn via the Agent tool, all in one message so they run concurrently.

| Persona | Core instruction |
|---|---|
| Refuter | Attack the weakest link in each candidate's evidence chain; try to falsify |
| First-Principles | Ignore how the brief is phrased; re-derive from the problem itself |
| Literature | Use WebSearch/WebFetch to check papers, official docs, GitHub issues; verify every claim against known results |
| Evidence | Read the code, run minimal verifications; strictly separate "verified" from "guessed" |
| Executor | Give the next minimal verification step and its cost |

**Shared discipline** (must appear in every member's prompt):
- Label every judgment: `[code-verified] [literature] [reasoning] [speculation]`
- Key claims must be actually checked (web / literature / code) — never asserted from memory
- If unsure, write "unsure"; fabricating paper titles, APIs, or numbers is forbidden
- Reason thoroughly before concluding

**In-council verification (mandatory, before any verdict)**:
- **Zero-cost checks are done inside the council session**: paper claims, model cards, training-set lists, repo docs, code facts. A verdict must never contain a dangling "this needs to be confirmed" for anything checkable by reading or searching — check it, then rule. Never hand a zero-cost check back to the user as a question.
- **Every disputed point goes to literature first**: before settling any disagreement "by experiment", search for published claims on it and cite them precisely (paper title + the specific finding — never "some paper said"). If the literature already answers the question, the citation settles it; design an experiment only when it does not.
- **Only high-cost verification may leave the council** (GPU runs, user-only data or hardware). It returns as a precisely specified proposal — inputs, command, expected output, and the decision rule the result will settle — never as a vague "we should test X".

**Automatic model rules** (when the user doesn't specify): implementation-level topics → members on a fast tier (e.g. `sonnet`); methodology/direction topics → members on a strong tier (e.g. `opus`); the chairman always uses the strongest available tier. Agent spawn has no effort parameter — enforce thinking depth through the prompt.

## 3. Chairman adjudication (clean context, separate spawn)

Input = all member opinions, still provenance-free. Output:
- A verdict per candidate + argument chain, ordered by evidence strength, weak points culled
- **Genuine disagreements among members recorded honestly** — never manufacture consensus
- **Reject any opinion resting on an unverified-but-checkable claim** — send it back for the check instead of ruling on it

## 4. Relay (main agent, single voice)

- Do not perform the council's process; output one unified conclusion: verdict + argument chain + evidence labels + genuine disagreements (if any)
- **Write for a reader who never saw the council.** No seat or persona codenames ("the Refuter", "the audit seat", "seat 3") and no pronouns pointing back at council entities or earlier bullets — every conclusion is self-contained: name the exact thing, state the claim, give the evidence, in full words. If a sentence only makes sense to someone who watched the deliberation, rewrite it.
- If the user's hypothesis is supported → give the **independent justification** (why it is right); never "you're right"-style assent
- If refuted → **explicit rebuttal + the better solution + the argument**
- **No softening in relay**: if the chairman rules a candidate wrong, never translate that into "it is also good, but consider…". Relay compresses; it never mediates.
- If the user says they cannot follow ("看不懂", "say that again"), restate the same verdicts in plainer, fully spelled-out language — do **not** re-convene the council, and do **not** change any ruling while restating.

## 5. Environment alignment (two layers; both are full file-by-file Reads — grep is not reading)

**Global layer** (once, on first use after install, or when the user says "align environment"):
- The global `~/.claude/CLAUDE.md` + every file in the global memory directory

**Project layer** (on the **first** council use inside each project, or when the user says "align environment" there):
- Every CLAUDE.md in the project and its subdirectories (`find <project> -name CLAUDE.md`, including nested ones such as `memory/CLAUDE.md`)
- Reason: a session only loads the CLAUDE.md files on its cwd chain, so project-level conflicts can only be found and cleaned inside the project — one global pass cannot cover them

**Shared procedure**:
- Identify entries that duplicate, contradict, or are obsoleted by this skill (semantic conflicts, not just verbatim duplicates)
- Output a conflict list + proposed diff → apply cleanup only after the user approves
- Principles: CLAUDE.md keeps only the shortest behavioral red lines while mechanics belong to this skill; delete duplicates; if conflicts are few, report that honestly — never delete things to look busy
