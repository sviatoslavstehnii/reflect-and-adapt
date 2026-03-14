"""
User simulator powered by Claude Haiku.

Given a persona definition, scenario definition, and conversation history so far,
generates the next user message. Returns None when the task is considered complete.
"""
from __future__ import annotations

from typing import Optional

import anthropic

SYSTEM_TEMPLATE = """\
You are roleplaying as a user in a conversation with an AI assistant (openclaw).
You MUST stay in character at all times.

== PERSONA ==
{persona_background}

== COMMUNICATION STYLE ==
{persona_style}

== SCENARIO ==
{scenario_name}

Opening prompt (already sent — do not repeat it):
{opening_prompt}

== YOUR GOAL ==
Complete the task described in the scenario through natural conversation.
Express the following signals/push-backs naturally when the situation warrants:
{signals}

== RULES ==
1. Write ONLY your next message — no narration, no meta-commentary.
2. Stay in character. Use the persona's vocabulary and tone exactly.
3. Keep messages realistic — 1–4 sentences unless the scenario needs more.
4. When the task is clearly finished and you have what you need, output exactly:
   <TASK_COMPLETE>
5. Do not output <TASK_COMPLETE> until the task is genuinely done.
6. Do not invent information about files that aren't in the scenario.
7. React naturally to what the agent just said — don't ignore it.
"""


class UserSimulator:
    def __init__(self, persona: dict, scenario: dict, model: str = "claude-haiku-4-5-20251001"):
        self._persona = persona
        self._scenario = scenario
        self._model = model
        self._client = anthropic.Anthropic()
        self._history: list[dict] = []
        self._system = SYSTEM_TEMPLATE.format(
            persona_background=persona.get("background", ""),
            persona_style=persona.get("communication_style", ""),
            scenario_name=scenario.get("name", ""),
            opening_prompt=scenario.get("opening_prompt", "").strip(),
            signals=_format_signals(scenario.get("signals_to_express", [])),
        )

    def record_agent_response(self, text: str) -> None:
        """Add an agent response to history before generating next user turn."""
        self._history.append({"role": "assistant", "content": text})

    async def next_message(self) -> Optional[str]:
        """
        Generate the next user message. Returns None if task is complete.
        Call record_agent_response() before calling this after the first turn.
        """
        import asyncio

        # Run the synchronous Anthropic call in a thread to keep async clean
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._generate)
        return result

    def _generate(self) -> Optional[str]:
        messages = list(self._history)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=self._system,
            messages=messages,
        )
        text = response.content[0].text.strip()

        if "<TASK_COMPLETE>" in text:
            return None

        # Add our own turn to history
        self._history.append({"role": "user", "content": text})
        return text

    @property
    def opening_prompt(self) -> str:
        """The first message to send (from scenario.yaml)."""
        msg = self._scenario.get("opening_prompt", "").strip()
        self._history.append({"role": "user", "content": msg})
        return msg


def _format_signals(signals) -> str:
    if not signals:
        return "(none)"
    if isinstance(signals, list):
        return "\n".join(f"- {s}" for s in signals)
    return str(signals)
