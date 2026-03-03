"""Hooks module for graph canvas lifecycle events."""

from typing import Any

__amplifier_module_type__ = "hook"

# Events handled by GraphCanvasHook (mirrors event_mapper._EVENT_HANDLERS keys)
_HOOK_EVENTS = [
    "provider:request",
    "provider:response",
    "content_block:delta",
    "tool:pre",
    "tool:post",
    "tool:error",
    "session:spawn",
    "session:complete",
    "recipe:step:start",
    "recipe:step:complete",
]


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the graph canvas hook into the Amplifier coordinator.

    Called by Kepler when loading the module via its entry point.  Creates a
    :class:`~hooks_graph_canvas.hook.GraphCanvasHook` and registers it for
    every event that the hook understands.

    Args:
        coordinator: Amplifier coordinator (provides ``coordinator.hooks.register``).
        config: Module configuration dict.  Recognised keys:
            - ``transport``: a :class:`~hooks_graph_canvas.hook.GraphCanvasTransport`
              instance (defaults to :class:`~hooks_graph_canvas.hook.JsonlTransport`).
            - ``skip_subsessions``: bool (default ``True``).
            - ``throttle_ms``: int (default ``100``).
    """
    from .hook import GraphCanvasHook, JsonlTransport

    config = config or {}
    transport = config.get("transport") or JsonlTransport()
    clean_config = {k: v for k, v in config.items() if k != "transport"}
    hook = GraphCanvasHook(config=clean_config, transport=transport)

    for event_name in _HOOK_EVENTS:
        coordinator.hooks.register(event_name, hook)
