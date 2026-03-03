"""Tool module for graph canvas operations."""

from typing import Any

__amplifier_module_type__ = "tool"


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the graph canvas tool into the Amplifier coordinator.

    Called by Kepler when loading the module via its entry point.  Creates a
    :class:`~tool_graph_canvas.tool.GraphCanvasTool` and registers it with the
    coordinator under the ``tools`` mount point.

    Args:
        coordinator: Amplifier coordinator (provides ``coordinator.mount``).
        config: Module configuration dict.  Recognised keys:
            - ``transport``: a transport object with an ``emit(delta)`` method
              (optional; defaults to ``None`` / no-broadcast mode).
    """
    from .tool import GraphCanvasTool

    config = config or {}
    transport = config.get("transport")
    tool = GraphCanvasTool(config=config, transport=transport)
    await coordinator.mount("tools", tool, name=tool.name)
