"""
Simulator session memory — tracks what the user has already told the agent
across prior sessions so the simulator doesn't repeat those explanations.

After each session, GPT-4.1 extracts newly communicated items from the
conversation. In the next session, the simulator knows what's already been
said and skips re-explaining it.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

log = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).resolve().parents[1] / "results" / "simulator_memory"


def load(persona_id: str, arm: str) -> list[str]:
    """Return the list of things the user has already told the agent."""
    path = MEMORY_DIR / persona_id / f"{arm}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()).get("already_told_agent", [])
    except Exception:
        return []


def _save(persona_id: str, arm: str, items: list[str]) -> None:
    path = MEMORY_DIR / persona_id / f"{arm}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"already_told_agent": items}, indent=2))


def update_from_session(
    persona_id: str,
    arm: str,
    scenario_id: str,
    turns: list,  # list[Turn] from session.py
) -> None:
    """
    Ask GPT-4.1 to extract what the user communicated to the agent in this
    session, then append new items to the memory file.
    """
    existing = load(persona_id, arm)

    conversation = "\n".join(
        f"User: {t.user_message}\nAgent: {t.agent_response}"
        for t in turns
    )

    prompt = f"""Review this conversation between a user and an AI assistant.

Extract things the USER explicitly communicated to the assistant that it should
remember going forward — style preferences, tool choices, corrections given,
constraints stated, things the user had to explain or clarify.

Rules:
- Only extract what the user said explicitly. Do not infer.
- Do not repeat anything already in the existing list.
- Prefix each item with the session id: "{scenario_id}: ..."
- Keep each item to one short sentence.
- If nothing new was communicated, return an empty list.

Existing memory:
{json.dumps(existing, indent=2)}

Conversation:
{conversation}

Return JSON only, no explanation: {{"new_items": ["..."]}}"""

    try:
        client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-05-01-preview"),
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        )
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        new_items = json.loads(raw).get("new_items", [])
        if new_items:
            _save(persona_id, arm, existing + new_items)
            log.info(f"[sim-memory] +{len(new_items)} item(s) after {scenario_id}")
        else:
            log.info(f"[sim-memory] Nothing new to add after {scenario_id}")
    except Exception as e:
        log.warning(f"[sim-memory] Extraction failed: {e}")


def build_prompt_block(items: list[str]) -> str:
    """
    Return the memory block to prepend to the simulator system prompt.
    Returns empty string if no items (s01 cold start).
    """
    if not items:
        return ""
    lines = "\n".join(f"- {item}" for item in items)
    return f"""\
== YOUR MEMORY OF PRIOR SESSIONS ==
You have worked with this assistant before. In previous sessions you already told it:

{lines}

Do NOT re-explain these things in this session — assume the agent knows them.
If the agent demonstrates it already knows → proceed naturally.
If the agent asks about something you already told it, or ignores it → respond
briefly with mild frustration ("I thought we covered this" / "like I mentioned before")
then give a short reminder, not a full re-explanation.
====================================

"""
