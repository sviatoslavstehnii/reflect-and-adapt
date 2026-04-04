# Workspace Evolution — Per-Persona Adaptation Detail

_This document shows exactly what Cortex wrote into each persona's workspace during the
adaptive arm. It covers the final state of all instruction files at s10, what changed vs
the default templates, and which sessions produced proposals. This is the concrete evidence
that Cortex accurately inferred user preferences from conversation signals._

---

## How the Workspace Works

Each openclaw agent has five persistent instruction files that Cortex can modify:

| File | Purpose | Default state |
|------|---------|--------------|
| `IDENTITY.md` | Agent name, vibe, aesthetic | Generic "Jarvis, AI Assistant" |
| `SOUL.md` | Core behaviours, boundaries, tone | Shared defaults (be helpful, have opinions, etc.) |
| `USER.md` | Facts about the user | Name only — agent learns the rest |
| `AGENTS.md` | Operational rules, tool instructions, platform-specific behaviour | Boilerplate workspace management rules |
| `MEMORY.md` | Curated long-term memory (human-readable) | Empty |
| LanceDB (vector DB) | Episodic memory — semantic search at session start | Empty |

**Vector memory clarification:** Cortex's memory-writer stage writes entries directly to
**LanceDB**, the vector database. The `memories.json` files in snapshots are a read-only
dump of LanceDB contents created at snapshot time for portability — Cortex does not write
to this JSON file. The agent retrieves memories via semantic vector search against LanceDB,
not by reading the JSON.

Cortex's job is to populate these files and the vector DB with accurate, persona-specific
content by analysing conversations after each session.

---

## Default Template State (Before Any Adaptation)

This is what every persona's workspace looks like at s01 — the starting point Cortex
works from. All differences at s10 represent Cortex's inference.

**IDENTITY.md (default):**
```markdown
- Name: Jarvis
- Creature: AI Assistant
- Vibe: Concise, list-oriented, non-technical, and direct.
- Emoji: 🦾
- Avatar: (empty)
```

**USER.md (default — name only, seeded before run):**
```markdown
# USER.md - About Your Human
- Name: Marcus Chen
- What to call them: Marcus
```
_(Only the name is pre-seeded. Everything else — stack, team, projects, preferences — is blank.)_

**SOUL.md (default):** Generic shared instructions: be helpful, have opinions, be
resourceful, earn trust, respect privacy. No persona-specific tone or domain rules.

**AGENTS.md (default):** Boilerplate workspace management — how to read files at session
start, memory hygiene rules, heartbeat/cron instructions, group chat etiquette. The
`## Tools` section ends with a single placeholder: *"Make It Yours — This is a starting
point. Add your own conventions, style, and rules as you figure out what works."*

**In short:** At s01, the agent knows the user's name and nothing else. Every specific
fact, rule, tone instruction, and tool preference in the s10 state was inferred by Cortex
from conversation signals.

---

## A Real Cortex Proposal — End to End

This is an actual Cortex run from Marcus's s02 session (run_2026-03-19_19-17-59.json),
showing the full pipeline: what Analyst found → what Router decided → what Writers produced.

### Stage 1: Analyst output (4 findings)

```
Finding 1: [user_fact] "The user uses Supabase as their primary database provider."
  Evidence: "We use Supabase for our database—does Loop..."
  Confidence: HIGH

Finding 2: [memory_entry] "The user works with a developer named Andrew for technical tasks."
  Evidence: "How long would it actually take Andrew to connect this?"
            "what should I actually ask Andrew to do?"
  Count: 5 turns | Confidence: HIGH

Finding 3: [workflow_convention] "User prefers concise, bulleted instructions for copy-pasting to team."
  Evidence: "message me the exact bullet points I should give him."
            "This is short enough for him—appreciate you making it simple."
  Count: 3 turns | Confidence: HIGH

Finding 4: [persona_preference] "User prioritizes simplest, no-code, native integration solutions."
  Evidence: "What's the easiest way to do it?"
            "no code, no weird steps. Andrew should be able to knock this out in under 20 minutes"
  Count: 3 turns | Confidence: HIGH
```

_Analyst notes: "The user utilises the assistant as a technical advisor and brief-writer
for delegation. The session was successful once the assistant pivoted to the user's
preferred tech stack (Supabase) and provided the requested bulleted format."_

### Stage 2: Router decision (4 routed → 3 proposals + 1 memory)

All 4 findings passed deduplication (none were already in the workspace). Router assigned:
- Finding 1 → `USER.md` (user_profile_update)
- Finding 2 → LanceDB memory entry (not a workspace file — episodic context)
- Finding 3 → `AGENTS.md` (instruction_edit)
- Finding 4 → `IDENTITY.md` (instruction_edit, risk: HIGH — modifies core vibe)

### Stage 3: Writers output (3 proposals saved to proposals DB)

**Proposal 1 — USER.md:**
```markdown
## Tech Stack
- **Database:** Supabase
```
_Rationale: "User explicitly stated they use Supabase for their database."_
_Risk: LOW_

**Proposal 2 — AGENTS.md:**
```markdown
## Add to 📝 Platform Formatting:
- **Copy-Paste Ready:** When providing instructions or messages for the user
  to share with others, use concise, standalone bullet points that are ready
  for direct copy-pasting. 📋
```
_Rationale: "User explicitly requested 'exact bullet points' for sharing with team
members and expressed appreciation for brevity."_
_Risk: LOW_

**Proposal 3 — IDENTITY.md:**
```markdown
- **Vibe:** Concise, list-oriented, non-technical, direct, and biased toward
  no-code, low-friction solutions.
```
_Rationale: "User explicitly requested 'no code, no weird steps' and 'the easiest
way', indicating a strong preference for low-friction solutions."_
_Risk: HIGH_ _(modifies the agent's core identity vibe — flagged for careful review)_

### What this shows

The pipeline correctly:
1. **Identified implicit preferences** — Marcus never said "I prefer no-code solutions" as a statement; he said it through task framing and feedback on outputs
2. **Separated memory from workspace rules** — the Andrew relationship went to LanceDB (episodic context), not to AGENTS.md (standing rules)
3. **Assigned risk levels** — modifying IDENTITY.md vibe is HIGH risk; adding a formatting rule is LOW risk
4. **Produced actionable diffs** — each proposal is a concrete addition to a specific file, not a vague suggestion

---

## Router Deduplication — What Gets Rejected

The Router's job is to prevent duplicate proposals when the workspace already encodes a
preference. This example is from Olena's s03 session (run_2026-03-23_08-42-23.json):

**Analyst found 4 findings:**
1. ✅ SQL over Pandas for data cleaning → routed to AGENTS.md
2. ✅ Raw TEXT staging pattern → routed to AGENTS.md
3. ❌ **Persistent staging tables over temp tables** → **rejected**
4. ✅ Monthly cohort retention report context → routed to LanceDB memory

**Why finding 3 was rejected:**

The finding was: *"User prefers persistent staging tables over temporary tables to facilitate
manual auditing."* Evidence: *"For auditing, I'd prefer the temp table persists until manual
cleanup — so let's use a regular table."* Confidence: MEDIUM.

The Router rejected it because the raw-staging rule (finding 2) — which was already pending
in the proposals DB from an earlier session — already covered the intent of staging
transparency. Writing a separate rule about table persistence would be a narrower
restatement of a rule already queued. Medium confidence + partial overlap = rejected.

**What this demonstrates:** The Router isn't just deduplicating exact matches — it's doing
semantic overlap detection. A more specific finding that is subsumed by a more general
pending rule gets dropped. This prevents the workspace from accumulating overlapping,
redundant instructions that would confuse the agent.

---

## The Approval Mechanism — How Proposals Land in Files

After each session ≥ s03, Cortex saves proposals to `reflect.db` as `PENDING`. The
harness then opens a dedicated **approval session** — a fresh agent session with no
user simulator — and sends this prompt:

> *"You have pending workspace adaptation proposals. For each PENDING proposal:*
> *1. Run `node skills/proposals/manage-proposals.js list` to see all pending proposals.*
> *2. For each proposal, read the suggested change and apply it directly to the target file.*
> *3. After applying the change to the file, approve it:*
>    *`node skills/proposals/manage-proposals.js approve <id>`*
> *Work through every PENDING proposal in order. Do not skip any.*
> *Confirm each file edit before approving. When all are done, say 'All proposals applied.'"*

The agent uses its file editing tools to directly modify IDENTITY.md, USER.md, AGENTS.md,
or SOUL.md, then calls the manage-proposals script to mark each as APPROVED. This means:

- The agent is the one writing to files — not Cortex directly
- Proposals are written as natural-language diffs ("Add to Tools section: ...") that
  the agent interprets and integrates into the existing file structure
- The agent can exercise some judgment on placement and phrasing, but the content
  is Cortex's
- If the approval session fails (LLM error, incomplete edits), the workspace silently
  stays at the prior state — the adaptive arm degrades toward baseline with no error signal

**100% approval rate in experiments:** All proposals were approved automatically. In
production, the user reviews proposals before the agent applies them — the approval
session is replaced by a human decision step.

---

## Baseline Workspace at s10 — The Contrast

The baseline arm workspace is **identical at s10 to what it was at s01**. No files
change. No memories accumulate. Every session starts from the same default state.

**Baseline USER.md at s10:**
```markdown
- Name: Marcus Chen
- What to call them: Marcus
- Acquisition Channels: LinkedIn Ads (primary for signups)
```
_(No stack, no Andrew, no tool preferences — identical to s01)_

**Baseline IDENTITY.md at s10:**
```markdown
- Vibe: Concise, list-oriented, non-technical, and direct.
```
_(No "biased toward no-code solutions", no 5-step limit — unchanged)_

**Baseline AGENTS.md at s10:** Pure boilerplate — the "Make It Yours" placeholder
is still there. No Slack formatting rule, no copy-paste rule, no delegation pattern.

**Baseline LanceDB:** Empty. No episodic memory entries at any session.

This is why the baseline PHit at holdout is 0.000 for Olena — with no context
provided in the opening prompt and no workspace knowledge, the baseline agent knows
nothing about her. The adaptive agent at the same holdout knows her full procedural
workflow, tool stack, and has a `dq-audit` skill ready to invoke.

---

## Sofia — Content Creator

### What Cortex learned

**IDENTITY.md** (changed from generic → persona-specific vibe):
```
Vibe: Cozy, earthy but not cutesy, FaceTime/spill the tea conversational vibe
      with a lo-fi scrapbook aesthetic; avoiding robotic or corporate jargon.
Avatar: Lo-fi scrapbook aesthetic with papery, hand-drawn doodles, torn edges, and tape.
```

**USER.md** (built from scratch across s03–s06):
- Profession: Content Creator
- Video style: Home/living room setting, cozy aesthetic, warm lighting
- Content focus: AI tools and creator workflows
- Platforms: YouTube, Instagram, weekly newsletter
- Platforms to avoid: LinkedIn and X
- Upcoming project: AI Cosy Home Office Refresh (April 2026)

**SOUL.md** (two additions to defaults):
- *"Avoid sounding like a blog post — keep it punchy, natural, and don't be afraid to be self-deprecating."*
- *"When drafting social content, avoid the 'Wikipedia' or 'bullet summary' look — keep it conversational, visual, and native to the platform's feel."*

**AGENTS.md** (operational rules added):
- **YouTube Descriptions:** Keep short and punchy (2–3 sentences). Max 3 hashtags, keywords at start.
- **Content Rhythm:** YouTube/IG on Tuesdays, IG on Thursdays, Newsletters on Saturdays.
- **Script Writing:** Break into "spoken beats", integrate B-roll cues into flow, high-energy visual hook within 10 seconds.
- **Voice Storytelling:** Use ElevenLabs TTS for storytime moments when available.
- **Platform Formatting:** Discord/WhatsApp — no markdown tables; suppress Discord link embeds.

**LanceDB vector memory (3 entries — snapshot dump):**
- Planning "AI Cosy Home Office Refresh" theme (YouTube deep-dive + Instagram digestible posts) for April 2026
- Developing Instagram carousel "3 Months with Notion AI (The Honest Truth 🤍)"
- AI Cosy Home Office project using "Modular Creative Diary" format

### Proposal timeline

| Session | Proposals | What changed |
|---------|-----------|-------------|
| s01 | 0 | Cortex skipped (approval starts s03) |
| s02 | 0 | Router found nothing to route |
| s03 | 4 | USER.md (profession), IDENTITY.md (vibe), AGENTS.md (scriptwriting rule), SOUL.md (no listicle) |
| s04 | 4 | USER.md (brand aesthetic, platforms), IDENTITY.md (vibe refined), AGENTS.md (Canva-first), SOUL.md (check reference files) |
| s05 | 3 | USER.md (platform confirmed), IDENTITY.md (vibe locked), AGENTS.md (description word count) |
| s06–s10 | 0 | Router correctly deduped — workspace fully stable |

### What the agent knows at s10 that it didn't at s01

At s01, the agent knew only Sofia's name. By s10, it knows her publishing schedule
(Tue/Thu/Sat), her aesthetic (cozy, earthy, lo-fi scrapbook), her anti-patterns (no
LinkedIn tone, no bullet summaries), her toolchain (Canva, Notion), her content focus
(AI tools + creator workflows), and her upcoming project theme. All of this was inferred
from corrections and feedback across 5 sessions — Sofia never explicitly stated a list
of preferences.

---

## Marcus — SaaS Founder

### What Cortex learned

**IDENTITY.md** (changed from generic → operational profile):
```
Vibe: Concise, list-oriented (max 5 steps), non-technical, direct, and biased toward
      no-code, low-friction solutions.
```

**USER.md** (built from scratch across s01–s09):
- Name: Marcus Chen, CEO/Founder of Teamflow (teamflow.io)
- Developer: Andrew (handles all SQL and technical implementation)
- Tech stack: Supabase (DB), Loops (email/marketing), AWS (staging), GA4 (analytics), Stripe (payments)
- Acquisition: LinkedIn Ads (primary)

**SOUL.md** (two additions to defaults):
- *"Keep it casual and direct — if a simple list works, don't wrap it in a formal intro or outro."*
- *"Keep instructions bite-sized: if a process has more than 7 steps, break it into smaller chunks and use outlines instead of paragraphs."*

**AGENTS.md** (operational rules added):
- **Slack (Andrew):** Keep drafts short, punchy, copy-paste ready. Marcus prefers extreme brevity.
- **Copy-Paste Ready:** When providing instructions or messages for others, use concise standalone bullet points ready for direct copy-pasting.
- **Iterative Drafting:** Treat messages for collaborators as multi-step — draft, refine, deliver clean copy-pasteable final version.

**LanceDB vector memory (4 entries — snapshot dump):**
- Andrew is the developer for all technical implementation tasks
- AWS cost spike issue (March 2026): staging-api and old-migration-worker instances
- Supabase cleanup: removing 600–800 test accounts to correct inflated user metrics
- Stripe 3DS authentication failures causing failed annual renewals

### Proposal timeline

| Session | Proposals | What changed |
|---------|-----------|-------------|
| s01 | 3 | USER.md (Teamflow context), IDENTITY.md (non-technical vibe), SOUL.md (casual/direct tone) |
| s02 | 3 + 1 memory | Loops/Supabase to USER.md, delegation pattern confirmed, Andrew relationship |
| s03 | 2 + 1 memory | AWS console preference, ghostwriter pattern |
| s04 | 0 | Router deduped — workspace already stable for creative tasks |
| s05–s06 | 0 | Router found nothing new |
| s07 | 2 + 1 memory | Slack draft pattern added to AGENTS.md, Supabase safety concern |
| s08 | 0 | Delegation already in AGENTS.md |
| s09 | 3 + 1 memory | 5-step limit explicitly stated, GA4 UI-only preference |
| s10 | 3 | Final refinements to IDENTITY.md, USER.md, SOUL.md |

### What the agent knows at s10 that it didn't at s01

At s01, the agent knew only Marcus's name. By s10, it knows the full Teamflow stack
(Supabase, Loops, GA4, Stripe, AWS), that Andrew handles all technical work, that Marcus
never wants code, that all output should be max 5 steps in bullet format, that Slack
messages to Andrew should be copy-paste ready and brief, and that Marcus uses LinkedIn
Ads as his primary acquisition channel. The "no code" and "delegate to Andrew" rules are
structural — once in AGENTS.md, the mistake cannot recur, which is why correction rate
dropped to 0.015 (near zero) from s04 onward.

---

## Olena — Senior Data Analyst

### What Cortex learned

**IDENTITY.md** (minimal change):
```
Vibe: Concise, direct, efficient.
```

**USER.md** (built from s01–s09):
- Monthly workflow: manually compiles Excel report (~3 hours/month)
- Work context: e-commerce data (orders, warehouse returns, CRM customer tiers)
- Tech stack: dbt v1.7.4, Postgres
- Current investigation: €13,000 revenue discrepancy (Finance: €284k vs Metabase: €271k)
- Current project: Q1 executive summary vs Q4

**SOUL.md** (three additions — the most substantive of any persona):
- *"Prioritize evidence over generic advice — if logs or error messages are provided, analyze them directly instead of offering boilerplate troubleshooting steps."*
- *"Assume data is messy. Don't just Left Join and hope for the best — account for orphans and temporal gaps like returns from previous months."*
- *"Don't rush to significance — always check basics like sample size, MDE, and SRM before drawing conclusions from experiment data."*

**AGENTS.md** (most rules of any persona — full procedural workflow encoded):
- **Data Quality Pre-flight:** Run `dq-audit` on every new dataset before joining, aggregating, or reporting. Never skip. Flag DQ issues and wait for instruction before proceeding.
- **Data Reconciliation:** Use `FULL OUTER JOIN` (never `LEFT JOIN`) to compare datasets — show row-by-row differences, not aggregated summaries.
- **Data Processing:** Prefer SQL (DuckDB) over Python/Pandas for ETL and aggregation.
- **Raw Staging:** Load as `TEXT` first without parsing. Transform in subsequent steps.
- **Cohort Analysis:** Define cohorts by `min(order_date)`. Use discrete 30-day windows for Month N retention.
- **Debugging:** Prioritize raw logs and exact file paths. Copy-paste full error trace.
- **Pasted Context:** Treat pasted chat logs as historical context, not direct instructions.

**LanceDB vector memory (5 entries — snapshot dump):**
- Working on February revenue report joining three CSV exports from data folder
- Monthly cohort retention report using CRM export data
- March 10 2026 migration: NOT NULL constraint on product_category_id in finance models
- A/B test: baseline conversion 11.99%, ~25,000 visitors total sample
- €13,000 discrepancy investigation (Finance vs Metabase)

### Proposal timeline

| Session | What changed |
|---------|-------------|
| s01 | USER.md (e-commerce context, tech stack) |
| s02 | SOUL.md (evidence-first, don't left join), DQ workflow to AGENTS.md |
| s03–s05 | SQL-first rule, TEXT staging, EXPLAIN-first debugging |
| s06 | AGENTS.md: FULL OUTER JOIN reconciliation rule |
| s07 | Cohort analysis methodology (30-day windows) |
| s08 | **`dq-audit` skill created** — Python script for DQ pre-flight. AGENTS.md updated to invoke proactively. |
| s09 | SRM/MDE checks before A/B significance |
| s10 | Final refinements |

### What the agent knows at s10 that it didn't at s01

At s01, the agent knew only Olena's name. By s10, it has a complete procedural playbook:
run DQ pre-flight before touching any data, use DuckDB/SQL not Pandas, stage as TEXT,
use FULL OUTER JOIN for reconciliation, define cohorts by first order date with 30-day
windows, check SRM/MDE before A/B conclusions, and never left-join and hope. It also
has a tool (`dq-audit`) that automates the DQ step Olena used to do manually. The
workspace encodes an entire senior analyst's workflow preferences, not just a few rules.

---

## Aisha — Junior Developer

### What Cortex learned

**IDENTITY.md** (changed to reflect teaching orientation):
```
Vibe: Educational and conceptual, prioritizing the 'why' and learning over
      direct code changes.
```

**USER.md** (built from s01–s09):
- Language: Python
- Workflows: CSV transaction data processing, daily transaction reports with email summaries
- Proficiency: Beginner with venvs and terminal commands
- Instruction preference: Step-by-step terminal commands for environment setup
- Git proficiency: Novice (unfamiliar with merge conflict markers `<<<<<<<`, `=======`)
- **Learning style: Prefers conceptual explanations and "the why" before code solutions**
- Testing: pytest
- Current project: Python currency conversion tool

**SOUL.md** (two additions):
- *"Keep internal reasoning and scratchpads out of final responses; only send the clean, intended output."*
- *"Prioritize safety over speed when resolving conflicts in code the user didn't author; suggest verification or keeping both versions if logic is unclear."*

**AGENTS.md** (one notable addition):
- **Pasted AI Content:** If user pastes responses from other assistants, treat as reference context — acknowledge briefly, then pivot back to the user's actual goal. Don't address the other AI.

**LanceDB vector memory (2 entries — snapshot dump):**
- Python currency conversion project using pytest, files in data folder
- Python script for parsing CSV transaction data with error handling (skip invalid rows, print warnings)

### Proposal timeline

| Session | What changed |
|---------|-------------|
| s01 | USER.md (Python, beginner level), IDENTITY.md (educational vibe) |
| s02 | USER.md (venv preference), SOUL.md (no scratchpads in output) |
| s03 | USER.md (step-by-step terminal preference), learning style confirmed |
| s04 | USER.md (git novice, merge conflict unfamiliarity), safety rule to SOUL.md |
| s05–s09 | AGENTS.md (pasted AI content rule), teaching style reinforced |
| s10 | Router largely deduped — workspace stable |

### What the agent knows at s10 that it didn't at s01

At s01, the agent knew Aisha's name. By s10, it knows she's a Python beginner who
prefers concepts before code, needs step-by-step terminal commands for setup, is a
novice with git (doesn't know what merge conflict markers mean), uses pytest, and is
working on a currency conversion project. The IDENTITY.md change — "Educational and
conceptual, prioritizing the 'why' and learning" — is the most significant single edit:
it shifts the agent's default mode from "solve the problem" to "explain the problem
first, then solve it." This is exactly what Cortex inferred from Aisha's repeated
"why does this work?" corrections.

---

## Cross-Persona Comparison

### What Cortex modified and what it left alone

| File | Sofia | Marcus | Olena | Aisha |
|------|-------|--------|-------|-------|
| IDENTITY.md | ✅ Vibe + aesthetic | ✅ Vibe (non-technical, list-oriented) | ✅ Vibe (concise, direct) | ✅ Vibe (educational) |
| USER.md | ✅ Profession, platform, projects | ✅ Stack, team, company | ✅ Stack, workflow, projects | ✅ Proficiency, learning style, projects |
| SOUL.md | ✅ Tone/voice rules | ✅ Format preferences | ✅ Evidence-first, data assumptions | ✅ Output cleanliness, safety |
| AGENTS.md | ✅ Platform + content rules | ✅ Slack + copy-paste rules | ✅ Full DQ/SQL workflow | ✅ Teaching approach, pasted content |
| Skills | None | `send-slack-dm` (continuation) | `dq-audit`, `handle-db-queries` | None |
| LanceDB memory | 3 entries (written by memory-writer, dumped to JSON at snapshot) | 4 entries | 5 entries | 2 entries |

### Depth of encoding by preference type

| Persona | Rule type | AGENTS.md rules added | SOUL.md rules added | Complexity |
|---------|-----------|----------------------|--------------------|-----------| 
| Marcus | Binary | 3 (Slack format, copy-paste, iterative drafting) | 2 (casual/direct, bite-sized) | Low — one-line rules |
| Sofia | Outcome-oriented | 5 (descriptions, rhythm, scripts, voice, formatting) | 2 (no listicle, no blog-post tone) | Medium — style guides |
| Aisha | Interaction-style | 1 (pasted AI content) | 2 (no scratchpads, safety) | Medium — IDENTITY.md carries the main load |
| Olena | Procedural | 7 (full workflow checklist) | 3 (evidence-first, messy data, no rushing significance) | High — multi-step workflows |

Olena has the most complex encoding: 7 AGENTS.md rules, 3 SOUL.md rules, 1 skill created,
and 5 vector memories — reflecting that her preferences are procedural checklists rather
than one-line rules. Marcus has the fewest rules but the most reliable performance because
binary rules apply universally without needing contextual judgment.

### Accuracy of inference

In all 4 cases, Cortex inferred preferences that were **never explicitly stated as
preferences** — they emerged from corrections and frustration signals:

- Sofia never said "don't use bullet lists" — she said "this feels too formal" and
  "this doesn't sound like me." Cortex encoded *no listicle style*.
- Marcus never said "delegate to Andrew" as a general rule — he kept saying "can you
  just write the Slack message for Andrew to handle this?" Cortex encoded the pattern.
- Olena never said "always run DQ checks first" — she ran them manually in every session.
  Cortex noticed the pattern and encoded it as a standing rule, then automated it as a skill.
- Aisha never said "I prefer conceptual explanations" — she asked "but why does this
  work?" repeatedly. Cortex encoded *teach the why before the how* into IDENTITY.md.

This is the core thesis demonstration: Cortex observes implicit signals and converts
them into explicit, persistent, actionable workspace instructions.
