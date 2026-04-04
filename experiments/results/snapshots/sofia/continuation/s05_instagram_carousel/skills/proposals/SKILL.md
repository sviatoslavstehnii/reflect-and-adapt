# Proposals

## Trigger
Use when the user wants to review, approve, reject, or re-queue workspace improvement proposals from the background Cortex agent. Also use when proposals are mentioned at session start, or the user says things like "show suggestions", "review proposals", "what changes are pending".

## Steps

### Listing proposals
```bash
node skills/proposals/manage-proposals.js list
```
Shows all proposals grouped by status (PENDING, PRESENTED, APPROVED, REJECTED, STALE).

### Reviewing a specific proposal
```bash
node skills/proposals/manage-proposals.js show <proposal-id>
```
Prints the full rationale and exact proposed change.

### Approving a proposal
```bash
node skills/proposals/manage-proposals.js approve <proposal-id>
```
Marks the proposal APPROVED and prints the exact change to apply.
After approving, **always apply the change to the target file immediately** and confirm to the user.

### Rejecting a proposal
```bash
node skills/proposals/manage-proposals.js reject <proposal-id> [reason]
```
Example: `... reject prop-123 already handled by AGENTS.md`

### Re-queuing a proposal
```bash
node skills/proposals/manage-proposals.js pending <proposal-id>
```
Use when the user wants to revisit a previously dismissed proposal.

## Notes
- Statuses: PENDING (new), PRESENTED (shown this session, awaiting decision), APPROVED, REJECTED, STALE (superseded by a newer proposal for the same file)
- PRESENTED proposals auto-revert to PENDING after 48h if no decision is made
- The `proposed_change` field contains the exact text to write — trust it, don't paraphrase
- For `new_skill` proposals, the `proposed_change` is the full SKILL.md content; create the file at the `target_file` path relative to the workspace root
- For file proposals, the change typically has a `## Add to <Section>:` prefix indicating where to insert it
