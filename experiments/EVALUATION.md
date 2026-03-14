# Evaluation Framework — Reflect & Adapt Plugin

## Overview

This document describes the evaluation strategy for the **reflect-and-adapt** openclaw plugin,
developed as part of the thesis *Adaptive AI Agent: Structural and Behavioral Adaptation Driven
by User Interaction*.

The goal is to empirically demonstrate that the plugin causes Claude Code to adapt to individual
users over time — producing measurably better responses without the user having to repeat their
preferences in every session.

---

## Experiment Design

### Two-Arm Longitudinal

Each persona is run simultaneously on two identical openclaw instances:

```
Control arm   (plugin OFF):  [S1][S2][S3]...[S9][S10-holdout]
                                                                →  compare score trajectories
Treatment arm (plugin ON):   [S1][S2][S3][A][S4][A][S5][A]...[S9][A][S10-holdout]

  [SN] = scenario session (scored)
  [A]  = approval session (unscored) — agent applies pending proposals via manage-proposals.js
```

**S1–S9** — unique but thematically related scenarios. Each generates consistent correction
and frustration signals rooted in the persona's stable preferences. Cortex accumulates
evidence across sessions and begins proposing adaptations after session 3–4.

**S10** — fixed holdout scenario, identical in both arms. No workspace files provided.
The treatment agent must rely on what it has learned; the control agent starts from zero.
This is the primary point comparison between arms.

### Why Not Same Scenario Repeated

Repeating the same scenario tests scenario-specific memorisation, not user-level adaptation.
The plugin learns WHO the user is — preferences that generalise across all tasks. Varied
scenarios produce higher-confidence findings in the analyst stage (the same correction
appearing across different contexts = strong signal) and better reflect real-world usage.

---

## Session Structure

```
Per persona × arm:

  Session N
  ─────────
  1. Harness copies scenario workspace_files → ~/.openclaw/workspace/data/
  2. If scenario has setup_script: run it → generates DB / git repo / log files
  3. before_agent_start hook fires (plugin injects pending proposals if treatment arm)
  4. User simulator sends opening_prompt
  5. Multi-turn conversation (max_turns from scenario config)
     └─ before_prompt_build fires each turn (plugin injects relevant memories)
  6. User signals: corrections, frustrations, clarifications (from signals_to_express)
  7. Session ends → agent_end hook fires
     ├─ evaluator.js scores the last turns → writes to scores table
     └─ Cortex pipeline fires (cooldown = 0 for experiments)
         analyst → router → writers → proposals saved / memories written
  8. [Treatment only] harness waits ~45s for Cortex to complete
  9. [Treatment, session ≥ 4] harness runs an approval session (see below)
```

### Approval Session

After each session where PENDING proposals may exist (session ≥ `auto_approve_after_session`,
default 4), the harness runs a short dedicated openclaw session with a fixed prompt before
starting the next scenario session:

```
APPROVAL_PROMPT = """
Please check for any pending proposals using the proposals skill and apply all of them.
For each proposal: show it, apply the change to the file, then mark it as approved.
"""
```

The agent handles this through the existing `manage-proposals.js` skill — it lists proposals,
applies each `proposed_change` to the target file, and marks them approved. This keeps the
full proposal workflow intact: file changes are made by the agent, not by the harness.

```
Timeline for treatment arm sessions 3–5 (example):

  [S3 scenario session]
      └─ agent_end → Cortex fires → proposals generated (PENDING)
  [45s wait]
  [Approval session]
      └─ agent lists proposals → applies changes → marks APPROVED
  [S4 scenario session]
      └─ agent now runs with adapted SOUL.md / USER.md / new skills
  [45s wait]
  [Approval session]  ← runs after every session from here on
  [S5 scenario session]
  ...
```

The approval session itself is not scored — it is excluded from metric collection.
It has no scenario context, no workspace files copied, and the user simulator is not used.
The harness simply sends the fixed prompt and waits for the session to end.

---

## Mock Data Flow

```
experiments/scenarios/<persona>/<scenario>/
    ├── scenario.yaml          # config: prompt, files, signals, expected adaptations
    ├── [data files]           # CSV, JSON, SQL, log files, code files
    └── setup.py (optional)    # generates dynamic artifacts (DB, git repo, logs)
                │
                ▼
harness copies/runs → ~/.openclaw/workspace/data/
                │
                ▼
openclaw reads files with Read / Bash tools (normal agent tools)
                │
                ▼
user simulator reacts to what the agent says about the data
```

**Static files** (CSV, JSON, code): copied directly before each session.
**setup.py scripts**: run with `--target <workspace_data_dir>` before copying; produce
SQLite databases, git repositories with specific states, or log files. Ensures
reproducible workspace state every run.

The user simulator's `opening_prompt` references the files naturally, as a real user would:
*"I exported the data — it's in the data folder"* rather than pasting contents inline.

---

## Metrics

Scores come from `evaluator.js`, which runs after every session and writes to `reflect.db`.

| Metric | Type | Direction |
|--------|------|-----------|
| `helpfulness` | 1–5 scale | ↑ higher is better |
| `conciseness` | 1–5 scale | ↑ higher is better |
| `correction_signal` | boolean | ↓ lower is better |
| `frustration_signal` | boolean | ↓ lower is better |
| `task_completed` | boolean | ↑ higher is better |
| `user_satisfaction` | positive/neutral/negative | positive ↑ |

**Primary analysis**: plot metric trajectory across sessions 1–9 per arm per persona.
Treatment arm should show improving helpfulness and declining correction/frustration rates.
Control arm should remain flat (no adaptation signal).

**Secondary analysis**: compare S10 holdout scores between arms. The treatment agent
has learned the user's context; the control agent has not. Holdout score gap is the
clearest single-number evidence of adaptation effectiveness.

**What to look for in proposals**: `cortex_runs/*.json` logs show what the analyst
extracted, what the router accepted, and what proposals were generated. Track:
- Sessions until first proposal generated
- Types of proposals (SOUL.md, USER.md, skills)
- Whether proposals match `expected_adaptations` in scenario.yaml

---

## Current Personas

| Persona | Type | Key signals generated | Holdout scenario |
|---------|------|-----------------------|------------------|
| **Marcus** (non-technical SaaS founder) | Business/management | No-code preference, plain language, delegate to dev | Board meeting prep |
| **Aisha** (junior Python dev) | Technical/learning | "Why does this work?", step-by-step, venv reminder | Code review |
| **Elena** (senior data analyst) | Technical/expert | SQL-first, no hand-holding, state assumptions | Q1 SQL summary |

---

## Next Personas

### Candidate 1 — Raj, DevOps/SRE Engineer

**Profile**: 8 years Linux/infrastructure. Runs everything in the terminal. Reads man pages
for fun. Gets actively annoyed when the AI adds explanations he didn't ask for or gives
GUI-based instructions. Expects exact commands with correct flags on first try.

**Contrast with existing personas**: opposite of Marcus (CLI-native, not GUI-first);
opposite of Aisha (expert, hates explanations).

**Consistent signals to generate**:
- Corrects wrong flags immediately: "that's `-p` not `--port` for this context"
- Pushes back on narrative responses: "I didn't ask for an explanation, just the command"
- Corrects wrong distro assumptions: "I'm on Alpine, not Ubuntu — different package manager"
- Gets frustrated when agent adds `sudo` unnecessarily or misses it when required

**Scenario ideas and mock data**:

| Session | Scenario | Mock data type |
|---------|----------|----------------|
| S1 | Diagnose a high-load nginx server | `setup.py` → generates realistic `/var/log/nginx/error.log` + `access.log` with spike patterns |
| S2 | Write a systemd unit file for a Go service | Static: broken `.service` file that fails to start |
| S3 | Debug a Docker network connectivity issue | Static: `docker inspect` JSON output + `docker logs` for two containers |
| S4 | Set up log rotation for an application | Static: current `/etc/logrotate.d/` config with a bug |
| S5 | Investigate a disk space issue | `setup.py` → generates `df -h` output + `du` tree showing large unexpected directories |
| S6 | Write a bash script to rotate backups | Static: existing broken backup script |
| S7 | Kubernetes pod keeps OOMKilling | Static: `kubectl describe pod` output + resource limits config |
| S8 | Secure a PostgreSQL installation | Static: `pg_hba.conf` + current `postgresql.conf` |
| S9 | Set up a basic prometheus alert rule | Static: existing `alerts.yml` + sample metrics output |
| S10 (holdout) | Write a runbook for a service restart procedure | No files — agent should know Raj's distro, tools, prefers terse format |

**Expected adaptations**:
- `USER.md`: Alpine Linux, uses Docker/K8s, Go services, prefers `podman` over Docker
- `SOUL.md`: commands only unless asked, correct flags first time, no sudo unless necessary

---

### Candidate 2 — Sofia, Freelance Content Creator

**Profile**: 29 years old. Makes YouTube videos and digital art. Non-developer — uses
Canva, Notion, CapCut, and Adobe Express. Thinks visually and iterates constantly.
Describes ideas in plain language and gets frustrated with technical jargon.
Very different from Marcus: her tasks are creative, not operational.

**Contrast with existing personas**: non-technical like Marcus but creative domain
rather than business; iterative like Aisha but through creative feedback not learning.

**Consistent signals to generate**:
- Corrects tone when it sounds too corporate: "this is too formal, I want it to sound like me"
- Pushes back on technical output: "I can't use code, I need something I can do in Canva"
- Iterates on creative output: "what if the colours were warmer?", "try a different angle"
- Gets frustrated when AI forgets her visual style from earlier in the conversation

**Scenario ideas and mock data**:

| Session | Scenario | Mock data type |
|---------|----------|----------------|
| S1 | Write a YouTube video script on a given topic | Static: `video_brief.md` — topic, target audience, desired length, her usual structure |
| S2 | Create a content calendar for the next month | Static: `past_calendar.csv` — her previous month's schedule showing patterns |
| S3 | Generate thumbnail concepts for a video | **Image** (user adds): screenshot of her channel showing current thumbnail style |
| S4 | Write SEO-optimised video descriptions | Static: `channel_stats.json` — top performing videos with their descriptions |
| S5 | Repurpose a YouTube video into an Instagram carousel | Static: `video_transcript.txt` — transcript of a 10-min video |
| S6 | Brainstorm a new series concept | Static: `audience_feedback.csv` — comments export with themes |
| S7 | Write email newsletter from a video | Static: existing `newsletter_example.md` — her previous newsletter style |
| S8 | Create a media kit for brand partnerships | Static: `channel_metrics.json` — views, subscribers, demographics |
| S9 | Generate image prompts for a video thumbnail | **Image** (user adds): her face reference photo + `brand_palette.md` |
| S10 (holdout) | Plan a collaboration video with another creator | No files — agent should know her niche, style, tools |

**Expected adaptations**:
- `USER.md`: YouTube + Instagram creator, uses Canva/CapCut/Adobe Express, specific niche
- `SOUL.md`: conversational tone, creative and iterative responses, no technical output
- Possible skill: `generate-content-brief` — recurring task she does for every video

---

### Candidate 3 — Dr. Amara Diallo, Academic Researcher

**Profile**: 36 years old. Postdoc in computational social science. Python and R user.
Extremely precise about methodology — she will correct the AI if it makes an unsupported
claim or uses the wrong statistical test. Wants citations or explicit uncertainty acknowledgment.
Uses LaTeX, Jupyter notebooks, and Zotero.

**Contrast with existing personas**: technical like Elena but in a different domain;
methodologically rigorous in a different way (scientific validity vs data engineering).

**Consistent signals to generate**:
- Pushes back on unsupported claims: "can you cite that or caveat it as uncertain?"
- Corrects statistical errors: "that's not what p-value means in this context"
- Asks for R alternatives when given Python: "is there a cleaner way to do this in R?"
- Gets frustrated when the AI is confidently wrong about her domain

**Scenario ideas and mock data**:

| Session | Scenario | Mock data type |
|---------|----------|----------------|
| S1 | Clean and analyse a survey dataset | `setup.py` → generates survey responses CSV with realistic missing data patterns |
| S2 | Choose the right regression model | Static: `dataset_description.md` + `correlation_matrix.csv` |
| S3 | Write the methods section of a paper | Static: `analysis_notes.md` — what she did, needs academic prose |
| S4 | Debug a failing R script | Static: `analysis.R` with a subtle `dplyr` pipe bug + error output |
| S5 | Visualise longitudinal data | `setup.py` → generates panel dataset CSV (subjects × time periods) |
| S6 | Interpret a peer reviewer's statistical comment | Static: `reviewer_comment.md` — a reviewer asking about measurement invariance |
| S7 | Export a Jupyter notebook to a clean PDF | Static: `notebook_issues.md` — her current LaTeX/nbconvert setup and what fails |
| S8 | Calculate sample size for a planned study | Static: `study_design.md` — her planned experiment parameters |
| S9 | Manage references for a paper submission | Static: `bibliography.bib` — messy .bib file with duplicates and formatting errors |
| S10 (holdout) | Draft a response to peer review comments | No files — agent should know her field, statistical tools, citation expectations |

**Expected adaptations**:
- `USER.md`: computational social science, Python + R, LaTeX, Zotero, postdoc
- `SOUL.md`: always caveat uncertain claims, cite sources or say explicitly if unavailable,
  offer R alternatives alongside Python, match academic register

---

## Implementation Notes

### Plugin configuration for experiments
```env
# reflect-and-adapt/.env
CORTEX_COOLDOWN_HOURS=0        # fire Cortex after every session
GOOGLE_MODEL=gemini-2.5-pro    # adjust to available model
```

### Harness approval session (pseudocode)
```python
APPROVAL_PROMPT = (
    "Please check for any pending proposals using the proposals skill "
    "and apply all of them. For each: show it, apply the change, mark approved."
)

async def run_approval_session(client: OpenClawClient):
    session_key = await client.new_session()
    await client.send_message(session_key, APPROVAL_PROMPT)
    # no scoring, no simulator — just wait for session to end
```

### Running two openclaw instances
Control and treatment require separate workspace directories and gateway ports.
If openclaw supports `--config` or `OPENCLAW_CONFIG` env var, use separate config files.
Otherwise run sequentially: control arm first (plugin removed from workspace), then
treatment arm (plugin present, clean DB state).

### State reset between personas
After completing all sessions for one persona, reset treatment workspace state:
```bash
cd ~/.openclaw/workspace-treatment/.openclaw/extensions/reflect-and-adapt
rm -f reflect.db reflect.db-shm reflect.db-wal
rm -rf memory.lance cortex_runs
# restore original instruction files from template backup
cp ~/.openclaw/workspace-template/SOUL.md ~/.openclaw/workspace-treatment/SOUL.md
cp ~/.openclaw/workspace-template/USER.md ~/.openclaw/workspace-treatment/USER.md
# ... other instruction files
```

### Parallel vs sequential arms
Running both arms in parallel (two openclaw instances, separate ports) is preferred —
eliminates time-of-day effects and ensures both arms face the same base model version.
Running sequentially is acceptable if parallel setup is not feasible; just note this
as a limitation in the thesis.
