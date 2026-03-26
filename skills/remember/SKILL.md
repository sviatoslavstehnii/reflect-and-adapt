# Remember

## Trigger
Use when the user explicitly asks you to remember something, OR when you observe something mid-session worth retaining: a stated preference, a personal fact, a correction to previous behavior, or an ongoing project detail. Don't wait for the background Cortex cycle — capture it now.

## Steps

```bash
node skills/remember/ingest-memory.js "<raw observation>" [type]
```

Types:
- `user_fact` — verifiable fact about the user (default)
- `preference` — style, tool, or workflow preference
- `example` — a specific interaction pattern worth repeating
- `context` — ongoing project or situational context

Examples:
```bash
node skills/remember/ingest-memory.js "User prefers bullet points over prose for summaries" preference
node skills/remember/ingest-memory.js "User is writing a Bachelor's thesis on adaptive AI agents" context
node skills/remember/ingest-memory.js "User corrected that they use pnpm, not npm" user_fact
```

## Notes
- Pass the raw observation — the script reformulates it into a clean, retrieval-friendly sentence and checks for duplicates before saving
- Read the script output: it prints either `Saved <id>: "<stored content>"` or `Skipped: <reason>`
- Confirm to the user what was stored (use the printed stored content, not your paraphrase)
- If skipped as a duplicate, tell the user the fact is already in memory
