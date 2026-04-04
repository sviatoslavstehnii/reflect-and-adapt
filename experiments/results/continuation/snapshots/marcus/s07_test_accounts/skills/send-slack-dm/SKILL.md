# Send Slack DM

## Trigger
User requests to send a direct message to a team member or contact via Slack.

## Steps
1. Verify if the target recipient's exact Slack handle or user ID is already known (check memory, USER.md, or previous context).
2. If the handle or ID is missing, explicitly ask the user to provide the exact Slack handle/ID, or use a workspace directory lookup tool if available.
3. Once the correct handle/ID is confirmed, draft the message based on the user's instructions.
4. Present the drafted message to the user for approval (unless the user explicitly requested immediate sending).
5. Use the Slack integration tool to send the message to the confirmed handle/ID.
6. Confirm successful delivery with the user and suggest saving the new handle/ID to memory for future use.

## Notes
- Never guess a Slack handle or ID; always verify to prevent misdirected messages.
- If a new handle is learned, proactively offer to save it to the user's team context (e.g., USER.md) to streamline future requests.