"""Tool module for graph canvas operations."""


def mount(config: dict | None = None):
    from .tool import GraphCanvasTool

    return GraphCanvasTool(config=config or {})
