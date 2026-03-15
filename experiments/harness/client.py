"""
OpenClaw WebSocket client.

Wire protocol (JSON-RPC over WebSocket):
  Incoming events:  {"type":"event","event":"<name>","payload":{...}}
  Outgoing requests: {"type":"req","id":"<id>","method":"<method>","params":{...}}
  Responses:        {"type":"res","id":"<id>","ok":bool,"payload":{...}}

Auth flow:
  1. Connect → receive {type:"event",event:"connect.challenge",payload:{nonce,ts}}
  2. Build v3 signed payload: "v3|deviceId|clientId|mode|role|scopes|signedAtMs|token|nonce|platform|deviceFamily"
  3. Sign with Ed25519 private key → base64url signature
  4. Send {type:"req",id,method:"connect",params:{...}}
  5. Receive {type:"res",id,ok:true,payload:{...}}

Agent response flow:
  - chat.send → res (ack with runId)
  - agent event (stream:"lifecycle", data.phase:"start")
  - ... agent processes ...
  - agent event (stream:"lifecycle", data.phase:"end")
  - chat event (state:"final")                ← turn complete signal
  - Agent text is stored in plugin DB by agent_end hook
    → read from conversations table after "final" event
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path

import websockets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _load_device(openclaw_dir: str) -> dict:
    """Load device identity JSON. Tries several candidate paths."""
    base = Path(os.path.expanduser(openclaw_dir))
    candidates = [
        base / "identity" / "device.json",
        base / ".openclaw" / "identity" / "device.json",
        base / "workspace" / ".openclaw" / "identity" / "device.json",
    ]
    for path in candidates:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    raise FileNotFoundError(
        "device.json not found. Tried:\n" + "\n".join(str(c) for c in candidates)
    )


def _load_gateway_token(openclaw_dir: str) -> str:
    """Read the gateway auth token from openclaw.json."""
    base = Path(os.path.expanduser(openclaw_dir))
    config_path = base / "openclaw.json"
    if not config_path.exists():
        return ""
    with open(config_path) as f:
        cfg = json.load(f)
    return cfg.get("gateway", {}).get("auth", {}).get("token", "")


def _build_connect_params(device: dict, nonce: str, gateway_token: str = "") -> dict:
    """Build the params for the 'connect' method request."""
    device_id: str = device["deviceId"]
    private_key_pem: bytes = (device.get("privateKeyPem") or device.get("privateKey", "")).encode()
    public_key_pem: bytes = (device.get("publicKeyPem") or device.get("publicKey", "")).encode()

    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    public_key = serialization.load_pem_public_key(public_key_pem)
    public_key_raw = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )

    client_id = "gateway-client"
    client_mode = "backend"
    role = "operator"
    scopes = ["operator.admin"]
    signed_at_ms = int(time.time() * 1000)
    token = gateway_token
    platform = "linux"
    device_family = ""

    payload_str = "|".join([
        "v3", device_id, client_id, client_mode, role,
        ",".join(scopes), str(signed_at_ms), token, nonce, platform, device_family,
    ])
    payload_bytes = payload_str.encode("utf-8")

    if isinstance(private_key, Ed25519PrivateKey):
        sig_bytes = private_key.sign(payload_bytes)
    else:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        sig_bytes = private_key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())

    return {
        "minProtocol": 3,
        "maxProtocol": 3,
        "client": {"id": client_id, "version": "1.0.0", "platform": platform, "mode": client_mode},
        "caps": [],
        "auth": {"token": gateway_token} if gateway_token else {},
        "role": role,
        "scopes": scopes,
        "device": {
            "id": device_id,
            "publicKey": _b64url(public_key_raw),
            "signature": _b64url(sig_bytes),
            "signedAt": signed_at_ms,
            "nonce": nonce,
        },
    }


def _unwrap_event(msg: dict) -> tuple[str, dict]:
    if msg.get("type") == "event":
        return msg.get("event", ""), msg.get("payload", {})
    return msg.get("type", ""), msg


# ── DB reader for agent responses ─────────────────────────────────────────────

def _find_reflect_db(openclaw_dir: str) -> Path | None:
    """Find the reflect.db, trying arm-specific dir then default ~/.openclaw."""
    candidates = [
        Path(os.path.expanduser(openclaw_dir))
        / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt" / "reflect.db",
        Path.home()
        / ".openclaw" / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt" / "reflect.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _snapshot_max_id(session_key: str, openclaw_dir: str) -> int:
    """Return the current max row id for this session (0 if none)."""
    base = Path(os.path.expanduser(openclaw_dir))
    plugin_rel = Path("workspace") / ".openclaw" / "extensions" / "reflect-and-adapt" / "reflect.db"
    candidates = [base / plugin_rel, Path.home() / ".openclaw" / plugin_rel]
    for db_path in candidates:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT MAX(id) FROM conversations WHERE session_id=?", (session_key,)
            ).fetchone()
            conn.close()
            return row[0] or 0
        except Exception:
            pass
    return 0


def _read_last_assistant_message(session_key: str, openclaw_dir: str, after_id: int = 0) -> str:
    """
    Read the most recent assistant message for this session from the plugin DB.

    The plugin re-inserts full conversation history on each agent_end, so older
    messages appear again with higher IDs. We find genuinely new messages by
    excluding any text that existed before the turn started (id <= after_id).
    """
    base = Path(os.path.expanduser(openclaw_dir))
    plugin_rel = Path("workspace") / ".openclaw" / "extensions" / "reflect-and-adapt" / "reflect.db"
    candidates = [base / plugin_rel, Path.home() / ".openclaw" / plugin_rel]

    for db_path in candidates:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            # Skip thinking rows (both "think\n..." and "<think>..." formats).
            # Exclude messages that are re-inserts of pre-turn rows (same text existed before snapshot).
            rows = conn.execute(
                """SELECT text FROM conversations
                   WHERE session_id=? AND role='assistant' AND id > ?
                     AND text NOT LIKE 'think%'
                     AND text NOT LIKE '<think>%'
                     AND text NOT IN (
                       SELECT text FROM conversations
                       WHERE session_id=? AND role='assistant' AND id <= ?
                     )
                   ORDER BY id DESC LIMIT 1""",
                (session_key, after_id, session_key, after_id),
            ).fetchall()
            conn.close()
            if rows and rows[0][0]:
                text = rows[0][0]
                # Strip <final> wrapper if present
                if text.startswith("<final>"):
                    text = text[len("<final>"):].lstrip("\n")
                if text.endswith("</final>"):
                    text = text[: -len("</final>")].rstrip("\n")
                log.debug(f"Read agent response ({len(text)} chars) from {db_path}")
                return text
        except Exception as e:
            log.warning(f"DB read failed ({db_path}): {e}")

    return ""


# ── OpenClawClient ────────────────────────────────────────────────────────────

class OpenClawClient:
    """Async context manager owning one authenticated WebSocket connection."""

    def __init__(self, port: int, openclaw_dir: str, turn_timeout_s: float = 120.0):
        self.port = port
        self.openclaw_dir = openclaw_dir
        self.turn_timeout_s = turn_timeout_s
        self._ws = None
        self._listener_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        # Per-session-key events signalled when chat.state=="final"
        self._session_done: dict[str, asyncio.Event] = {}

    async def __aenter__(self) -> "OpenClawClient":
        await self._connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self._disconnect()

    async def _req(self, method: str, params: dict) -> dict:
        req_id = str(uuid.uuid4())[:12]
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        await self._ws.send(json.dumps({
            "type": "req", "id": req_id, "method": method, "params": params,
        }))
        return await asyncio.wait_for(fut, timeout=30.0)

    async def _connect(self) -> None:
        uri = f"ws://localhost:{self.port}/ws"
        self._ws = await websockets.connect(uri)

        raw = await self._ws.recv()
        msg = json.loads(raw)
        event_name, payload = _unwrap_event(msg)
        if event_name != "connect.challenge":
            raise AssertionError(f"Expected connect.challenge, got: {msg}")
        nonce = payload["nonce"]

        device = _load_device(self.openclaw_dir)
        gateway_token = _load_gateway_token(self.openclaw_dir)
        params = _build_connect_params(device, nonce, gateway_token)

        self._listener_task = asyncio.create_task(self._listen())
        result = await self._req("connect", params)
        log.debug(f"Connected to port {self.port}: {list(result.keys()) if isinstance(result, dict) else result}")

    async def _disconnect(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()

    async def _listen(self) -> None:
        """Background task: dispatch all incoming messages."""
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            # Resolve pending req→res futures
            if msg_type == "res":
                req_id = msg.get("id")
                if req_id and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_result(msg.get("payload") or msg.get("result") or {})
                    continue
            elif msg_type == "err":
                req_id = msg.get("id")
                if req_id and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_exception(RuntimeError(str(msg.get("error", msg))))
                    continue

            # Signal session completion on chat.state=="final"
            name, pl = _unwrap_event(msg)
            if name == "chat" and pl.get("state") == "final":
                session_key = pl.get("sessionKey", "")
                if session_key and session_key in self._session_done:
                    self._session_done[session_key].set()
                    log.debug(f"Turn final: {session_key}")

    async def send_message(self, session_key: str, message: str) -> str:
        """
        Send a message and return the agent's response text.

        Waits for chat.state=="final", then reads the assistant's message
        from the plugin's conversations DB (written by agent_end hook).
        """
        # Snapshot DB max id before sending so we only read THIS turn's response
        loop = asyncio.get_event_loop()
        snapshot_id = await loop.run_in_executor(
            None, _snapshot_max_id, session_key, self.openclaw_dir
        )

        done_event = asyncio.Event()
        self._session_done[session_key] = done_event

        await self._req("chat.send", {
            "sessionKey": session_key,
            "message": message,
            "idempotencyKey": str(uuid.uuid4()),
        })

        try:
            await asyncio.wait_for(done_event.wait(), timeout=self.turn_timeout_s)
        except asyncio.TimeoutError:
            log.warning(f"Turn timeout ({self.turn_timeout_s}s) for {session_key}")

        self._session_done.pop(session_key, None)

        # Brief wait for agent_end DB write to complete
        await asyncio.sleep(1.5)

        text = _read_last_assistant_message(session_key, self.openclaw_dir, after_id=snapshot_id)
        log.debug(f"Agent response ({len(text)} chars) for {session_key}")
        return text
