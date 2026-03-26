# reflect-and-adapt

An [OpenClaw](https://openclaw.ai) plugin that makes your AI assistant smarter over time. It silently observes every conversation, evaluates interaction quality, and runs a background meta-agent (Cortex) that proposes concrete improvements to your workspace — updating behavioral guidelines, building a user profile, creating new skills, and storing episodic memories for future retrieval.

---

## What it does

After each session ends, the plugin:

1. **Logs** every user and assistant message to a local SQLite database.
2. **Evaluates** each conversation turn with an LLM-as-judge (helpfulness, conciseness, frustration signals, correction signals, etc.) and submits scores to LangSmith for monitoring.
3. **Runs the Cortex pipeline** (at most once per hour, configurable) — a three-stage multi-agent system that reads recent conversations and session quality scores, extracts patterns, and either proposes file changes or commits episodic memories.
4. **Presents proposals** at the start of the next session, asking you to approve or reject each one.
5. **Retrieves memories** before every message — semantically searches the vector store for relevant past context and quietly prepends it to the assistant's context.

You can also trigger adaptation on demand or save memories mid-session — see [On-demand commands](#on-demand-commands) and [Skills](#skills).

### What gets adapted

| Target | What changes | Mechanism |
|---|---|---|
| `SOUL.md` | Behavioral rules (e.g. "stop doing X") | Proposal, user-approved |
| `USER.md` | Core facts (name, profession, location) | Proposal, user-approved |
| `AGENTS.md` | Workflow conventions | Proposal, user-approved |
| `HEARTBEAT.md` | Periodic tasks to automate | Proposal, user-approved |
| `IDENTITY.md` | Persona (name, vibe) | Proposal, user-approved |
| `skills/*/SKILL.md` | New reusable capabilities | Proposal, user-approved |
| `memory.lance/` | Episodic facts, preferences, examples | Auto-committed, no approval needed |

---

## Architecture

```
index.js
├── before_agent_start   → injects pending proposals into session context
├── before_prompt_build  → semantic memory retrieval, prepends [RELEVANT MEMORY] block
├── agent_end            → logs messages, fires evaluator + Cortex in background
└── command:adapt        → runs Cortex immediately on /adapt, bypassing cooldown

src/
├── db.js               SQLite (better-sqlite3), WAL mode
│                       Tables: conversations, scores, proposals, state
├── evaluator.js        LLM-as-judge per turn → scores table + LangSmith feedback
├── analyst.js          Stage 1: extracts typed findings from conversations + scores
├── router.js           Stage 2: rules-based routing, evidence thresholds, dedup suppression
├── writers.js          Stage 3: specialized LLM writer per file type (parallel)
├── memory.js           LanceDB vector store + Google Gemini embeddings
├── memory-writer.js    Extracts memory entries, LLM dedup check, auto-commits
│                       Also exports ingestMemory() for direct mid-session ingestion
└── cortex.js           Pipeline orchestrator: analyst → router → writers + memory → save

skills/
├── install.sh          One-shot installer: npm install + .env + skills symlinks
├── proposals/
│   ├── SKILL.md            Teaches the assistant how to review/approve/reject proposals
│   └── manage-proposals.js CLI for listing, showing, approving, and rejecting proposals
└── remember/
    ├── SKILL.md            Teaches the assistant to save observations to memory mid-session
    └── ingest-memory.js    CLI: reformulate → dedup → insert into LanceDB
```

### Cortex pipeline in detail

```
agent_end
    │
    ├─ evaluateTurn()  ──────────────────────────────────────────► scores table
    │                                                               LangSmith feedback
    │
    └─ runCortexCycle()  (if cooldown elapsed)
           │
           ├─ Stage 1: Analyst  [gemini-3-flash-preview]
           │     structured output, reads last 40 turns + session health
           │     worst sessions analysed first
           │     extracts typed findings:
           │       correction, user_fact, missing_capability, workflow_convention,
           │       persona_preference, periodic_task, frustration_pattern, memory_entry
           │
           ├─ Stage 2: Router  [no LLM]
           │     enforces evidence thresholds (1–2+ occurrences per type)
           │     suppresses re-proposals via word overlap vs. REJECTED history
           │     routes memory_entry findings to memory writer (bypasses proposals)
           │
           └─ Stage 3: Writers (parallel)
                 ├─ File proposals  [gemini-3-pro-preview]
                 │     file-specific prompts, reads current file content
                 │     skip=true if finding already covered
                 │     → saved to proposals table as PENDING
                 │
                 └─ Memory entries  [gemini-3-flash-preview]
                       extracts self-contained factual sentence
                       cosine search in LanceDB (threshold 0.82)
                       LLM dedup check if similar entries found
                       → inserted into LanceDB (auto-committed)
```

### Memory retrieval

```
User sends message
       │
       ▼
before_prompt_build hook fires
       │
       ├─ embed user message  [gemini-embedding-001, 3072 dims]
       ├─ cosine search in LanceDB (threshold 0.60, top 5)
       │
       ├─ if matches found:
       │     prepend [RELEVANT MEMORY] block to context
       │
       └─ LLM sees memory + user message → context-aware response
```

### Proposal lifecycle

```
PENDING → PRESENTED → APPROVED  (apply change to file)
                    → REJECTED   (stored with reason, suppresses similar future proposals)

PRESENTED proposals auto-revert to PENDING after 48 hours if no decision is made.
```

---

## Requirements

- [OpenClaw](https://openclaw.ai) gateway running
- Node.js ≥ 18 (same version as the OpenClaw gateway — see [Node version note](#node-version-alignment))
- Google AI API key — get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey)
- LangSmith account (optional — for quality monitoring dashboards)

---

## Setup

### 1. Clone the plugin

Place the plugin inside your OpenClaw extensions directory:

```bash
cd ~/.openclaw/workspace/.openclaw/extensions
git clone <repo-url> reflect-and-adapt
cd reflect-and-adapt
```

### 2. Run the installer

```bash
bash skills/install.sh
```

This does three things:
- Runs `npm install` (installs all dependencies)
- Creates `.env` from `.env.example` if it doesn't exist
- Symlinks `skills/proposals/` and `skills/remember/` into your workspace `skills/` directory so the assistant can use them

### 3. Configure your API key

Edit `.env` in the plugin directory:

```bash
nano .env
```

```env
# Google AI (required) — https://aistudio.google.com/app/apikey
GOOGLE_API_KEY="your-google-api-key"
GOOGLE_MODEL="gemini-3-pro-preview"          # Full model — writers + evaluator
GOOGLE_MODEL_MINI="gemini-3-flash-preview"   # Fast model — analyst + memory writer
GOOGLE_EMBEDDING_MODEL="gemini-embedding-001" # Embeddings for vector memory

# LangSmith (optional — quality monitoring)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY="lsv2_pt_..."
LANGCHAIN_PROJECT="reflect-and-adapt"

# Tuning
CORTEX_COOLDOWN_HOURS=1   # How often Cortex runs (default: 1)
```

### 4. Register the plugin with OpenClaw

```bash
openclaw plugins add .openclaw/extensions/reflect-and-adapt
```

Or if OpenClaw auto-discovers extensions from that directory, just restart the gateway.

### 5. Restart the gateway

```bash
openclaw gateway restart
```

Verify the plugin loaded:

```bash
openclaw gateway status
# Look for: [reflect-and-adapt] Started.
```

Or check the log directly:

```bash
grep "reflect-and-adapt" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log
```

---

## Node version alignment

`better-sqlite3` is a native Node.js addon compiled for a specific ABI. If the OpenClaw gateway runs a different Node version than the one you used for `npm install`, the plugin will silently fail to load.

**Check for a mismatch:**

```bash
openclaw gateway status | grep runtimeVersion
node --version
```

If the versions differ, fix the gateway's systemd service to use the same Node:

```bash
# Find your nvm node path
which node

# Edit the service
nano ~/.config/systemd/user/openclaw-gateway.service
# Change ExecStart=/usr/bin/node to ExecStart=/home/<you>/.nvm/versions/node/v23.x.x/bin/node

# Reload and rebuild
systemctl --user daemon-reload
cd ~/.openclaw/workspace/.openclaw/extensions/reflect-and-adapt
npm rebuild better-sqlite3
openclaw gateway restart
```

---

## On-demand commands

### `/adapt`

Runs the full Cortex pipeline immediately, bypassing the cooldown timer. Useful after a long session where you don't want to wait for the next automatic trigger.

The assistant handles it — just type `/adapt` in your chat. The pipeline summary (findings → routed → proposals saved) is returned as a reply.

After a manual run, the cooldown timer resets so automatic Cortex doesn't fire again too soon.

---

## Skills

Skills are symlinked into your workspace `skills/` directory by the installer. The assistant reads their `SKILL.md` to know when and how to use them.

### `remember` — save a memory mid-session

The assistant automatically uses this skill when:
- You explicitly ask it to remember something
- It observes something worth retaining mid-session: a stated preference, personal fact, correction, or project detail

The skill passes your raw observation through the same reformulate → dedup → insert pipeline that Cortex uses, ensuring consistent memory quality. The assistant confirms what was actually stored (the reformulated sentence, not your raw text).

You can also invoke it directly from the CLI:

```bash
# From your workspace root
node skills/remember/ingest-memory.js "<observation>" [type]
```

Types: `user_fact` | `preference` | `example` | `context`

```bash
node skills/remember/ingest-memory.js "User prefers bullet points over prose for summaries" preference
node skills/remember/ingest-memory.js "User is writing a Bachelor's thesis on adaptive AI" context
```

### `proposals` — review workspace improvement suggestions

See [Managing proposals](#managing-proposals) below.

---

## Managing proposals

When the Cortex pipeline produces proposals, they appear at the start of your next session. The assistant will walk you through each one and ask for a decision.

You can also manage proposals manually using the CLI:

```bash
# List all proposals grouped by status
node skills/proposals/manage-proposals.js list

# Show full details + proposed change for a specific proposal
node skills/proposals/manage-proposals.js show <proposal-id>

# Approve (prints the exact change to apply to the file)
node skills/proposals/manage-proposals.js approve <proposal-id>

# Reject with an optional reason
node skills/proposals/manage-proposals.js reject <proposal-id> "already covered"

# Re-queue a previously dismissed proposal
node skills/proposals/manage-proposals.js pending <proposal-id>
```

**Proposal statuses:**

| Status | Meaning |
|---|---|
| `PENDING` | New, will be shown at next session start |
| `PRESENTED` | Shown this session, awaiting decision |
| `APPROVED` | Accepted — change has been applied |
| `REJECTED` | Dismissed — reason stored, suppresses similar future proposals |
| `STALE` | Superseded by a newer proposal for the same file |

---

## What the Cortex analyst looks for

The analyst reads recent conversations and session health metrics, then extracts findings by type:

| Finding type | Min occurrences | Target |
|---|---|---|
| `correction` | 2 | `SOUL.md` — behavioral rule to add |
| `frustration_pattern` | 2 | `SOUL.md` — behavioral rule to add |
| `user_fact` | 1 | `USER.md` — factual profile entry |
| `missing_capability` | 2 | New `SKILL.md` |
| `workflow_convention` | 2 | `AGENTS.md` — workflow rule |
| `persona_preference` | 1 | `IDENTITY.md` — explicit user request only |
| `periodic_task` | 2 | `HEARTBEAT.md` — recurring task checklist |
| `memory_entry` | 1 | `memory.lance/` — episodic memory, auto-committed |

Low-confidence findings and findings matching previously rejected proposals are suppressed automatically.

---

## LangSmith monitoring (optional)

When `LANGCHAIN_API_KEY` is set, the evaluator submits per-turn feedback scores to LangSmith after each session:

- `helpfulness` (0–1, from 1–5 scale)
- `conciseness` (0–1)
- `correction_signal` (0 or 1)
- `frustration_signal` (0 or 1)
- `task_completed` (0 or 1)
- `user_satisfaction` (0, 0.5, or 1)
- `response_accepted` (0 or 1)
- `format_match` (0 or 1)

View charts at [smith.langchain.com](https://smith.langchain.com) → your project → **Monitoring** → **Feedback**.

The Cortex pipeline runs (analyst, memory writer, file writers) are also traced — visible in the **Traces** tab.

---

## Local data storage

All data is stored locally inside the plugin directory:

| Path | Contents |
|---|---|
| `reflect.db` | SQLite: conversations, scores, proposals, state |
| `memory.lance/` | LanceDB vector store: episodic memories with embeddings |
| `cortex_runs/` | JSON logs of each Cortex pipeline run (for debugging) |

No data is sent anywhere except to the Google AI API and (optionally) LangSmith.

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | — | Google AI API key |
| `GOOGLE_MODEL` | No | `gemini-3-pro-preview` | Full model — writers + evaluator |
| `GOOGLE_MODEL_MINI` | No | `gemini-3-flash-preview` | Fast model — analyst + memory writer |
| `GOOGLE_EMBEDDING_MODEL` | No | `gemini-embedding-001` | Embedding model for vector memory |
| `LANGCHAIN_TRACING_V2` | No | — | Set to `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | No | — | LangSmith API key |
| `LANGCHAIN_PROJECT` | No | — | LangSmith project name |
| `CORTEX_COOLDOWN_HOURS` | No | `1` | Minimum hours between Cortex runs |
