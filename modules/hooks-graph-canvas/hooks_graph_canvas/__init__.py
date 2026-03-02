"""Hooks module for graph canvas lifecycle events."""


def mount(config: dict | None = None):
    from .hook import GraphCanvasHook, JsonlTransport

    config = config or {}
    transport = config.get("transport") or JsonlTransport()
    clean_config = {k: v for k, v in config.items() if k != "transport"}
    return GraphCanvasHook(config=clean_config, transport=transport)
