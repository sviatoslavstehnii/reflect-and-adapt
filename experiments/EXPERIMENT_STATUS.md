# Experiment Status — Reflect & Adapt Plugin

**Thesis:** *Adaptive AI Agent: Structural and Behavioral Adaptation Driven by User Interaction*
**Last updated:** 2026-03-16

---

## What Is Being Tested

Two-arm longitudinal experiment measuring whether the reflect-and-adapt plugin improves agent
helpfulness over repeated sessions with the same user.

| Arm | Description | Cortex | Port |
|-----|-------------|--------|------|
| **baseline** | No adaptation — agent behavior stays static | Disabled (cooldown=999h) | 3100 |
| **adaptive** | Full pipeline — Cortex runs after each session, proposals applied to workspace | Runs after every session | 3101 |

**4 personas × 10 scenarios × 2 arms = 80 sessions total**

Personas: `sofia` (content creator), `marcus` (SaaS founder), `aisha` (junior dev), `elena` (data analyst)

---

## What Is Working

### Experiment Harness
- [x] WebSocket client connects to both gateways, sends messages, waits for agent turn completion
- [x] User simulator (Azure GPT-4.1) generates realistic persona-specific feedback across 6–12 turns
- [x] Session key format: `agent:main:exp-{persona}-{arm4}-{scenario}-{uuid8}`
- [x] Each scenario gets a unique UUID-suffixed session key → fresh conversation, no prior turn history bleeds across scenarios (simulates sessions days apart)
- [x] DB snapshot + NOT IN subquery correctly isolates per-turn agent responses (prevents stale-response bug)
- [x] Loop detection: simulator signals `<TASK_COMPLETE>` or repeats → session ends cleanly
- [x] Both arms run concurrently per persona (parallel asyncio tasks)
- [x] Per-scenario data files (CSV, images, code) are copied to `data/` before each session

### Adaptation Pipeline (adaptive arm only)
- [x] **Cortex runs directly** via `node src/cortex.js` after each session — no cooldown dependency
- [x] **Analyst** (Gemini Flash, 8k tokens) extracts findings from conversations + scores
- [x] **Router** deduplicates against existing pending/approved proposals
- [x] **Writers** generate proposals for `IDENTITY.md`, `USER.md`, `AGENTS.md`, `SOUL.md`, new skills
- [x] **Proposals saved** to `reflect.db` as PENDING
- [x] **Approval session** sends proposals with full current file contents to agent (gemini-3-pro for actual file edits)
- [x] Agent edits workspace files directly — confirmed working: `IDENTITY.md`, `AGENTS.md`, `USER.md` all modified

### Workspace Isolation (Fix 1 — complete)
- [x] `~/.openclaw-adaptive/openclaw.json` sets `"workspace": "/home/sviatoslav/.openclaw-adaptive/workspace"`
- [x] `~/.openclaw-baseline/openclaw.json` sets `"workspace": "/home/sviatoslav/.openclaw-baseline/workspace"`
- [x] `setup_workspaces.sh` patches `agents.defaults.workspace` in each arm's `openclaw.json` after copying; also sets `plugins.load.paths` to shared plugin source (`~/.openclaw/workspace/.openclaw/extensions`)
- [x] Each arm's adaptations are fully isolated — baseline workspace never receives Cortex changes

### Workspace Reset (Fix 3 — complete)
- [x] `reset_workspace_for_persona(persona_id, openclaw_dir)` uses the arm-specific workspace path
- [x] Resets `IDENTITY.md`, `SOUL.md`, `AGENTS.md` to clean defaults
- [x] `USER.md` set to persona-specific template (name only — agent learns the rest)
- [x] `MEMORY.md` and daily memory files cleared
- [x] Vector memory DB (`<openclaw_dir>/memory/main.sqlite`) truncated — uses arm-specific path
- [x] `_build_approval_prompt()` reads current file contents from arm-specific workspace

### Evaluation Metrics
- [x] Per-turn: `helpfulness`, `conciseness`, `task_completed`, `response_accepted`, `format_match`
- [x] Per-turn: `correction_signal`, `frustration_signal` — friction indicators
- [x] Per-turn: `user_satisfaction` (positive/neutral/negative)
- [x] **NEW** Per-turn: `personalization_hit` — True when agent uses user-specific knowledge unprompted (direct adaptation signal; should be near 0% for baseline, rising for adaptive)
- [x] Scores saved to `reflect.db` under experiment session IDs
- [x] `collect.py` produces `scores.csv` (raw turns) **and** `sessions.csv` (session-level aggregates)
- [x] Session aggregates: `satisfaction_score`, `correction_rate`, `frustration_rate`, `turns_per_session`, `personalization_hit` rate
- [x] `plot.py` generates 6 charts: helpfulness, satisfaction, friction, turns-per-session, personalization hit rate, metrics summary

### Run 1 — sofia adaptive only, s01–s03 (earlier partial run)
- Helpfulness trend: **3.48 → 3.68 → 3.86** (steady increase across sessions)
- Confirmed adaptation signal: agent referenced "Cosy Spring pivot" and Sofia's posting cadence in s03 without being told
- Proposals applied: vibe, content format, user profile

### Run 2 — sofia adaptive only, s01–s06 (2026-03-16, complete) ✅

**Command:** `python run_experiment.py --personas sofia --arms adaptive --max-scenarios 6`
**Model:** `google/gemini-3-pro-preview` (agent + approval), Azure GPT-4.1 (user simulator)
**Total turns:** 38 across 6 sessions
**Avg helpfulness:** 2.94/5 (single-arm, no baseline comparison yet)

#### Proposals — 11 generated, 11 approved (100%)

All proposals were applied in the same run via the approval session. No rejections or stale proposals.

| Session | File | Change |
|---------|------|--------|
| s01 | — | No proposals (Cortex skipped — approval only kicks in from s03) |
| s02 | — | Cortex ran, no new proposals (router deduplication) |
| s03 | `USER.md` | Added profession: Content Creator, videos about workflow and AI tools |
| s03 | `IDENTITY.md` | Vibe set to "Cosy, Sunday morning conversational tone, like chatting with a friend" |
| s03 | `AGENTS.md` | Scriptwriting rule: integrate natural pauses and sensory B-roll cues (*coffee steaming*, *scribbles*, *sunlight*) |
| s03 | `SOUL.md` | Vibe rule: lean into story-driven narrative; avoid listicle or bulleted style |
| s04 | `USER.md` | Brand aesthetic: Cozy, earthy, and warm-toned; platform: YouTube; content format: short-form video |
| s04 | `IDENTITY.md` | Vibe refined: "Bright, warm, cozy Sunday morning with gentle shadows; avoids dark/high-contrast/moody tones" |
| s04 | `AGENTS.md` | Design tool rule: prioritize Canva-compatible instructions for thumbnail/visual work |
| s04 | `SOUL.md` | Boundary added: check reference files for brand constraints before suggesting new designs |
| s05 | — | No new proposals (router correctly saw all files already adapted) |
| s05 | `USER.md` | Platform + content format confirmed |
| s05 | `IDENTITY.md` | Vibe locked: "Cozy Sunday morning; warm and conversational, avoiding corporate or YouTube Guru tones" |
| s05 | `AGENTS.md` | Video description rule: 150–300 words, max 3–5 hashtags |
| s06 | — | No new proposals (workspace fully adapted, router had nothing to route) |

**Vector memory entries:** 2 entries written to `memory.lance`
- `[preference]` User creates moodboards for clients and prefers specific, relatable anecdotes in content
- `[context]` Sofia Reyes developing CapCut AI video; needs thumbnail concepts based on reference images

**File evolution by session:**
- `s01` → initial state (all files at template defaults)
- `s02` → no changes (Cortex ran but 0 proposals)
- `s03` → IDENTITY.md, USER.md, AGENTS.md, SOUL.md all updated
- `s04` → IDENTITY.md, USER.md, AGENTS.md refined further
- `s05` → no changes (router deduped everything)
- `s06` → no changes (workspace fully stable)

**Key qualitative observation:** By s05–s06 the agent spontaneously used language like "Sunday morning vibe", referenced "Behind the Canvas" as a series concept, and suggested cozy/earthy aesthetics — without being prompted. The workspace had absorbed Sofia's brand identity structurally.

#### Bugs fixed during/after this run
- `collect.py` was reading from `~/.openclaw` (shared) instead of each arm's isolated DB → stale data from previous partial runs appeared in sessions.csv, causing plots to show only 4 scenarios. Fixed: now reads from `arm_cfg["openclaw_dir"]` per arm.
- `src/cortex.js` in arm-specific copy was missing `latestSessionId` lookup → memory entries had `source_session: "unknown"`. Fixed: `reset_workspace_for_persona` now syncs `src/` from shared source before each run.

---

## Known Issues / Blockers

- **Baseline arm has 0 data** — has never been run. Both gateways need to be running and `--arms baseline` passed to `run_experiment.py`. Once baseline data exists, adaptive vs baseline comparison charts will populate.
- **Both gateways must be running** before `run_experiment.py` is invoked — they are not auto-started by the harness.
- **Approval session after s01/s02** — Cortex skips approval for the first two sessions (`approval_after_session_index: 2` in `experiment.yaml`). This means s01 and s02 snapshots always show the initial template state. First adaptations appear in s03 snapshot.

---

## Checklist to Run Full Experiment on 1 Persona (e.g. sofia)

### Prerequisites (one-time, before starting)

- [x] **gemini-3-pro-preview** set as primary model in `~/.openclaw-adaptive/openclaw.json` — needed for approval sessions to edit files correctly (flash model wraps response without using tools)
- [ ] Re-run `setup_workspaces.sh --reset` to rebuild both arm dirs with correct workspace paths
  ```bash
  bash experiments/setup_workspaces.sh --reset
  ```
- [ ] Copy auth profiles to both arms (needed for API access):
  ```bash
  cp ~/.openclaw/agents/main/agent/auth-profiles.json ~/.openclaw-adaptive/agents/main/agent/auth-profiles.json
  cp ~/.openclaw/agents/main/agent/auth-profiles.json ~/.openclaw-baseline/agents/main/agent/auth-profiles.json
  ```
- [ ] Copy plugin to baseline arm workspace (needed for evaluator + score collection):
  ```bash
  cp -r ~/.openclaw/workspace/.openclaw/extensions/reflect-and-adapt \
        ~/.openclaw-baseline/workspace/.openclaw/extensions/reflect-and-adapt
  ```

### Start Both Gateways (two terminals)

```bash
# Terminal 1
openclaw --profile baseline gateway --port 3100 --allow-unconfigured

# Terminal 2
openclaw --profile adaptive gateway --port 3101 --allow-unconfigured
```

### Run Experiment

```bash
cd /home/sviatoslav/.openclaw/workspace/.openclaw/extensions/reflect-and-adapt/experiments
source venv/bin/activate
python run_experiment.py --personas sofia --arms baseline adaptive
# or limit to N scenarios for a partial run:
python run_experiment.py --personas sofia --arms adaptive --max-scenarios 6
```

Expected: ~20 sessions (10 baseline + 10 adaptive), each 6–12 turns. After each adaptive session, Cortex runs and an approval session edits the workspace files.

### Generate Results

```bash
python analysis/collect.py
python analysis/plot.py
```

Charts saved to `results/plots/`. Key charts:
- `helpfulness_over_sessions.png` — adaptive rising, baseline flat
- `friction_over_sessions.png` — correction + frustration rates falling for adaptive
- `personalization_hit_rate.png` — adaptive arm rising, baseline near 0%
- `turns_per_session.png` — fewer turns needed over time for adaptive
- `metrics_summary.png` — all metrics comparison in holdout sessions (s08–s10)

---

## What the Results Should Show (Hypothesis)

If the plugin works:
1. **Adaptive arm helpfulness increases over s01→s10** while baseline stays flat
2. **Personalization hit rate rises** for adaptive after s03 (Cortex has enough signal), stays ~0% for baseline
3. **Correction and frustration rates fall** for adaptive (fewer mismatches), stable for baseline
4. **Turns per session decreases** for adaptive (agent gets things right faster)
5. **Holdout sessions (s08–s10) show largest gap** — agent has had 7 sessions to adapt
6. **Qualitative**: adaptive agent references user preferences, uses correct formats, avoids friction unprompted

If the plugin doesn't help (null result):
- Both arms trend similarly → adaptation adds no measurable benefit over base model's in-context learning
- Still a valid thesis finding: structural adaptation vs in-context memory may not differ at this scale

---

## Additional Tests Worth Running

| Test | What It Shows |
|------|---------------|
| Compare proposal quality across personas | Does Cortex generate more/better proposals for some user types? |
| Check which proposals get applied vs rejected | What types of adaptations survive the approval step? |
| Re-run adaptive arm with proposals NOT applied | Isolates Cortex analysis benefit from file-change benefit |
| Run all 4 personas after 1-persona results confirmed | Full 80-session dataset for thesis |
