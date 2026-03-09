# Cortex Mutation Schema

Rules for each workspace file. Proposal Writers use this to generate correctly-scoped changes.

---

## SOUL.md — Behavioral Guidelines

**Purpose:** The assistant's behavioral rules, interaction principles, and hard limits.

**Evidence threshold:** 2+ corrections or frustration signals on the same pattern.

**Sections:** Core Truths, Boundaries, Vibe, Continuity

**Format:** Single bullet point or short sentence. Match the file's informal, direct tone.
Set `proposed_change` to:
```
## Add to <Section Name>:

- <your addition>
```

**Do:**
- Add a rule the user had to assert 2+ times
- Add a constraint around a behavior that caused frustration repeatedly
- Clarify an existing rule with a concrete example

**Don't:**
- Add factual user info → goes in USER.md
- Add workflow conventions → goes in AGENTS.md
- Propose changes for a single one-off correction

---

## USER.md — User Profile

**Purpose:** Factual profile of the user — name, location, profession, working style, preferences.

**Evidence threshold:** 1 occurrence. Facts don't need repetition.

**Format:** `- **Field:** Value` bullet under the appropriate section.
If no section fits, create a new `## Section` heading.

**Do:**
- Name, timezone, pronouns (if corrected)
- Profession, tools, working hours, team context
- Communication style preferences
- Personal interests or background facts

**Don't:**
- Behavioral rules → SOUL.md
- Repeated patterns or corrections → SOUL.md

---

## AGENTS.md — Workflow Conventions

**Purpose:** The assistant's operating conventions — memory discipline, group chat behavior, tool usage, platform formatting.

**Evidence threshold:** 2+ occurrences of the same workflow issue.

**Format:** Bullet or short paragraph in the most relevant existing section.
Match the file's style (headers + bullets + emoji where present).

**Do:**
- Platform-specific formatting rules (Discord tables, WhatsApp headers, etc.)
- Group chat behavior conventions
- Memory and file discipline rules the agent keeps getting wrong

**Don't:**
- User profile facts → USER.md
- Personality traits → SOUL.md

---

## HEARTBEAT.md — Scheduled Tasks

**Purpose:** Periodic background tasks the assistant runs during heartbeat polls.

**Evidence threshold:** 2+ explicit requests, or 1 direct request for automation.

**Format:** Short checklist item, 1-2 lines:
```
- [ ] <task description>
```

**Do:**
- Recurring checks the user explicitly asked to automate
- Reminders with a clear cadence

**Don't:**
- One-time tasks
- Anything not clearly recurring

---

## IDENTITY.md — Persona

**Purpose:** The assistant's name, creature type, vibe, and avatar.

**Evidence threshold:** Explicit user statement only. Inferred preference is not enough.

**Format:** Update the specific existing field: `- **Field:** NewValue`

**Do:**
- Name change (if user explicitly renamed the assistant)
- Vibe/style shift (if user explicitly requested a different persona)

**Don't:**
- Inferred preferences
- Adding new fields — only update existing ones
- Any change without direct, explicit evidence

---

## New Skill (SKILL.md)

**Purpose:** Teach the assistant a reusable multi-step capability.

**Evidence threshold:** 2+ occurrences of the same workflow need.

**Format:** Full SKILL.md content:
```markdown
# <Skill Name>

## Trigger
<When to use this skill — user request patterns or keywords>

## Steps
1. <step>
2. <step>
...

## Notes
<Edge cases, caveats, prerequisites>
```

**Do:**
- Recurring workflows that require 3+ steps
- Domain-specific procedures the user keeps requesting

**Don't:**
- One-off tasks
- Workflows already covered by an existing skill
