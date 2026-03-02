"""Hooks module for graph canvas lifecycle events."""


def mount(config: dict | None = None):
    from .hook import GraphCanvasHook, JsonlTransport

    config = config or {}
    transport = config.get("transport") or JsonlTransport()
    return GraphCanvasHook(config=config, transport=transport)
