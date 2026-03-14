"""
OpenClaw WebSocket client.

Protocol:
  1. Connect → receive {type:"connect.challenge", nonce, deviceId}
  2. Sign nonce with device RSA private key
  3. Send {type:"connect", deviceId, signature}
  4. Receive {type:"hello-ok"}
  5. Send {type:"chat.send", sessionKey, message}
  6. Stream {type:"chat", ...} events until turn.status=="done" or silence timeout
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import AsyncIterator

import websockets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def _load_device_key(openclaw_dir: str) -> tuple[str, bytes]:
    """Load deviceId and private key PEM from identity/device.json."""
    identity_path = Path(os.path.expanduser(openclaw_dir)) / "identity" / "device.json"
    if not identity_path.exists():
        # Fallback: look inside workspace/.openclaw/
        identity_path = (
            Path(os.path.expanduser(openclaw_dir))
            / "workspace" / ".openclaw" / "identity" / "device.json"
        )
    with open(identity_path) as f:
        data = json.load(f)
    device_id: str = data["deviceId"]
    private_key_pem: bytes = data["privateKey"].encode()
    return device_id, private_key_pem


def _sign_nonce(nonce_b64: str, private_key_pem: bytes) -> str:
    """Sign a base64-encoded nonce with RSA-SHA256, return base64 signature."""
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    nonce_bytes = base64.b64decode(nonce_b64)
    signature = private_key.sign(nonce_bytes, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


class ChatCollector:
    """Collects streaming chat events into a single response string."""

    def __init__(self, silence_timeout_s: float = 15.0):
        self.silence_timeout_s = silence_timeout_s
        self._chunks: list[str] = []
        self._done = asyncio.Event()

    def feed(self, event: dict) -> None:
        """Process one incoming WebSocket event."""
        t = event.get("type", "")

        if t == "chat":
            payload = event.get("payload", event)
            # Text delta
            delta = payload.get("delta") or payload.get("text") or ""
            if delta:
                self._chunks.append(delta)
            # Turn completion signal
            status = payload.get("status") or payload.get("turnStatus") or ""
            if status == "done":
                self._done.set()

        elif t == "turn.done" or t == "agent.done":
            self._done.set()

        elif t == "error":
            self._done.set()

    @property
    def text(self) -> str:
        return "".join(self._chunks)

    async def wait(self) -> str:
        try:
            await asyncio.wait_for(self._done.wait(), timeout=self.silence_timeout_s)
        except asyncio.TimeoutError:
            pass  # silence timeout — treat as done
        return self.text


class OpenClawClient:
    """Async context manager that owns one authenticated WebSocket connection."""

    def __init__(self, port: int, openclaw_dir: str, silence_timeout_s: float = 15.0):
        self.port = port
        self.openclaw_dir = openclaw_dir
        self.silence_timeout_s = silence_timeout_s
        self._ws = None
        self._listener_task: asyncio.Task | None = None
        self._collectors: dict[str, ChatCollector] = {}
        self._active_run_id: str | None = None

    async def __aenter__(self) -> "OpenClawClient":
        await self._connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self._disconnect()

    async def _connect(self) -> None:
        uri = f"ws://localhost:{self.port}/ws"
        self._ws = await websockets.connect(uri)

        # Step 1: receive challenge
        raw = await self._ws.recv()
        challenge = json.loads(raw)
        assert challenge.get("type") == "connect.challenge", f"Expected connect.challenge, got: {challenge}"

        nonce = challenge["nonce"]
        device_id = challenge.get("deviceId")

        # Step 2: load key and sign
        loaded_device_id, private_key_pem = _load_device_key(self.openclaw_dir)
        if not device_id:
            device_id = loaded_device_id

        signature = _sign_nonce(nonce, private_key_pem)

        # Step 3: send connect
        await self._ws.send(json.dumps({
            "type": "connect",
            "deviceId": device_id,
            "signature": signature,
        }))

        # Step 4: receive hello-ok
        raw = await self._ws.recv()
        hello = json.loads(raw)
        assert hello.get("type") == "hello-ok", f"Expected hello-ok, got: {hello}"

        # Start background listener
        self._listener_task = asyncio.create_task(self._listen())

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
        """Background task: route incoming events to the active collector."""
        async for raw in self._ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            run_id = event.get("runId") or self._active_run_id
            if run_id and run_id in self._collectors:
                self._collectors[run_id].feed(event)

    async def send_message(self, session_key: str, message: str) -> str:
        """
        Send a message and return the full agent response text.
        Blocks until turn is complete (done event or silence timeout).
        """
        collector = ChatCollector(self.silence_timeout_s)

        # Unique run tracking via sessionKey-based UUID
        run_id = str(uuid.uuid4())[:8]
        self._active_run_id = run_id
        self._collectors[run_id] = collector

        payload = {
            "type": "chat.send",
            "sessionKey": session_key,
            "message": message,
        }
        await self._ws.send(json.dumps(payload))

        # Read immediate ack to get real runId
        raw = await self._ws.recv()
        ack = json.loads(raw)
        real_run_id = ack.get("runId", run_id)

        if real_run_id != run_id:
            # Re-register collector under real runId
            self._collectors[real_run_id] = collector
            del self._collectors[run_id]
            self._active_run_id = real_run_id

        response = await collector.wait()

        # Clean up
        self._collectors.pop(real_run_id, None)
        self._active_run_id = None

        return response
