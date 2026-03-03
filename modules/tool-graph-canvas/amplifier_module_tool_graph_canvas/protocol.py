"""Canonical graph data model shared by all modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EdgeType(Enum):
    """Type of connection between nodes."""

    DATA_FLOW = "data_flow"
    DEPENDENCY = "dependency"


class DeltaAction(Enum):
    """Actions that can be applied to a graph."""

    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    UPDATE_NODE = "update_node"
    ADD_EDGE = "add_edge"
    REMOVE_EDGE = "remove_edge"
    CLEAR = "clear"


@dataclass
class NodeSlot:
    """A typed input or output slot on a node."""

    name: str
    type: str

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type}

    @classmethod
    def from_dict(cls, data: dict) -> NodeSlot:
        return cls(name=data["name"], type=data["type"])


@dataclass
class Node:
    """A node in the graph."""

    id: str
    type: str
    x: float
    y: float
    title: str | None = None
    properties: dict = field(default_factory=dict)
    inputs: list[NodeSlot] = field(default_factory=list)
    outputs: list[NodeSlot] = field(default_factory=list)
    modifiers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "title": self.title,
            "properties": self.properties,
            "inputs": [s.to_dict() for s in self.inputs],
            "outputs": [s.to_dict() for s in self.outputs],
            "modifiers": self.modifiers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        return cls(
            id=data["id"],
            type=data["type"],
            x=data["x"],
            y=data["y"],
            title=data.get("title"),
            properties=data.get("properties", {}),
            inputs=[NodeSlot.from_dict(s) for s in data.get("inputs", [])],
            outputs=[NodeSlot.from_dict(s) for s in data.get("outputs", [])],
            modifiers=data.get("modifiers", {}),
        )


@dataclass
class Edge:
    """A connection between two node slots."""

    id: str
    from_node: str
    from_slot: int
    to_node: str
    to_slot: int
    edge_type: EdgeType = EdgeType.DATA_FLOW

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_node": self.from_node,
            "from_slot": self.from_slot,
            "to_node": self.to_node,
            "to_slot": self.to_slot,
            "edge_type": self.edge_type.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Edge:
        return cls(
            id=data["id"],
            from_node=data["from_node"],
            from_slot=data["from_slot"],
            to_node=data["to_node"],
            to_slot=data["to_slot"],
            edge_type=EdgeType(data.get("edge_type", "data_flow")),
        )


@dataclass
class Graph:
    """A collection of nodes and edges with CRUD operations."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Node '{node.id}' already exists")
        self.nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise KeyError(node_id)
        del self.nodes[node_id]
        # Cascade: remove all connected edges
        to_remove = [
            eid
            for eid, edge in self.edges.items()
            if edge.from_node == node_id or edge.to_node == node_id
        ]
        for eid in to_remove:
            del self.edges[eid]

    def add_edge(self, edge: Edge) -> None:
        if edge.id in self.edges:
            raise ValueError(f"Edge '{edge.id}' already exists")
        if edge.from_node not in self.nodes:
            raise KeyError(edge.from_node)
        if edge.to_node not in self.nodes:
            raise KeyError(edge.to_node)
        self.edges[edge.id] = edge

    def remove_edge(self, edge_id: str) -> None:
        if edge_id not in self.edges:
            raise KeyError(edge_id)
        del self.edges[edge_id]

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Graph:
        g = cls()
        for nd in data.get("nodes", []):
            node = Node.from_dict(nd)
            g.nodes[node.id] = node
        for ed in data.get("edges", []):
            edge = Edge.from_dict(ed)
            g.edges[edge.id] = edge
        return g


@dataclass
class Delta:
    """A single change operation on a graph."""

    action: DeltaAction
    target_id: str | None = None
    data: dict | None = None

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "target_id": self.target_id,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Delta:
        return cls(
            action=DeltaAction(data["action"]),
            target_id=data.get("target_id"),
            data=data.get("data"),
        )
