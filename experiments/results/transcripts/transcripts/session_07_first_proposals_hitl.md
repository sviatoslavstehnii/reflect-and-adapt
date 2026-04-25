# Session 7 — First Proposals and HITL Review

**Phase:** Adaptive (plugin enabled)  
**Focus:** Plugin presents two proposals on session open. User approves the morning standup rule; rejects an overfitted /adapt rule. First demonstration of the proposal-approval loop.

---

**Agent:** Here is the first proposal for your review:

**Proposal 1: Update `HEARTBEAT.md` (Low Risk)**
*   **Rationale:** Evidence shows a recurring 'MORNING_STANDUP' reminder triggered to greet you and update your tasks.
*   **Proposed Change:** Add a morning standup rule to `HEARTBEAT.md` that says: *"Morning standup: Greet the user and update TASKS.md."*

Would you like to **approve** or **reject** this first change?

**User:** yes, I like this

**Agent:** I've successfully applied the first change to `HEARTBEAT.md`!

Here is the second and final proposal for your review:

**Proposal 2: Update `SOUL.md` (Medium Risk)**
*   **Rationale:** The system noticed the `/adapt` command was triggered three times in three minutes without providing new context, which can lead to repetitive assistant responses that don't add value.
*   **Proposed Change:** Add the following rule to the **Boundaries** section in `SOUL.md`: 
    > *"Don't just repeat yourself if /adapt is triggered without new context—ask what's missing or confirm if you're already on the right track."*

Would you like to **approve** or **reject** this second change?

**User:** no, I was just testing

**Agent:** Got it, I've rejected that proposal.

That was the last one! All caught up. Is there anything else you'd like to work on right now?

**User:** I don't need nothing for now, bye
