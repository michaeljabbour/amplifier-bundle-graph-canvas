"""Amplifier Hook module -- observes kernel events and emits graph deltas."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from .event_mapper import map_event

logger = logging.getLogger(__name__)


class GraphCanvasTransport(ABC):
    """Abstract base for delta transports."""

    @abstractmethod
    async def emit(self, delta: dict) -> None:
        """Emit a graph delta."""

    @abstractmethod
    async def close(self) -> None:
        """Close the transport."""


class JsonlTransport(GraphCanvasTransport):
    """Writes deltas as dicts to an in-memory list (for testing/CLI fallback)."""

    def __init__(self, output: list[dict] | None = None) -> None:
        self._output: list[dict] = output if output is not None else []

    async def emit(self, delta: dict) -> None:
        self._output.append(delta)

    async def close(self) -> None:
        pass


class WebSocketTransport(GraphCanvasTransport):
    """Placeholder transport for Kepler WebSocket integration."""

    def __init__(self, send_func: Callable | None = None) -> None:
        self._send_func = send_func

    async def emit(self, delta: dict) -> None:
        if self._send_func is None:
            return
        try:
            await self._send_func(json.dumps(delta))
        except Exception:
            logger.warning("WebSocketTransport send failed", exc_info=True)

    async def close(self) -> None:
        pass


class GraphCanvasHook:
    """Amplifier Hook: observes kernel events and emits graph deltas."""

    def __init__(
        self,
        config: dict,
        transport: GraphCanvasTransport | None = None,
    ) -> None:
        self._skip_subsessions: bool = config.get("skip_subsessions", True)
        self._throttle_ms: int = config.get("throttle_ms", 100)
        self._transport: GraphCanvasTransport = transport or JsonlTransport()
        self._last_content_emit: float = 0.0

    async def __call__(self, event: str, data: dict, **kwargs: object) -> dict:
        """Process a kernel event. Always returns {"action": "continue"}."""
        try:
            await self._handle(event, data)
        except Exception:
            logger.warning("GraphCanvasHook error handling %s", event, exc_info=True)
        return {"action": "continue"}

    async def _handle(self, event: str, data: dict) -> None:
        # Skip subsession events if configured
        if self._skip_subsessions and data.get("parent_id"):
            return

        # Throttle content_block:delta events
        if event == "content_block:delta":
            now = time.monotonic() * 1000  # ms
            if now - self._last_content_emit < self._throttle_ms:
                return
            self._last_content_emit = now

        delta = map_event(event, data)
        if delta is None:
            return

        await self._transport.emit(delta)
