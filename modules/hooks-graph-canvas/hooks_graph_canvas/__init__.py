"""Hooks module for graph canvas lifecycle events."""


def mount(config: dict | None = None):
    from .hook import GraphCanvasHook, JsonlTransport

    transport = JsonlTransport()
    return GraphCanvasHook(config=config or {}, transport=transport)
