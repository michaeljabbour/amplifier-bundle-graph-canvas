"""Maps Amplifier kernel events to graph delta dicts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone


def _timestamp(data: dict) -> str:
    """Extract timestamp from data or generate one."""
    return data.get("timestamp") or datetime.now(timezone.utc).isoformat()


def _node_id_from(data: dict) -> str:
    """Extract a node ID from event data, tolerating missing keys."""
    return data.get("request_id") or data.get("session_id", "unknown")


def _map_provider_request(data: dict) -> dict:
    return {
        "event": "provider:request",
        "action": "add_node",
        "node_id": _node_id_from(data),
        "data": {
            "type": "llm_turn",
            "status": "thinking",
            "model": data.get("model"),
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_provider_response(data: dict) -> dict:
    return {
        "event": "provider:response",
        "action": "update_node",
        "node_id": _node_id_from(data),
        "data": {
            "status": "complete",
            "usage": data.get("usage"),
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_content_block_delta(data: dict) -> dict:
    return {
        "event": "content_block:delta",
        "action": "update_node",
        "node_id": _node_id_from(data),
        "data": {
            "streaming": True,
            "delta": data.get("delta"),
        },
        "detail_level": "drill_down",
        "timestamp": _timestamp(data),
    }


def _map_tool_pre(data: dict) -> dict:
    return {
        "event": "tool:pre",
        "action": "add_node",
        "node_id": data["tool_use_id"],
        "data": {
            "type": data.get("tool_name", "unknown_tool"),
            "status": "executing",
        },
        "edge": {
            "from_node": _node_id_from(data),
            "to_node": data["tool_use_id"],
            "edge_type": "data_flow",
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_tool_post(data: dict) -> dict:
    result = data.get("result", "")
    preview = result[:200] if isinstance(result, str) else str(result)[:200]
    return {
        "event": "tool:post",
        "action": "update_node",
        "node_id": data["tool_use_id"],
        "data": {
            "status": "complete",
            "result_preview": preview,
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_tool_error(data: dict) -> dict:
    return {
        "event": "tool:error",
        "action": "update_node",
        "node_id": data["tool_use_id"],
        "data": {
            "status": "error",
            "error": data.get("error"),
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_session_spawn(data: dict) -> dict:
    return {
        "event": "session:spawn",
        "action": "add_node",
        "node_id": data["session_id"],
        "data": {
            "type": "agent_spawn",
            "collapsed": True,
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_session_complete(data: dict) -> dict:
    return {
        "event": "session:complete",
        "action": "update_node",
        "node_id": data["session_id"],
        "data": {
            "status": "complete",
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_recipe_step_start(data: dict) -> dict:
    return {
        "event": "recipe:step:start",
        "action": "add_node",
        "node_id": data["step_id"],
        "data": {
            "type": "recipe_step",
            "step_name": data.get("step_name"),
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


def _map_recipe_step_complete(data: dict) -> dict:
    return {
        "event": "recipe:step:complete",
        "action": "update_node",
        "node_id": data["step_id"],
        "data": {
            "status": "complete",
        },
        "detail_level": "high",
        "timestamp": _timestamp(data),
    }


_EVENT_HANDLERS: dict[str, Callable] = {
    "provider:request": _map_provider_request,
    "provider:response": _map_provider_response,
    "content_block:delta": _map_content_block_delta,
    "tool:pre": _map_tool_pre,
    "tool:post": _map_tool_post,
    "tool:error": _map_tool_error,
    "session:spawn": _map_session_spawn,
    "session:complete": _map_session_complete,
    "recipe:step:start": _map_recipe_step_start,
    "recipe:step:complete": _map_recipe_step_complete,
}


def map_event(event: str, data: dict) -> dict | None:
    """Convert a kernel event to a graph delta dict.

    Returns None for unrecognized events (forward-compatible).
    """
    handler = _EVENT_HANDLERS.get(event)
    if handler is None:
        return None
    return handler(data)
