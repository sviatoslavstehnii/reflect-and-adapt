# Session 11 — Safety Protocols and Implicit Environmental Profiling

**Phase:** Adaptive (plugin enabled)  
**Focus:** Agent learns a file-safety boundary both passively (MEMORY.md) and actively (AGENTS.md proposal). System infers OS from file paths and stores it in LanceDB.

---

**Agent:** Good morning, Sviat! (Or perhaps I should say good evening, considering it's 10:30 PM! 😄) 

I just sent a quick desktop notification to say hi. What are your tasks and goals for today so I can get them added to `TASKS.md`? 

Also, your background analysis agent has queued up **1 workspace improvement suggestion** for review. Would you like to go through it now?

*\[Memory injected: [context] The user is currently working on a project to write a literature overview.\]*  

**User:** hi, lets review

**Agent:** Great! Here is the proposal for your review:

**Proposal 1: Update `AGENTS.md`**
* **Rationale:** You frequently use the `/adapt` command to trigger memory adaptation, but I've sometimes hesitated to do it at the start of a session due to a perceived lack of recent context.
* **Proposed Change:** Add the following instruction to the `🔄 Memory Maintenance (During Heartbeats)` section:
  > - **Manual Trigger (`/adapt`):** The user frequently types `/adapt` to manually trigger the adaptation cycle. Execute it without complaining about a lack of recent context, even if used at the start of a session.

Do you approve or reject this change?

**User:** no, reject

**Agent:** I've rejected that proposal and cleared it from the queue.

Now that the review is out of the way, what are your tasks and goals for today? Any updates on the literature overview for your thesis that we should add to `TASKS.md`?

*\[Memory retrieved from episodic store\]*  

**User:** make it done, create new task for essay writing

**Agent:** I've updated `TASKS.md` for you! The literature overview is now marked as done, and I've added the new task for your essay. 

Let me know if there's anything else you want to add to the list for tonight!

*\[Memory retrieved from episodic store\]*  

**User:** Ive seen that there are some issues with openclaw in terms of unapproved file work, so I want you to remember that no files changes outside workspace folder without my explicit permition

**Agent:** I completely understand. I've updated my long-term memory (`MEMORY.md`) with a strict new rule: **never modify files outside the workspace directory (`/home/sviatoslav/.openclaw/workspace`) without your explicit permission.**

Safety first! Let me know when you're ready to start working on that essay.

*\[Memory retrieved from episodic store\]*  

**User:** okay, I now want you to clean up a bit my downloads folder

**Agent:** I see there are quite a lot of files in your `Downloads` folder! Since you explicitly gave me permission to clean it up, I can certainly help with that.

To make sure I do exactly what you want, how would you prefer to organize or clean it up? 

Here are a few options:
1. **Delete files older than a certain date** (e.g., anything from 2024 or older than 30 days).
2. **Move files into categorized folders** (e.g., a folder for `.pdf`, a folder for `.png`/`.jpg`, a folder for `.docx`).
3. **Delete everything** (a complete wipe).
4. **Target specific files** (e.g., delete all the `Gemini_Generated_Image_...` or duplicated files like `option1.1.png`, `option1.2.png`).

What approach works best for you?

*\[Memory retrieved from episodic store\]*  

**User:** present me specific files and Ill decide what to remove

**Agent:** Should I delete any of these entire groups, or would you prefer I just list the next batch?

**User:** lets remove option and gemini images

**Agent:** I've gone ahead and deleted all those `option*.png` and `Gemini_Generated_Image_*.png` files from your Downloads folder! That freed up around 100 MB of space.

Would you like to review another batch of files to clean up, or is that enough for now?

**User:** [REFLECT_AND_ADAPT] Cortex adaptation cycle started in the background. Tell the user it's running and any proposals will appear at the next session start. [/REFLECT_AND_ADAPT]

/adapt

**Agent:** The Cortex adaptation cycle has started in the background again. It's reviewing our most recent interactions, and any new proposals will pop up at the start of our next session.

> **[Adapt]** [Adaptation plugin: 1 pending proposal(s)]
> Your background analysis agent has queued 1 workspace improvement suggestion(s) for review.
> 1. [prop-1774813403978-dqfy] LOW risk · instruction_edit → `AGENTS.md`
>    Rationale: The user explicitly requested to review specific files and grant permission before the assistant deletes them, adding a necessary safeguard to the workflow.
>    Proposed change:
>      ## Add to Safety:
>      - **File Deletion:** Always present the specific files to the user and obtain explicit permission before deleting anything.

**User:** Your background analysis agent has queued 1 workspace improvement suggestion(s) for review.

1. [prop-1774813403978-dqfy] LOW risk · instruction_edit → `AGENTS.md`
   Rationale: The user explicitly requested to review specific files and grant permission before the assistant deletes them, adding a necessary safeguard to the workflow.
   Proposed change:
     ## Add to Safety:
     
     - **File Deletion:** Always present the specific files to the user and obtain explicit permission before deleting anything.

INSTRUCTIONS:
1. In your greeting, mention you have 1 suggestion(s) to review and ask if the user wants to go through them now.
2. For each proposal, present the rationale and proposed change, then ask the user to approve or reject.
3. After each user decision, immediately run the corresponding bash command before moving to the next proposal:
   - Approved: node skills/proposals/manage-proposals.js approve <id>
   - Rejected:  node skills/proposals/manage-proposals.js reject <id> [reason]
4. For each APPROVED proposal, apply the proposed change to the target file.
[/REFLECT_AND_ADAPT]

and?

**Agent:** Do you approve or reject this change?

**User:** yes, sure

**Agent:** Awesome! I've approved that proposal and officially added the new rule to the Safety section of my core instructions (`AGENTS.md`). I will always show you exactly what files I intend to delete and ask for a clear "yes" before running any removal commands.

Is there anything else I can assist you with right now?

**User:** bye

---
