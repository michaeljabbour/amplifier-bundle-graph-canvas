"""Tool module for graph canvas operations."""


def mount(config: dict | None = None):
    from .tool import GraphCanvasTool

    config = config or {}
    transport = config.get("transport")
    return GraphCanvasTool(config=config, transport=transport)
