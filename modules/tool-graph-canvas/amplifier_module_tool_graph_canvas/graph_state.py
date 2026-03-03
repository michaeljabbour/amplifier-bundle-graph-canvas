"""In-process graph state manager with CRUD operations and delta emission."""

from __future__ import annotations

import uuid
from typing import Any

from amplifier_module_graph_canvas_compiler.schema import CompileError, get_node_type, list_node_types

from .protocol import DeltaAction, Edge, EdgeType, Graph, Node, NodeSlot


class GraphState:
    """Maintains a graph and provides CRUD operations with delta emission."""

    def __init__(self) -> None:
        self._graph = Graph()
        self._metadata: dict[str, Any] = {}

    def get_state(self) -> dict[str, Any]:
        """Return the full graph as a dict."""
        result = self._graph.to_dict()
        result["metadata"] = dict(self._metadata)
        return result

    def add_node(
        self,
        type: str,
        x: float,
        y: float,
        title: str | None = None,
        properties: dict[str, Any] | None = None,
        *,
        _with_delta: bool = False,
    ) -> str | tuple[str, dict[str, Any]]:
        """Create a node, return node_id. With _with_delta=True, return (node_id, delta)."""
        # Validate type against schema registry
        try:
            spec = get_node_type(type)
        except CompileError as exc:
            raise ValueError(str(exc)) from None

        node_id = uuid.uuid4().hex

        # Build inputs/outputs from schema spec
        inputs = [NodeSlot(name=s.name, type=s.type) for s in spec.inputs]
        outputs = [NodeSlot(name=s.name, type=s.type) for s in spec.outputs]

        # Merge default properties from spec with user-provided ones
        merged_props = dict(spec.properties)
        if properties:
            merged_props.update(properties)

        node = Node(
            id=node_id,
            type=type,
            x=x,
            y=y,
            title=title or spec.title,
            properties=merged_props,
            inputs=inputs,
            outputs=outputs,
        )
        self._graph.add_node(node)

        delta = {
            "action": DeltaAction.ADD_NODE.value,
            "target_id": node_id,
            "data": node.to_dict(),
        }

        if _with_delta:
            return node_id, delta
        return node_id

    def remove_node(self, node_id: str) -> dict[str, Any]:
        """Remove a node and its connected edges. Returns delta."""
        # Graph.remove_node raises KeyError if not found
        self._graph.remove_node(node_id)
        return {
            "action": DeltaAction.REMOVE_NODE.value,
            "target_id": node_id,
            "data": None,
        }

    def set_node_property(
        self, node_id: str, property: str, value: Any
    ) -> dict[str, Any]:
        """Set a property on a node. Returns delta."""
        if node_id not in self._graph.nodes:
            raise KeyError(node_id)
        self._graph.nodes[node_id].properties[property] = value
        return {
            "action": DeltaAction.UPDATE_NODE.value,
            "target_id": node_id,
            "data": {"property": property, "value": value},
        }

    def connect_nodes(
        self,
        from_id: str,
        from_slot: int,
        to_id: str,
        to_slot: int,
        edge_type: str = "data_flow",
        *,
        _with_delta: bool = False,
    ) -> str | tuple[str, dict[str, Any]]:
        """Create an edge between two nodes. Returns edge_id or (edge_id, delta)."""
        edge_id = uuid.uuid4().hex
        edge = Edge(
            id=edge_id,
            from_node=from_id,
            from_slot=from_slot,
            to_node=to_id,
            to_slot=to_slot,
            edge_type=EdgeType(edge_type),
        )
        # Graph.add_edge raises KeyError if from_node or to_node missing
        self._graph.add_edge(edge)

        delta = {
            "action": DeltaAction.ADD_EDGE.value,
            "target_id": edge_id,
            "data": edge.to_dict(),
        }

        if _with_delta:
            return edge_id, delta
        return edge_id

    def disconnect(self, edge_id: str) -> dict[str, Any]:
        """Remove an edge. Returns delta."""
        # Graph.remove_edge raises KeyError if not found
        self._graph.remove_edge(edge_id)
        return {
            "action": DeltaAction.REMOVE_EDGE.value,
            "target_id": edge_id,
            "data": None,
        }

    def clear(self) -> dict[str, Any]:
        """Clear all nodes and edges. Returns delta."""
        self._graph.clear()
        return {
            "action": DeltaAction.CLEAR.value,
            "target_id": None,
            "data": None,
        }

    def get_node_types(self, category: str | None = None) -> list[dict[str, Any]]:
        """Return available node types, optionally filtered by category."""
        specs = list_node_types(category=category)
        return [s.to_dict() for s in specs]
