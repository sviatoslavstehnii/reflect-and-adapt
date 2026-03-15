"""
User simulator powered by Azure OpenAI GPT-4.1 (Qwen 3.5 Plus as fallback).

Given a persona definition, scenario definition, and conversation history so far,
generates the next user message. Returns None when the task is considered complete.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

log = logging.getLogger(__name__)

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
Complete the task described in the scenario through natural, iterative conversation.
You are an active collaborator — you review what the agent produces and request changes.
You MUST express ALL of the following feedback/actions during the conversation:
{signals}

== RULES ==
1. Write ONLY your next message — no narration, no meta-commentary.
2. Stay in character. Use the persona's vocabulary and tone exactly.
3. Keep messages realistic — 1–4 sentences unless the scenario needs more.
4. ALWAYS react to something SPECIFIC the agent just wrote — quote a word or phrase,
   name a section, ask about a specific part. Never respond generically.
5. On the first draft: pick at least one signal from the list and express it naturally.
6. On subsequent drafts: express another signal you haven't expressed yet, OR
   acknowledge a good change while still requesting something new.
7. Only output <TASK_COMPLETE> once you have expressed ALL signals at least once
   AND the agent has made meaningful changes. The task is NOT done on the first draft.
8. Do not invent information about files that aren't in the scenario.
"""


class UserSimulator:
    def __init__(self, persona: dict, scenario: dict, model: str = None):
        self._persona = persona
        self._scenario = scenario
        self._history: list[dict] = []
        self._last_user_msg: Optional[str] = None
        self._repeat_count: int = 0
        self._system = SYSTEM_TEMPLATE.format(
            persona_background=persona.get("background", ""),
            persona_style=persona.get("communication_style", ""),
            scenario_name=scenario.get("name", ""),
            opening_prompt=scenario.get("opening_prompt", "").strip(),
            signals=_format_signals(scenario.get("signals_to_express", [])),
        )

    # ── Provider clients ──────────────────────────────────────────────────────

    def _azure_client(self) -> AzureOpenAI:
        return AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        )

    def _qwen_client(self) -> OpenAI:
        return OpenAI(
            api_key=os.environ["QWEN_API_KEY"],
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    def _call_llm(self, messages: list[dict]) -> str:
        try:
            client = self._azure_client()
            deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
            resp = client.chat.completions.create(
                model=deployment,
                messages=messages,
                max_tokens=512,
                temperature=1.1,
            )
            return resp.choices[0].message.content or ""
        except Exception as azure_err:
            log.warning(f"Azure OpenAI failed ({azure_err}), falling back to Qwen...")
            client = self._qwen_client()
            qwen_model = os.environ.get("QWEN_MODEL", "qwen-plus")
            resp = client.chat.completions.create(
                model=qwen_model,
                messages=messages,
                max_tokens=512,
                temperature=1.1,
            )
            return resp.choices[0].message.content or ""

    # ── Public API ────────────────────────────────────────────────────────────

    def record_agent_response(self, text: str) -> None:
        """Add an agent response to history before generating next user turn."""
        self._history.append({"role": "assistant", "content": text})

    async def next_message(self) -> Optional[str]:
        """
        Generate the next user message. Returns None if task is complete.
        Call record_agent_response() before calling this after the first turn.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._generate)

    def _generate(self) -> Optional[str]:
        messages = [{"role": "system", "content": self._system}] + self._history

        raw = ""
        for attempt in range(3):
            try:
                raw = self._call_llm(messages)
                if raw:
                    break
            except Exception as e:
                log.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
        if not raw:
            raw = "Okay, that looks good. What's next?"

        text = raw.strip()
        if not text:
            text = "Okay, that looks good. What's next?"

        if "<TASK_COMPLETE>" in text:
            return None

        # Loop detection: if the same message repeats 2+ times, signal completion
        if text == self._last_user_msg:
            self._repeat_count += 1
            if self._repeat_count >= 2:
                log.info("Loop detected (same message 3x) — signalling task complete.")
                return None
        else:
            self._last_user_msg = text
            self._repeat_count = 0

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
