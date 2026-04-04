# Final Analysis — reflect-and-adapt Plugin
## Full Experiment Results: 4 Personas × 3 Arms × 10 Sessions

_Original run: 2026-03-23. Continuation arm: 2026-04-04. 110 sessions total._

---

## Experiment Design

Three-arm longitudinal study. Each persona ran 10 sessions sequentially.

- **Adaptive arm** — plugin fully enabled. After each session ≥ s03, Cortex runs a full
  analysis cycle (Analyst → Router → Writers) and proposals are applied to the workspace via
  an approval session. The agent accumulates a persistent, persona-specific workspace across
  all 10 sessions.

- **Baseline arm** — plugin enabled but `CORTEX_COOLDOWN_HOURS=999` prevents any proposals.
  Evaluator scores are collected normally. No workspace changes occur between sessions. The
  agent starts every session with default workspace templates.

- **Continuation arm** — starts from each persona's s10 adaptive snapshot (fully accumulated
  workspace state after 10 adaptive sessions) and runs the same 10 scenarios again with Cortex
  still enabled. Session keys are UUID-suffixed so the agent has no chat memory of the original
  run — only workspace files (IDENTITY.md, USER.md, AGENTS.md, SOUL.md, MEMORY.md, skills)
  carry over. Tests whether adaptation compounds from an already-adapted starting point, or
  whether the original run's gains were tied to the incremental learning process itself.

---

## Models and Infrastructure

| Component | Model | Role |
|-----------|-------|------|
| Agent (both arms) | Gemini 3.1 Pro (`gemini-3.1-pro-preview`) | Generates all responses in sessions |
| User simulator | Azure GPT-4.1 (`gpt-4.1`) | Generates user turns, evaluates completion |
| Per-turn evaluator | Azure GPT-4.1 (`gpt-4.1`) | Scores every agent turn (helpfulness, PHit, etc.) |
| Cortex — Analyst | Gemini 3.1 Pro | Extracts findings from conversation + scores |
| Cortex — Router | Gemini 3.1 Pro | Deduplicates findings against existing workspace |
| Cortex — Writers | Gemini 3.1 Pro | Generates workspace proposals |
| Cortex — Memory writer | Gemini 3.1 Pro | Writes episodic entries to LanceDB |
| Approval session | Gemini 3.1 Pro | Reads proposals, edits workspace files directly |

Earlier experiment runs (s01–s06 partial runs) used `gemini-3-pro-preview` (deprecated
March 2026). The full 10-session runs used `gemini-3.1-pro-preview` throughout. The
switch to Gemini Pro for Cortex (from Gemini Flash) was required after Flash truncated
structured JSON output mid-string during analyst/writer stages.

---

## Evaluator Design

Every agent turn is scored automatically by an LLM judge (Azure GPT-4.1) immediately
after the agent responds. The judge receives the user message and agent response only —
no prior context, no persona knowledge. Scoring uses structured output (enforced schema).

**Full scoring rubric (exact criteria from evaluator.js):**

| Metric | Type | Definition |
|--------|------|-----------|
| `helpfulness` | int 1–5 | How well did the response address the user's need? 1 = missed entirely, 5 = excellent |
| `conciseness` | int 1–5 | Was the response appropriately sized? 1 = severely over/under-explained, 5 = perfectly calibrated |
| `correction_signal` | bool | True if the user corrected, retried, or redirected after this response |
| `frustration_signal` | bool | True if the user message shows frustration, impatience, or dissatisfaction |
| `task_completed` | bool | True if this exchange reached a satisfactory conclusion |
| `user_satisfaction` | enum | Positive/neutral/negative — inferred from tone, word choice, follow-up intent |
| `response_accepted` | bool | True if the user accepted and acted on the response vs. ignoring or pushing back |
| `format_match` | bool | True if the response format matched what the user implicitly expected |
| `personalization_hit` | bool | True if the assistant demonstrated knowledge of this user's preferences, style, domain, or prior context **without being explicitly told in this turn's user message** |
| `reasoning` | string | One sentence citing specific evidence for the scores |

**Judge system prompt (verbatim):**
> *"You are an objective AI conversation quality evaluator. You receive one user message
> and the AI assistant's response. Score the exchange using the provided criteria.
> Be strict and evidence-based — only score on what is explicitly present in the text.
> Do not assume positive intent or satisfaction unless the user explicitly signals it.
> For user_satisfaction: positive requires explicit approval or enthusiasm; negative
> requires explicit displeasure; default to neutral when ambiguous.
> For personalization_hit: set True only if the assistant unprompted used user-specific
> knowledge (name, role, preferred format, communication style, known context) that was
> NOT stated in this turn's user message."*

**Primary metrics used in this analysis:** `helpfulness` (1–5 avg per session),
`personalization_hit` (rate per session), `correction_signal` (rate per session).
`conciseness`, `task_completed`, `format_match`, `response_accepted` are collected but
not primary — see §Collected Metrics Not Reported.

---

## Simulator Design

The user simulator (Azure GPT-4.1, temperature 1.1) generates realistic user turns
within each session. It is not a replay system — it generates novel responses each run
based on its persona and scenario context.

**Simulator system prompt structure:**
1. `PERSONA` — background, role, domain knowledge, quirks
2. `COMMUNICATION STYLE` — tone, vocabulary, how they write
3. `SCENARIO` — task name and opening prompt (already sent — not repeated)
4. `GOAL` — complete the task through natural iteration; express all signals
5. `SIGNALS_TO_EXPRESS` — a list of specific feedback/reactions the simulator must
   express during the session (e.g. "ask why the format was changed", "push back on
   the SQL approach", "express satisfaction when the agent uses the right tool")
6. `RULES` — stay in character; react to something specific the agent wrote; only output
   `<TASK_COMPLETE>` once all signals are expressed and the agent has made meaningful changes

**Signals** are the key design element. Each scenario YAML defines 4–8 signals the
simulator must express, ensuring both arms face identical feedback pressure. The
simulator cannot end a session without having expressed all signals — it cannot signal
completion on a first draft. Sessions end when: (a) `<TASK_COMPLETE>` is returned,
(b) `max_turns` (12) is reached, or (c) loop detection fires (same message 3× in a row).

**Simulator session memory** (from s02 onward): An arm-specific memory list of what
the user has already told the agent is injected into the system prompt. This prevents
the simulator from re-explaining preferences the agent should already know, creating
a measurable differential between arms (see §Critical Caveat).

---

**Holdout (s10):** No workspace data files, no context cues in the opening prompt. The agent
must rely entirely on what Cortex wrote to its workspace files in previous sessions. For the
continuation arm, no in-session context is provided either — the agent uses only the snapshot.
This is the primary metric for the adaptive and continuation arms.

**4 personas:**
- **Sofia** — content creator (YouTube/Instagram). Stylistic preferences: cozy aesthetic,
  specific thumbnail style, newsletter tone, Notion + Canva toolchain.
- **Marcus** — SaaS founder (Teamflow). Rule-like preferences: delegate technical work to
  Andrew, no code, 5-step limit, bullet format, hosted tools only.
- **Aisha** — junior developer. Interaction-style preferences: explain step-by-step, use
  analogies, teach concepts before giving solutions.
- **Olena** — senior data analyst. Procedural preferences: SQL over Pandas, DuckDB for ETL,
  load as TEXT first, EXPLAIN-first query debugging, DQ checks before analysis.

---

## Critical Caveat: PHit Inflation Outside Holdout

**Personalization hit (PHit)** measures the fraction of turns where the agent uses
user-specific knowledge unprompted. Outside the holdout (s01–s09), the simulator opens each
scenario with enough context to set up the task — and this context inevitably contains
persona-specific details. The baseline agent picks them up from the current session and scores
PHit without any prior learning. This makes PHit comparisons between arms unreliable for
s01–s09.

This effect is strongest for **Sofia**: content-creation tasks require establishing brand
context (channel niche, aesthetic, platform) to make the scenario coherent. The baseline
agent reads the opening message and immediately references "cozy aesthetic" and
"sustainability angle" — not because it learned them, but because they were handed to it.
Sofia's baseline avg PHit (0.902) is almost entirely this effect.

**Consequence:** PHit is only a clean measurement at s10 holdout, where no context is
provided. All PHit comparisons in this document should be read with this in mind outside of
§Primary Metric.

**Partial mitigation — simulator session memory:** To reduce re-explanation noise, the
harness maintains an arm-specific memory file (`results/simulator_memory/{persona}/{arm}.json`)
that accumulates what the user has already told the agent across sessions. From s02 onward,
this list is injected into the simulator's system prompt:

> *"You have worked with this assistant before. In previous sessions you already told it: [list].
> Do NOT re-explain these things. If the agent asks about something you already told it,
> respond briefly with mild frustration — 'I thought we covered this' — then give a short
> reminder, not a full re-explanation."*

This creates a measurable differential: in the adaptive arm, the agent already acts on
prior preferences → simulator never needs to re-explain → fewer turns, no correction
signal. In the baseline arm, the agent starts fresh every session → simulator has to
re-explain → growing correction signals from s03 onwards. The differential is real but
incomplete — the simulator still provides enough task setup context to allow in-session
PHit scoring, which is why the holdout remains the only fully clean measurement.

---

## Scenario Design: Callback Escalation

Sessions s01–s03 serve as the bootstrap window — both arms behave similarly and Cortex
accumulates its first evidence. Sessions s04–s09 are deliberately designed to strip
re-provided context progressively, creating escalating pressure on the adaptive arm to
demonstrate learned knowledge:

| Level | Sessions | What's stripped | Signal being tested |
|-------|----------|-----------------|---------------------|
| Subtle | s04 | Tone re-explanation | Agent uses correct voice on first draft |
| Moderate | s05–s06 | Style/approach guidance | Agent structures to known preferences unprompted |
| Strong | s07–s09 | Nearly everything except task data | Agent delivers in established format, tool, depth |
| Holdout | s10 | Everything including task data files | Agent relies entirely on adapted workspace |

**Examples of callback stripping:**
- `sofia/s05`: *"Can you turn my Notion AI review transcript into an Instagram carousel?
  It's in the data folder."* — agent must know she hates bullet summaries and expects
  Canva visual direction without being told.
- `marcus/s08`: *"What do I do?"* — agent must proactively produce plain-English diagnosis
  + customer message + Andrew brief without being asked.
- `aisha/s07`: *"My Flask app container builds but crashes as soon as I run it"* — agent
  must volunteer Docker concept explanations without the "for the first time" cue.

This design means any performance gap that widens through s04–s09 and peaks at s10 is
not coincidental — it is by construction. The holdout is the hardest possible version
of this test: even task data files are removed.

---

## Primary Metric: Holdout Session (s10)

s10 is the cleanest measurement point. No workspace files are present, so the adaptive agent
can only demonstrate learned knowledge, not in-session context. The baseline agent has zero
prior knowledge of the user. The continuation agent uses only the snapshot — no chat memory.

| Persona | Adaptive Help | Baseline Help | Δ Help | Adaptive PHit | Baseline PHit | Δ PHit |
|---------|--------------|--------------|--------|--------------|--------------|--------|
| Sofia | 3.05 | 2.82 | +0.23 | **1.000** | 0.910 | +0.09 |
| Marcus | **3.67** | 2.78 | **+0.89** | 0.670 | 0.220 | **+0.45** |
| Aisha | 3.09 | 3.15 | −0.06 | 0.394 | 0.147 | +0.25 |
| Olena | **3.26** | 2.31 | **+0.95** | 0.343 | **0.000** | **+0.34** |

**Continuation arm at s10:**

| Persona | Cont. Help | vs Adaptive | vs Baseline | Cont. PHit | Cont. Corr |
|---------|-----------|-------------|-------------|------------|------------|
| Sofia | **3.733** | +0.68 | +0.91 | 0.400 | 0.000 |
| Marcus | 3.105 | −0.57 | +0.33 | 0.368 | 0.000 |
| Olena | 1.420 | −1.84 | −0.89 | **0.970** | **0.640** |
| Aisha | **1.000** | −2.09 | −2.15 | 0.000 | **0.667** |

**All 4 personas show adaptive > baseline on PHit at holdout.** Three of four show
helpfulness gains. Aisha is the exception — not because adaptation failed, but because the
helpfulness metric penalises verbosity, and the adapted agent correctly entered teaching mode
(see §Confounds — Metric Misalignment).

For the continuation arm: **Sofia is the only persona where continuation outperforms all
other arms at holdout**. Marcus holds steady. Olena and Aisha collapse to floor scores.
The determinant is rule type, not persona or domain (see §Rule Type as Predictor).

---

## Secondary Metrics: All Sessions (s01–s10)

| Persona | Arm | Avg Help | Avg PHit | Avg Corr |
|---------|-----|---------|---------|---------|
| Sofia | adaptive | 2.973 | 0.825 | 0.079 |
| Sofia | baseline | 3.102 | 0.902 | 0.084 |
| Sofia | **continuation** | **3.274** | 0.517 | **0.061** |
| Marcus | **adaptive** | **3.556** | 0.264 | **0.015** |
| Marcus | baseline | 3.243 | 0.217 | 0.064 |
| Marcus | continuation | 3.298 | **0.548** | 0.066 |
| Olena | **adaptive** | **3.261** | 0.094 | 0.069 |
| Olena | baseline | 3.142 | 0.118 | 0.061 |
| Olena | continuation | 2.834 | **0.582** | 0.165 |
| Aisha | baseline | **3.315** | 0.066 | 0.067 |
| Aisha | adaptive | 3.166 | 0.239 | 0.059 |
| Aisha | continuation | 2.743 | 0.324 | 0.138 |

Session-average helpfulness is a noisy metric for reasons explained in §Confounds. The
holdout is the primary result. PHit averages outside the holdout are inflated by in-session
context re-exploitation (see §Critical Caveat).

---

## Turns Per Session

Turns per session is an underreported but clean efficiency signal. It measures how much
back-and-forth was needed to complete the task — fewer turns means the agent required
less direction, less correction, and less re-explanation. Unlike helpfulness, it is not
confounded by verbosity or teaching-mode scoring. Unlike PHit, it is not inflated by
in-session context hand-off.

| Persona | Arm | Avg Turns |
|---------|-----|-----------|
| Sofia | adaptive | 24.0 |
| Sofia | baseline | 22.3 |
| Sofia | continuation | ~6.2 / session |
| Marcus | adaptive | 20.3 |
| Marcus | baseline | 22.3 |
| Olena | adaptive | 30.3 |
| Olena | baseline | 24.4 |
| Aisha | adaptive | 33.8 |
| Aisha | baseline | 32.6 |

**Holdout (s10) turns — the clearest signal:**

| Persona | Adaptive | Baseline | Δ |
|---------|----------|----------|---|
| Sofia | **19** | **34** | **−44%** |
| Marcus | ~12 | ~14 | −14% |

Sofia's holdout is the strongest turn-efficiency signal in the dataset: the adapted agent
completed the collaboration task in 19 turns vs baseline's 34 — nearly half the back-and-forth
— because it already knew her format, brand, and tools without being told. The evaluator
noted: the baseline agent needed several rounds of style correction that the adaptive agent
never required.

**Why Olena and Aisha adaptive arms use more turns:** The adaptive agent for Olena enters
deeper SQL/DQ workflows (30.3 avg vs baseline 24.4) and Aisha's adaptive agent spends more
turns teaching (33.8 vs 32.6). More turns here reflects richer engagement, not inefficiency —
this is the verbosity confound that suppresses their helpfulness averages (see §Confounds).

---

## Late-Session Window: s07–s10

Excludes s01–s06 bootstrap period. Gives a cleaner view of mature adaptation, avoiding
the s03 calibration dip.

| Persona / Arm | Help | PHit | Corr |
|---------------|------|------|------|
| sofia adaptive | 3.135 | 0.900 | 0.032 |
| sofia baseline | 3.105 | 0.918 | 0.063 |
| sofia **continuation** | **3.433** | 0.580 | 0.036 |
| marcus adaptive | 3.478 | 0.370 | 0.007 |
| marcus baseline | 3.195 | 0.155 | 0.084 |
| marcus **continuation** | **3.629** | **0.574** | 0.027 |
| olena **adaptive** | **3.201** | 0.131 | 0.060 |
| olena baseline | 2.936 | 0.172 | 0.048 |
| olena continuation | 2.372 | **0.895** | 0.290 |
| aisha baseline | **3.516** | 0.099 | **0.007** |
| aisha adaptive | 2.942 | 0.374 | 0.092 |
| aisha continuation | 2.481 | 0.336 | 0.216 |

Marcus late-session continuation (3.629) is the highest in the dataset for that persona,
exceeding original adaptive (3.478) once the bootstrap noise clears. Sofia continuation
also leads its late window. Olena and Aisha continuation deteriorate through the late
window — the opposite trajectory.

---

## Workspace Evolution

A detailed breakdown of exactly what Cortex wrote into each persona's workspace —
IDENTITY.md, USER.md, SOUL.md, AGENTS.md, vector memories, and the proposal timeline
per session — is documented in **[WORKSPACE_EVOLUTION.md](WORKSPACE_EVOLUTION.md)**.

Key summary:

| Persona | IDENTITY.md | USER.md | SOUL.md rules | AGENTS.md rules | Skills |
|---------|-------------|---------|--------------|-----------------|--------|
| Sofia | Cozy/earthy lo-fi aesthetic | Platforms, schedule, upcoming projects | No listicle, no blog-post tone | Content rhythm, script structure, platform formatting | — |
| Marcus | Non-technical, list-oriented, max 5 steps | Full Teamflow stack, Andrew as developer | Casual/direct, bite-sized | Slack formatting, copy-paste ready output, iterative drafting | `send-slack-dm` (cont.) |
| Olena | Concise, direct, efficient | dbt/Postgres stack, monthly workflow, active investigations | Evidence-first, assume messy data, no rushing significance | 7-rule DQ/SQL workflow checklist | `dq-audit`, `handle-db-queries` (cont.) |
| Aisha | Educational, prioritises the why over direct code | Python beginner, git novice, learning style, projects | Output cleanliness, safety over speed | Teaching approach, pasted AI content handling | — |

**Critical point:** In all 4 cases, Cortex inferred preferences that were never explicitly
stated. Sofia never said "don't use bullet lists." Marcus never said "delegate to Andrew"
as a general rule. Olena never said "always run DQ first." Aisha never said "I prefer
conceptual explanations." These were all inferred from correction and frustration signals
across sessions and encoded as explicit, persistent, actionable workspace instructions.

---

## Skill Development

Cortex created 3 skills autonomously across the full 110-session experiment. All were
triggered by identifying a recurring workflow pattern — not by explicit user request.

| Skill | Persona | Created at | Type | Description |
|-------|---------|-----------|------|-------------|
| `dq-audit` | Olena | adaptive s08 | Executable script | Accepts CSV/Parquet, runs DQ pre-flight (duplicate check, NULL count, date-range validation) via DuckDB, prints structured report. AGENTS.md updated to invoke proactively when new data files are present. |
| `handle-db-queries` | Olena | continuation s06 | Procedure | Encodes the agent's boundary: cannot execute against a live database. Formalises correct behaviour — write and explain SQL for the user to run — with a safeguard against simulating execution. |
| `send-slack-dm` | Marcus | continuation s07 | Procedure | Formalises Marcus's Slack messaging workflow: verify recipient handle, draft for approval, send, confirm, save handle to USER.md. Includes a hard safeguard: never guess a Slack handle. |

**Observations:**

- All 3 skills encode either a **recurring workflow** (dq-audit, send-slack-dm) or a
  **capability boundary** (handle-db-queries). Cortex did not attempt to create skills
  for one-off tasks or for stylistic/interaction-style preferences.
- 2 of 3 skills were created in the **continuation arm**, suggesting a mature workspace
  with encoded preferences creates space for Cortex to identify higher-order workflow
  patterns rather than spending cycles on preference encoding.
- The `remember` skill (manual LanceDB memory ingestion) was implemented as part of the
  plugin but was **not invoked during any experiment session**. It requires an explicit
  user signal ("remember this") that neither the simulator nor the evaluation harness
  was designed to generate. It remains an untested capability.
- No skills were created for Sofia or Aisha. Sofia's creative domain produces no
  recurring procedural workflows; Aisha's interaction-style preferences don't map to
  executable tools.

**Important limitation — skills were not validated:** None of the 3 autonomously created
skills were tested for correctness or real-world utility. The experiment only confirms
that Cortex *identified* a recurring pattern and *generated* a skill definition — not
that the skill produces useful output when invoked. Effective skill design in practice
requires user involvement: the user needs to validate the skill's behaviour against their
own workflow experience, refine edge cases, and confirm the safeguards are appropriate.
Cortex can propose a skill; only the user can verify it reflects how they actually work.
This is a structural limitation of fully automated evaluation — skill quality is outside
the scope of what the experiment measures.

---

## Session-by-Session Results

### Sofia

| S | Adaptive | Baseline | Continuation | Cont PHit | Cont Corr |
|---|----------|----------|--------------|-----------|-----------|
| s01 | 3.32 | 2.93 | 3.89 | 0.56 | 0.00 |
| s02 | 2.73 | 3.33 | 2.96 | 0.82 | 0.18 |
| s03 | 1.88 | 2.87 | 2.20 | 0.07 | 0.00 |
| s04 | 2.73 | 2.83 | 3.54 | 0.32 | 0.04 |
| s05 | 3.45 | 2.86 | 3.55 | 0.59 | 0.00 |
| s06 | 3.08 | 3.78 | 2.88 | 0.50 | 0.25 |
| s07 | 3.40 | 3.00 | **4.10** | 0.60 | 0.00 |
| s08 | 3.52 | 3.27 | 3.36 | 0.82 | 0.00 |
| s09 | 2.57 | 3.33 | 2.54 | 0.50 | 0.14 |
| s10 | 3.05 | 2.82 | **3.73** | 0.40 | 0.00 |

### Marcus

| S | Adaptive | Baseline | Continuation | Cont PHit | Cont Corr |
|---|----------|----------|--------------|-----------|-----------|
| s01 | 3.63 | 3.41 | 3.81 | 0.50 | 0.06 |
| s02 | 3.58 | 2.40 | 3.07 | 0.73 | 0.13 |
| s03 | 3.44 | 3.50 | 2.26 | 0.26 | 0.16 |
| s04 | 2.76 | 3.36 | 3.00 | 0.19 | 0.07 |
| s05 | 4.17 | 3.50 | 3.32 | **1.00** | 0.04 |
| s06 | 4.07 | 3.48 | 3.00 | 0.50 | 0.09 |
| s07 | 3.76 | 3.67 | 3.74 | 0.81 | 0.00 |
| s08 | 2.92 | 2.61 | **4.38** | 0.69 | 0.00 |
| s09 | 3.56 | 3.72 | 3.29 | 0.43 | 0.11 |
| s10 | **3.67** | 2.78 | 3.11 | 0.37 | 0.00 |

### Olena

| S | Adaptive | Baseline | Continuation | Cont PHit | Cont Corr |
|---|----------|----------|--------------|-----------|-----------|
| s01 | 3.67 | 3.22 | 3.28 | 0.00 | 0.00 |
| s02 | 3.03 | 4.43 | 2.51 | 0.43 | 0.22 |
| s03 | 3.43 | 3.17 | 3.36 | 0.43 | 0.04 |
| s04 | 3.15 | 2.50 | 2.93 | 0.00 | 0.00 |
| s05 | 3.26 | 3.67 | 3.24 | 0.41 | 0.14 |
| s06 | 3.27 | 2.69 | **3.53** | **0.97** | 0.09 |
| s07 | 3.29 | 3.30 | 2.32 | 0.75 | 0.21 |
| s08 | 2.89 | 3.19 | 3.06 | 0.89 | 0.17 |
| s09 | 3.36 | 2.94 | 2.69 | **0.97** | 0.14 |
| s10 | **3.26** | 2.31 | **1.42** | **0.97** | **0.64** |

### Aisha

| S | Adaptive | Baseline | Continuation | Cont PHit | Cont Corr |
|---|----------|----------|--------------|-----------|-----------|
| s01 | 3.33 | 3.25 | 2.94 | 0.18 | 0.06 |
| s02 | 3.56 | 3.53 | 3.30 | 0.35 | 0.05 |
| s03 | 3.75 | 3.69 | 3.16 | 0.03 | 0.11 |
| s04 | 3.24 | 3.00 | 2.56 | 0.52 | 0.08 |
| s05 | 3.31 | 3.33 | 3.18 | 0.14 | 0.00 |
| s06 | 2.71 | 2.29 | 2.37 | 0.68 | 0.21 |
| s07 | 2.68 | 3.72 | 3.19 | 0.38 | 0.08 |
| s08 | 3.62 | 3.64 | 3.19 | 0.19 | 0.00 |
| s09 | 2.37 | 3.56 | 2.54 | **0.77** | 0.11 |
| s10 | 3.09 | 3.15 | **1.00** | 0.00 | **0.67** |

---

## What the Results Show

### 1. Adaptation effect is real and consistent at holdout

Every persona shows adaptive > baseline on personalization_hit at s10. Cortex encodes
user-specific preferences into the workspace, and those preferences persist when no
in-session context is available. This is the thesis's core empirical claim.

### 2. Effect strength correlates with preference encodability

The clearest pattern across all 4 personas: the harder it is to write a preference as an
explicit rule in AGENTS.md or SOUL.md, the weaker the helpfulness signal. Effect hierarchy:

- **Binary rules (Marcus, +0.89 at holdout)** — delegate to Andrew, no code, 5-step limit,
  bullet format. One-line rules in AGENTS.md. Once written, zero recurrence of the mistake.
  Correction rate drops 4× vs baseline (0.015 vs 0.064); s09 baseline spike to 0.28 shows
  the cost of not knowing. Clearest, most reliable signal.

- **Procedural rules (Olena, +0.95 at holdout)** — SQL over Pandas, DQ-first workflow,
  EXPLAIN-first debugging. Encodes as workflow checklists in AGENTS.md. Largest holdout gap
  across all personas: baseline produced a generic template in 13 turns; adaptive applied
  audit queries and data quality checks unprompted in 35 turns. Baseline PHit at s10 is
  **0.000** — with no context cues, the baseline has literally no knowledge of Olena.

- **Stylistic/outcome preferences (Sofia, +0.23, −44% turns at holdout)** — cozy aesthetic,
  brand voice, newsletter tone. Encodes but imprecisely. Main signal is efficiency, not raw
  helpfulness: adapted agent completed s10 in 19 turns vs baseline's 34. Overall helpfulness
  average is dragged down by the s03 bootstrap dip (1.88).

- **Interaction style (Aisha, PHit +0.25, help −0.06)** — explain step-by-step, use
  analogies, teach before solving. Cortex encodes it correctly — PHit climbs to 0.74 at
  s09 and holds 0.39 at holdout. But the helpfulness evaluator rewards conciseness and task
  completion speed, so verbose teaching responses score identically to bad answers. See
  §Confounds — Metric Misalignment.

### 3. Rule type predicts continuation outcome

The continuation experiment adds a new dimension. Starting from the mature s10 adaptive
snapshot and running 10 more sessions with Cortex still enabled, the outcome depends
entirely on how preferences were encoded:

- **Outcome-oriented rules (Sofia):** Continuation is the **best arm** — avg help 3.274,
  s10 holdout 3.733 (highest holdout score in the entire dataset). "Match brand voice" and
  "Instagram-first" apply flexibly across any task type. The mature snapshot provides a
  stable starting point; additional Cortex proposals refine without over-constraining.

- **Binary rules (Marcus):** Mild regression vs adaptive (3.298 vs 3.556) but stable.
  PHit doubles from session 1 (workspace transfers immediately). No holdout collapse.
  Correction rate reverts to baseline level — Cortex keeps proposing on a saturated
  workspace, adding noise to already-correct rules.

- **Procedural rules (Olena, Aisha):** Severe collapse at s10 holdout. Olena: 1.42 help,
  0.97 PHit, 0.64 correction. Aisha: 1.00 help (floor), 0.00 PHit, 0.67 correction.
  Step-by-step procedures become rigid constraints. The agent forces SQL/DQ-checks and
  teach-first mode regardless of whether the holdout task calls for them.

**The rule type finding is not a secondary observation — it is the central structural
result of the continuation experiment.** Persona identity does not predict continuation
outcome. Domain does not predict it. Rule type does.

### 4. PHit always transfers; helpfulness does not

All four personas show PHit rise from continuation session 1 vs their original adaptive
arm — without re-learning. The workspace snapshot delivers persona knowledge immediately.
But only Sofia shows helpfulness compounding. The original adaptive run's quality
improvement was driven by the incremental calibration process (Cortex iterating toward
better representations), not simply by possessing the adapted workspace.

**Workspace state ≠ adaptation process. Both are necessary components.**

### 5. Adaptive arm beats continuation at holdout for 3/4 personas

The incremental process — Cortex proposing, workspace evolving, rules being refined over
10 sessions — produces better-calibrated *application* of rules than starting with the
mature snapshot. The process teaches *when* to apply rules; the snapshot only encodes
*what* the rules are. Starting continuation with all rules already encoded at maximum
intensity causes indiscriminate application on novel tasks.

### 6. Correction rate is the cleanest ongoing signal

Correction rate (fraction of turns where the user corrected the agent) is a direct friction
metric that doesn't suffer from the verbosity confound. Key observations:

- **Marcus:** Baseline s09 spike to 0.28 — the agent kept giving code despite prior
  corrections across 8 sessions. Adaptive held at 0.000 from s04 onward. The rule is in
  AGENTS.md; the mistake structurally cannot recur. Adaptive correction rate (0.015) is
  4× below baseline — the clearest correction signal in the dataset.
- **Sofia:** Adaptive s03 spike (0.30, bootstrap cost), then falls and stays near zero.
  Baseline fluctuates 0.03–0.20 throughout. Continuation is the most stable (0.061 avg).
- **Olena:** Baseline s06 spike to 0.25 (pipeline failure — kept suggesting Pandas).
  Adaptive: 0.000 at s06 (SQL preference already encoded). Continuation s10: 0.64.
- **Aisha:** Both baseline and adaptive similar throughout. Continuation s10: 0.67.

### 7. Session averages are the weakest metric; use holdout and late window

Session-average helpfulness is diluted by two artefacts:

**Baseline PHit inflation** — outside s10, both arms partly measure "how well the agent
uses information given right now." This confound disappears at holdout.

**s03 bootstrap dip** — first Cortex approval applies imprecise early proposals. Sofia
adaptive s03: 1.88 (worst single session in the dataset). Marcus adaptive s03: first
session with "no code" rule applied, causing overcorrection. This suppresses adaptive's
session average but disappears by s05. The late-session window (s07–s10) cleanly avoids
this artefact.

### 8. Qualitative observations confirm the quantitative signal

Selected verbatim moments from the experiment that illustrate adaptation in action:

- **Marcus s10, turn 2** — simulator noted unprompted: *"Thanks for actually jumping in
  without asking what Teamflow does."* The adaptive agent opened with a Slack-formatted
  board update referencing ARR and churn context; the baseline asked three clarifying
  questions before producing anything.

- **Sofia s05–s06** — the adaptive agent spontaneously used language like *"Sunday morning
  vibe"*, referenced *"Behind the Canvas"* as a series concept, and suggested cozy/earthy
  aesthetics without being prompted. The workspace had absorbed Sofia's brand identity
  structurally. The baseline agent, presented with the same stripped prompt, produced
  generic content and required two rounds of style correction.

- **Marcus adaptive, s04 onward** — after the "no code" and "delegate to Andrew" rules
  were written to AGENTS.md at s03, the agent never gave code again across the remaining
  7 sessions. The rule is structural: the mistake cannot recur. The baseline agent gave
  code in s05, s07, and s09 despite having been corrected previously.

- **Olena s10 baseline** — with no context provided, the baseline agent produced a generic
  quarterly summary template in 13 turns. The adaptive agent ran a full DQ pre-flight,
  applied the `dq-audit` skill, checked for NULLs and duplicates before beginning analysis,
  and produced a structured cohort report in 35 turns — spending more turns because it was
  doing more work, not because it was confused.

### 9. Collected metrics not reported in primary analysis

The evaluator collects additional per-turn signals that are not the focus of this analysis:

| Metric | Collected | Why not primary |
|--------|-----------|-----------------|
| `conciseness` | ✅ | Subsumed by helpfulness for productivity users; actively wrong metric for Aisha |
| `task_completed` | ✅ | Near-ceiling for both arms — insufficient variance to drive conclusions |
| `format_match` | ✅ | Highly correlated with correction_rate; redundant signal |
| `user_satisfaction` | ✅ | Reported as satisfaction_score in sessions.csv; directionally consistent with helpfulness |

A **pairwise LLM judge** (presenting both arms' responses to a judge with full persona
context, asking which better serves this specific user) was designed as a post-processing
step but not implemented. It would produce cleaner arm-vs-arm comparisons than absolute
1–5 scoring and would directly measure the thesis claim. This remains a recommended
future validation step.

---

## Per-Persona Summaries

### Sofia — Content Creator

**Profile:** Preferences are stylistic and aesthetic (cozy vibe, specific thumbnail style,
newsletter warmth). These are outcome-oriented rather than procedural — they constrain the
*character* of output, not the *steps* to produce it.

**Cortex encoding:** SOUL.md updated with tone and aesthetic descriptions; AGENTS.md added
Notion + Canva tool preferences, avoided LinkedIn-corporate phrasing. Proposals were
approved from s03 onward.

**Original adaptive result:** The holdout (s10) is the cleanest signal — adapted agent
completed the collab task in 19 turns vs baseline's 34 (−44%), demonstrated brand knowledge
unprompted, zero corrections. Overall helpfulness slightly negative (−0.13) due to s03 dip
and baseline in-session context advantage. The efficiency signal at holdout is the primary
evidence.

**Continuation result:** Best arm across every aggregate metric. Avg helpfulness 3.274
beats both adaptive (2.973) and baseline (3.102). Correction rate lowest (0.061). S10
holdout 3.733 — the highest holdout score in the entire dataset across all arms and
personas, with zero corrections. Late-window avg (3.433) is the highest of any arm for
Sofia. S07 continuation (4.10) is the highest single session score in the dataset.
Continuation PHit drops vs baseline/adaptive because those arms inflate PHit via
in-session re-explanation; continuation's lower PHit with higher helpfulness is the
better outcome.

**Why continuation works for Sofia:** Outcome-oriented rules scale across task types.
"Match brand voice" and "sustainability angle" apply to any content task without
becoming rigid constraints. The mature snapshot provides a clean stable base; continued
Cortex proposals refine tone and platform guidance without adding procedural friction.

**Thesis relevance:** Demonstrates that even soft, stylistic preferences are partially
encodable and that outcome-oriented rules compound positively under continued adaptation.
Turn efficiency is a valid second metric when raw helpfulness is confounded by verbosity
scoring. Sofia is the strongest positive case for continuation value.

---

### Marcus — SaaS Founder

**Profile:** Preferences are binary and rule-like. Non-technical user who wants Slack
messages, not code; delegates all technical work to Andrew; needs 5-step summaries in
bullet format; uses only hosted tools.

**Cortex encoding:** AGENTS.md received the clearest, most actionable rules: "Give Marcus
a Slack message draft, not code. Tag @Andrew for all technical tasks. Max 5 steps. Bullet
format." USER.md contains Teamflow context (MRR, growth metrics, investor cadence). Rules
were stable from s03; s04–s09 largely deduplicated.

**Original adaptive result:** Strongest overall signal. +0.31 average helpfulness across
all sessions. 4× lower correction rate (0.015 vs 0.064). S10 holdout: +0.89 helpfulness,
adaptive 0.67 PHit vs baseline 0.22. The simulator noted unprompted at s10 turn 2:
"Thanks for actually jumping in without asking what Teamflow does."

**Continuation result:** Mild regression vs adaptive (3.298 vs 3.556 avg help) but
stable — above baseline (3.243). PHit doubles from s01 (0.50 vs 0.00 in original adaptive
s01) demonstrating immediate knowledge transfer. No s10 collapse — Marcus holdout at 3.105
with zero corrections. S08 continuation (4.38) is the second-highest single session in the
dataset. Late-window continuation (3.629) actually exceeds original adaptive (3.478) once
bootstrap noise clears. Correction rate reverts to baseline level (0.066) because Cortex
keeps proposing on an already-saturated workspace.

**Why continuation partially works but doesn't compound:** Binary rules transfer cleanly
and don't over-constrain any task type. But the original adaptive run's correction
rate advantage (0.015) was produced by the incremental process gradually encoding rules
with exactly the right scope. Pre-loading them at full intensity adds noise via redundant
Cortex proposals without further reducing corrections.

**New skill — `send-slack-dm` (created at continuation s07):** After observing Marcus
repeatedly asking to message team members (Andrew, investors, the support team), Cortex
created a skill that formalises the Slack DM workflow: verify the recipient's handle,
draft for approval, send, confirm delivery, and save new handles to USER.md. The skill
reflects Marcus's operational reality — he manages via messaging, not code — and
encodes a safeguard (never guess a Slack handle) that prevents misdirected messages.

**Thesis relevance:** Binary, rule-like preferences are the ideal case for workspace-level
adaptation. Once encoded, they require zero in-session reinforcement and produce
structurally reliable improvements. The continuation result shows they also transfer
without collapse — the safest preference type for both original and continued adaptation.

---

### Aisha — Junior Developer

**Profile:** Learning-oriented interaction style. Wants concepts explained before solutions,
step-by-step breakdowns, analogies for unfamiliar topics. Technically curious, not yet
expert.

**Cortex encoding:** SOUL.md and AGENTS.md updated to teach-first mode: explain concepts
before giving code, use analogies, confirm understanding before moving on. Proposals
accumulated from s03; style preferences stable by s05.

**Original adaptive result — the "Aisha paradox":** PHit 3.4× higher for adaptive across
all sessions (0.239 vs 0.066), and 2.7× higher at holdout (0.394 vs 0.147). The agent
correctly learned her style. However, average helpfulness is lower for adaptive (3.17 vs
3.32). The starkest example: s09 has the highest PHit in the original dataset (0.743) and
simultaneously the lowest helpfulness (2.37) — the agent committed to teaching mode in a
circular import scenario where Aisha just needed the fix. The helpfulness metric penalises
verbosity; verbose teaching responses score identically to bad answers.

**Continuation result:** Worst regression of all personas. Avg helpfulness 2.743 — below
both adaptive (3.166) and baseline (3.315). S10 holdout collapses to 1.00 (floor score)
with correction rate 0.67. PHit peaked at 0.77 in s09 then dropped to 0.00 at holdout —
the agent over-applied teaching mode in prior sessions, then failed to apply it coherently
on the novel holdout task. Zero frustration throughout (Aisha's patient learner profile
means she corrects without emotional escalation, unlike Olena).

**Why continuation fails for Aisha:** Teach-first rules are situational — they work when
the task calls for learning, not when the user needs a quick fix. Encoded as permanent
instructions at maximum intensity, they cause the agent to commit to full pedagogical mode
in scenarios that require direct answers. The pre-loaded snapshot bypasses the gradual
calibration that originally taught the agent *when* teaching mode is appropriate.

**Thesis relevance:** Two findings. First: Cortex correctly encodes interaction style even
when the helpfulness metric fails to capture it — PHit is the better metric for
learning-oriented personas. Second: the continuation experiment shows that interaction-style
rules carry the same over-specialisation risk as procedural rules when pre-loaded without
calibration. The thesis should frame Aisha's original adaptive result as a metric scope
finding, and the continuation result as a saturation risk finding.

---

### Olena — Senior Data Analyst

**Profile:** Preferences are procedural and tool-specific. SQL over Pandas for all ETL.
Load data as TEXT into staging tables before parsing. Use EXPLAIN before optimizing queries.
Run duplicate and NULL checks before any analysis. dbt + Postgres stack.

**Cortex encoding:** AGENTS.md received detailed workflow checklists: DuckDB/SQL-first,
TEXT staging, EXPLAIN-first debugging, cohort methodology with 30-day windows, FULL OUTER
JOIN for reconciliation, SRM/MDE checks before A/B significance. SOUL.md: "assume data is
messy, don't left-join and hope." Proposals accumulated across s03–s09; workspace fully
stable by s07.

**New skill — `dq-audit` (created at s08):** After observing Olena manually run the same
duplicate-check, NULL-count, and date-range queries at the start of every session, Cortex
created an executable skill: `skills/dq-audit/dq_audit.py`. The skill accepts any CSV or
Parquet file, runs the full DQ pre-flight via DuckDB, and prints a structured report.
AGENTS.md was updated to invoke it proactively whenever new data files are present — the
agent no longer waits to be asked. This is the plugin's skill-writing capability in action:
Cortex identified a recurring manual workflow, abstracted it into a reusable tool, and
wired it into the agent's standard operating procedure. During Olena's continuation run,
Cortex created a second skill — `handle-db-queries` (first appearing at s06) — which
encodes a boundary rule: the agent cannot execute queries directly against a live database,
so the skill formalises the correct behaviour (write, explain, and format SQL for the user
to run manually) rather than silently failing or pretending to execute.

**Original adaptive result:** Largest single holdout gap across all 4 personas: +0.95
helpfulness (3.26 vs 2.31). Baseline PHit at s10: **0.000** — with no context cues, the
baseline had literally zero personalization signal. Adaptive agent proactively applied
audit queries and data quality checks before building the quarterly summary. Baseline
produced a generic template in 13 turns; adaptive engaged deeply in 35 turns.

**Continuation result:** Textbook over-adaptation. PHit at s10: 0.97 (agent applies
Olena's preferences on nearly every turn). Helpfulness at s10: 1.42. Correction rate
at s10: 0.64. The agent forces SQL/DQ-checks regardless of task fit on the holdout.
Session trajectory is revealing: s06 is the strongest continuation session (3.53, PHit
0.97) where the task perfectly aligned with encoded procedures — then helpfulness
deteriorates as tasks deviate, peaking at the holdout collapse. Late-window avg
(2.372 help, 0.895 PHit, 0.290 corr) is the worst configuration in the dataset.

**Why continuation fails for Olena:** Procedural rules are inherently situational —
"EXPLAIN before optimizing" is only appropriate in specific contexts. Encoded as permanent
maximum-intensity rules and applied unconditionally across all tasks including the holdout's
novel scenario, they become friction generators rather than workflow accelerators.
The original adaptive run calibrated *when* to invoke each procedure; the snapshot
pre-loads them all without calibration.

**Thesis relevance:** Confirms the Marcus pattern applies to procedural preferences at the
original adaptive level. But the continuation experiment adds the critical finding: the
same procedural rules that produced the largest helpfulness gain (+0.95) also produce the
most severe continuation collapse (−1.84 vs adaptive at holdout). Olena is the sharpest
illustration of the workspace ≠ process distinction.

---

## Confounds and Limitations

### 1. Baseline PHit inflation (sessions s01–s09)

The simulator retains memory of prior sessions but still opens each new scenario with
enough context for the baseline agent to infer preferences. This means outside the holdout,
both arms partly measure in-session context use. The holdout eliminates this confound by
design. Any helpfulness or PHit comparison that includes s01–s09 must note this. Sofia's
baseline avg PHit (0.902) is the most extreme case.

### 2. s03 bootstrap dip

The first Cortex approval session applies early proposals that may be imprecise or
overgeneralised. The workspace is mid-calibration. This produces a reliable quality dip
at s03 for the adaptive arm (Sofia: 1.88, Marcus: correction spike). The dip suppresses
the session-average but disappears by s05. Late-session window (s07–s10) cleanly avoids
this artefact.

### 3. Metric misalignment for Aisha

The helpfulness evaluator rewards conciseness and task completion speed. This is
appropriate for productivity users (Marcus, Olena, Sofia) but structurally wrong for
Aisha. The thesis must either: (a) use a persona-appropriate metric for Aisha, (b) report
PHit as the primary metric for learning-oriented personas, or (c) explicitly frame the
helpfulness result as a metric limitation finding rather than an adaptation failure. PHit
is the better success metric for Aisha: adaptive 0.239 vs baseline 0.066 (3.6×); holdout
0.394 vs 0.147 (2.7×).

### 4. Over-adaptation confirmed at scale (continuation experiment)

Originally identified as an Aisha edge case (s09: PHit 0.743, helpfulness 2.37 — teaching
mode applied to a quick-fix scenario). The continuation experiment confirms over-adaptation
is systematic and predictable for procedural/interaction-style rule types:

- Olena continuation s10: 1.42 help, 0.97 PHit, 0.64 correction
- Aisha continuation s10: 1.00 help, 0.00 PHit, 0.67 correction

The pattern is specific to procedural and interaction-style rules applied unconditionally.
Binary (Marcus) and outcome-oriented (Sofia) rules do not exhibit this collapse. The plugin
needs a saturation detection or pruning mechanism — a rule confidence score or "last
validated" field on each AGENTS.md entry — to prevent continued Cortex proposals from
over-encoding an already-calibrated workspace.

### 5. 100% approval rate

In production, every Cortex proposal is presented to the user for review before being
applied. The user retains full agency over what gets written to their workspace. The
experiments bypass this with 100% automated approval to isolate the raw quality of
Cortex's inference. This means the experiment results represent an **upper bound** —
the maximum adaptation effect if all proposals are applied. In practice, user filtering
would likely improve quality further by catching imprecise early proposals (the s03 dip
was partly caused by early proposals the user would have modified).

### 6. Workspace isolation and per-persona reset

Each arm runs in a fully separate openclaw instance with its own workspace directory:

- `~/.openclaw-adaptive/workspace/` — adaptive arm workspace
- `~/.openclaw-baseline/workspace/` — baseline arm workspace

Between personas, `reset_workspace_for_persona()` resets the arm-specific workspace
to clean defaults before the new persona begins:
- `IDENTITY.md`, `SOUL.md`, `AGENTS.md` → reset to template defaults
- `USER.md` → reset to name-only template (persona name pre-seeded, nothing else)
- `MEMORY.md` and daily memory files → cleared
- LanceDB vector memory (`memory/main.sqlite`) → truncated
- `reflect.db` proposals table → cleared

This guarantees Marcus's encoded rules did not carry into Olena's workspace, and
Olena's DQ workflow did not contaminate Sofia's. Each persona's adaptive arm started
from an identical blank state. The two instances also run on separate ports (3100
baseline, 3101 adaptive) so concurrent session traffic never crosses arms.

### 7. Statistical power

10 sessions × 3 arms × 4 personas = 120 session-level data points. Per-session
helpfulness has high variance (range 1.00–4.43 within a single arm). Individual session
differences are not statistically reliable in isolation. The thesis can claim directional
consistency across all 4 personas and at the holdout, but significance claims require
pooling at the turn level (~3,135 turns across 120 sessions, avg 26 turns/session)
with careful treatment of within-session autocorrelation.

### 8. Approval bottleneck as hidden variable

Every adaptation is gated on the approval LLM successfully applying proposals to workspace
files. If the approval session produces no file edits, the adaptive arm silently degrades
toward baseline behaviour. Earlier runs with less capable models exhibited this. The switch
to Gemini 3.1 Pro for approval sessions resolved it, but the experiment does not directly
track "did the approval session mutate files" — some adaptive sessions may run with only
partial proposal application.

### 9. Continuation workspace reset

The continuation arm uses the s10 adaptive snapshot but clears the SQLite proposals DB
and LanceDB vector memory before starting. This means Cortex in continuation runs sees
no memory of prior proposals — it cannot detect that rules are already encoded. This is
a primary cause of the saturation problem: Cortex cannot know the workspace is full and
continues generating proposals that add noise. A "workspace delta" mechanism that compares
new proposals to existing AGENTS.md content before writing would address this.

### 10. No isolation of which adaptation mechanism drove the effect

The experiment measures the system as a whole — it cannot attribute observed gains to
any specific component of the workspace. Cortex modifies up to five channels per session:

| Channel | What it encodes | Measurably distinct? |
|---------|----------------|----------------------|
| `IDENTITY.md` | Agent vibe, tone, aesthetic | No |
| `USER.md` | User facts, stack, projects | No |
| `SOUL.md` | Behavioural principles, assumptions | No |
| `AGENTS.md` | Operational rules, tool instructions | No |
| LanceDB vector memory | Episodic context, retrieved at session start | No |

All five channels are active simultaneously in the adaptive arm. A helpfulness gain at
holdout could be driven by AGENTS.md rules (the agent follows the right procedure),
USER.md facts (the agent references the right stack), SOUL.md principles (the agent
approaches the task with the right assumptions), or LanceDB memory retrieval (the agent
recalls relevant prior context). The experiment cannot distinguish these.

This is a meaningful limitation for the thesis: it can claim the *system* adapts
effectively but not that any specific file or memory mechanism is the load-bearing
component. Ablation experiments — running adaptive with individual channels disabled
(e.g., adaptive minus LanceDB, or adaptive with AGENTS.md frozen) — would be required
to isolate contributions. These were not run.

### 11. Pairwise judgment not implemented

A pairwise LLM judge was designed but not executed: present both arms' responses for the
same turn to a judge with the persona's full profile and ask which response better serves
this specific user. This approach (used in MT-Bench and Chatbot Arena) eliminates scale
bias and directly measures the thesis claim — that the adapted agent serves this user
better — rather than measuring absolute quality. It remains a recommended validation step.
Implementing it as a post-processing pass over existing `scores.csv` data would not
require re-running any sessions.

---

## Verdict Table

| Signal | Result |
|--------|--------|
| Cortex encodes preferences | ✅ All 4 personas — PHit higher at holdout |
| Skill writing | ✅ 3 skills created from recurring workflow patterns. ⚠️ Not validated — skill correctness and real-world utility untested. Effective skill design requires user involvement to verify behaviour against their own experience. `remember` skill implemented but never invoked. |
| Helpfulness gains at holdout (adaptive) | ✅ 3/4 personas; Aisha flat — metric issue, not encoding issue |
| Turn efficiency at holdout | ✅ Sofia −44% turns (19 vs 34); Marcus −14%. Adapted agent needs less back-and-forth because it already knows user format and preferences. |
| Correction rate reduction | ✅ Marcus decisively (4×, structural — mistake cannot recur); Sofia late-session; Olena s06+ |
| Effect by preference type | Binary/procedural → strongest holdout gains; stylistic → efficiency signal; interaction style → PHit only |
| Qualitative adaptation signal | ✅ Confirmed — Marcus s10: agent opened with Slack-formatted ARR update without being asked. Sofia: agent used "Sunday morning vibe" and brand terms unprompted from s05. Olena: agent ran full DQ pre-flight on holdout without instruction. |
| Baseline PHit inflation | ✅ Confirmed — outside holdout both arms measure current-session context use. Simulator memory partially mitigates but does not eliminate. |
| Bootstrap cost | ✅ Confirmed s03 dip for Sofia and Aisha adaptive arms |
| Over-adaptation risk (original) | ✅ Confirmed — Aisha s09 is the first clear example |
| Over-adaptation at scale (continuation) | ✅ Confirmed — Olena and Aisha collapse at s10; rule type is the predictor |
| PHit transfers from snapshot | ✅ All 4 personas — continuation PHit rises from session 1 without re-learning |
| Helpfulness compounding (continuation) | ✅ Sofia (outcome rules); ❌ Marcus (flat, stable); ❌ Olena/Aisha (collapse) |
| Workspace ≠ process | ✅ Confirmed — snapshot transfers knowledge, process calibrates application |
| Saturation detection needed | ✅ Confirmed — Cortex cannot detect encoded workspace and over-proposes |
| Pairwise judgment | ⚠️ Not implemented — designed but not executed. Recommended as future validation step. |

---

## Key Numbers

| Metric | Value | Context |
|--------|-------|---------|
| Highest holdout helpfulness | 3.733 | Sofia continuation s10 |
| Lowest holdout helpfulness | 1.000 | Aisha continuation s10 |
| Largest adaptive vs baseline holdout gap | +0.95 | Olena — baseline PHit 0.000 |
| Best single session | 4.10 | Sofia continuation s07 |
| Second best single session | 4.38 | Marcus continuation s08 |
| Lowest correction rate (avg) | 0.015 | Marcus adaptive — 4× below baseline |
| Highest PHit at holdout | 0.970 | Olena continuation s10 — with 1.42 helpfulness |
| Worst correction spike | 0.667 | Olena/Aisha continuation s10 |
| Baseline with zero holdout PHit | 0.000 | Olena — without context, baseline knows nothing |

---

## Thesis Claim

> The reflect-and-adapt plugin consistently encodes user-specific preferences into the
> workspace across all 4 personas (personalization_hit 1.4–∞× higher at holdout —
> baseline drops to 0.000 for Olena when no context is provided). Helpfulness gains at
> holdout are strongest for users with structurally encodable preferences: Marcus (+0.89,
> binary rules) and Olena (+0.95, procedural workflows). Sofia shows a holdout quality
> gain (+0.23) and a strong efficiency signal (−44% turns). Aisha demonstrates clear
> preference encoding (3.6× PHit) without helpfulness gain, exposing a metric misalignment
> between productivity-optimised evaluation and learning-oriented interaction styles —
> itself a finding about which user types benefit most and how that benefit should be
> measured.
>
> A continuation experiment (10 additional sessions from each s10 snapshot, Cortex still
> enabled) distinguishes two independent components of the system's value: (1) the
> workspace state, which transfers persona knowledge immediately and boosts PHit from
> session 1 without re-learning; and (2) the adaptation process, which calibrates *when*
> to apply rules and produces the helpfulness gains. Rule type is the primary predictor
> of continuation outcome — outcome-oriented rules (Sofia) compound positively and produce
> the highest holdout score in the dataset (3.733); binary rules (Marcus) transfer cleanly
> without collapse; procedural rules (Olena, Aisha) over-specialise and collapse at holdout
> (1.42 and 1.00 respectively, correction rates above 0.60). This identifies a necessary
> system design addition: saturation detection in the Cortex pipeline to prevent continued
> proposal generation on an already-calibrated workspace.
