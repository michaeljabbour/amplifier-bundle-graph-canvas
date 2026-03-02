"""Amplifier Tool module -- LLM-callable graph manipulation tool."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from graph_canvas_compiler import compile_graph, decompile_recipe

from .graph_state import GraphState

logger = logging.getLogger(__name__)


@runtime_checkable
class Transport(Protocol):
    """Protocol for transport objects that broadcast mutation deltas."""

    async def emit(self, delta: dict[str, Any]) -> None: ...


_ACTIONS = [
    "get_graph_state",
    "get_node_types",
    "add_node",
    "remove_node",
    "set_node_property",
    "connect_nodes",
    "disconnect",
    "clear_graph",
    "compile_recipe",
    "load_recipe",
    "execute_graph",
]


class GraphCanvasTool:
    """LLM-callable tool for graph canvas manipulation."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._config = config or {}
        self._state = GraphState()
        self._transport = transport

    async def _broadcast(self, delta: str | dict[str, Any]) -> None:
        """Emit a mutation delta via transport, if available. Fire-and-forget."""
        if self._transport is not None and isinstance(delta, dict):
            try:
                await self._transport.emit(delta)
            except Exception:
                logger.debug("transport.emit failed", exc_info=True)

    @property
    def name(self) -> str:
        return "graph_canvas"

    @property
    def description(self) -> str:
        return (
            "Manipulate a visual node graph for building Amplifier recipes. "
            "Supports adding/removing nodes, connecting them, setting properties, "
            "compiling to recipe YAML, and loading existing recipes."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": _ACTIONS,
                    "description": "The action to perform on the graph canvas.",
                },
                "type": {
                    "type": "string",
                    "description": "Node type (for add_node).",
                },
                "x": {
                    "type": "number",
                    "description": "X position (for add_node).",
                },
                "y": {
                    "type": "number",
                    "description": "Y position (for add_node).",
                },
                "title": {
                    "type": "string",
                    "description": "Node title (for add_node).",
                },
                "properties": {
                    "type": "object",
                    "description": "Node properties (for add_node).",
                },
                "node_id": {
                    "type": "string",
                    "description": "Node ID (for remove_node, set_node_property).",
                },
                "property": {
                    "type": "string",
                    "description": "Property name (for set_node_property).",
                },
                "value": {
                    "description": "Property value (for set_node_property).",
                },
                "from_id": {
                    "type": "string",
                    "description": "Source node ID (for connect_nodes).",
                },
                "from_slot": {
                    "type": "integer",
                    "description": "Source slot index (for connect_nodes).",
                },
                "to_id": {
                    "type": "string",
                    "description": "Target node ID (for connect_nodes).",
                },
                "to_slot": {
                    "type": "integer",
                    "description": "Target slot index (for connect_nodes).",
                },
                "edge_type": {
                    "type": "string",
                    "description": "Edge type (for connect_nodes). Default: data_flow.",
                },
                "edge_id": {
                    "type": "string",
                    "description": "Edge ID (for disconnect).",
                },
                "category": {
                    "type": "string",
                    "description": "Category filter (for get_node_types).",
                },
                "yaml": {
                    "type": "string",
                    "description": "Recipe YAML string (for load_recipe).",
                },
                "name": {
                    "type": "string",
                    "description": "Recipe name (for compile_recipe).",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self, *, arguments: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Dispatch to the appropriate action handler."""
        action = arguments.get("action", "")

        try:
            if action == "get_graph_state":
                return {"result": self._state.get_state()}

            elif action == "get_node_types":
                category = arguments.get("category")
                types = self._state.get_node_types(category=category)
                return {"result": types}

            elif action == "add_node":
                node_id, delta = self._state.add_node(
                    type=arguments["type"],
                    x=arguments.get("x", 0.0),
                    y=arguments.get("y", 0.0),
                    title=arguments.get("title"),
                    properties=arguments.get("properties"),
                    _with_delta=True,
                )
                result = {"result": {"node_id": node_id}, "delta": delta}
                await self._broadcast(delta)
                return result

            elif action == "remove_node":
                delta = self._state.remove_node(arguments["node_id"])
                result = {"result": {"removed": arguments["node_id"]}, "delta": delta}
                await self._broadcast(delta)
                return result

            elif action == "set_node_property":
                delta = self._state.set_node_property(
                    arguments["node_id"],
                    arguments["property"],
                    arguments["value"],
                )
                result = {"result": {"updated": arguments["node_id"]}, "delta": delta}
                await self._broadcast(delta)
                return result

            elif action == "connect_nodes":
                edge_id, delta = self._state.connect_nodes(
                    from_id=arguments["from_id"],
                    from_slot=arguments.get("from_slot", 0),
                    to_id=arguments["to_id"],
                    to_slot=arguments.get("to_slot", 0),
                    edge_type=arguments.get("edge_type", "data_flow"),
                    _with_delta=True,
                )
                result = {"result": {"edge_id": edge_id}, "delta": delta}
                await self._broadcast(delta)
                return result

            elif action == "disconnect":
                delta = self._state.disconnect(arguments["edge_id"])
                result = {"result": {"removed": arguments["edge_id"]}, "delta": delta}
                await self._broadcast(delta)
                return result

            elif action == "clear_graph":
                delta = self._state.clear()
                result = {"result": {"cleared": True}, "delta": delta}
                await self._broadcast(delta)
                return result

            elif action == "compile_recipe":
                graph_dict = self._state.get_state()
                recipe_name = arguments.get("name", "untitled")
                yaml_str = compile_graph(graph_dict, name=recipe_name)
                return {"result": {"yaml": yaml_str}}

            elif action == "load_recipe":
                yaml_str = arguments["yaml"]
                graph_dict = decompile_recipe(yaml_str)
                # Replace current state
                self._state = GraphState()
                self._state._graph = self._state._graph.from_dict(graph_dict)
                return {
                    "result": {
                        "loaded": True,
                        "node_count": len(graph_dict.get("nodes", [])),
                    }
                }

            elif action == "execute_graph":
                return {
                    "result": {
                        "status": "not_implemented",
                        "message": "Graph execution requires client-side litegraph.js engine",
                    }
                }

            else:
                return {"error": f"Unknown action: {action}"}

        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}
