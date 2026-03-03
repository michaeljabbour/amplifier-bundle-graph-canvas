"""Tests for the protocol module: NodeSlot, Node, Edge, Graph, Delta dataclasses."""

import pytest

from amplifier_module_tool_graph_canvas.protocol import (
    Delta,
    DeltaAction,
    Edge,
    EdgeType,
    Graph,
    Node,
    NodeSlot,
)


# ── NodeSlot ──────────────────────────────────────────────────────────


class TestNodeSlot:
    def test_creation(self):
        slot = NodeSlot(name="input_0", type="float")
        assert slot.name == "input_0"
        assert slot.type == "float"

    def test_to_dict(self):
        slot = NodeSlot(name="color", type="vec3")
        assert slot.to_dict() == {"name": "color", "type": "vec3"}

    def test_from_dict(self):
        slot = NodeSlot.from_dict({"name": "value", "type": "int"})
        assert slot.name == "value"
        assert slot.type == "int"

    def test_round_trip(self):
        original = NodeSlot(name="texture", type="sampler2D")
        restored = NodeSlot.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.type == original.type


# ── EdgeType enum ─────────────────────────────────────────────────────


class TestEdgeType:
    def test_data_flow_value(self):
        assert EdgeType.DATA_FLOW.value == "data_flow"

    def test_dependency_value(self):
        assert EdgeType.DEPENDENCY.value == "dependency"


# ── DeltaAction enum ─────────────────────────────────────────────────


class TestDeltaAction:
    def test_all_values(self):
        assert DeltaAction.ADD_NODE.value == "add_node"
        assert DeltaAction.REMOVE_NODE.value == "remove_node"
        assert DeltaAction.UPDATE_NODE.value == "update_node"
        assert DeltaAction.ADD_EDGE.value == "add_edge"
        assert DeltaAction.REMOVE_EDGE.value == "remove_edge"
        assert DeltaAction.CLEAR.value == "clear"


# ── Node ──────────────────────────────────────────────────────────────


class TestNode:
    def test_creation_minimal(self):
        node = Node(id="n1", type="math/add", x=10.0, y=20.0)
        assert node.id == "n1"
        assert node.type == "math/add"
        assert node.x == 10.0
        assert node.y == 20.0

    def test_defaults(self):
        node = Node(id="n1", type="basic", x=0.0, y=0.0)
        assert node.title is None
        assert node.properties == {}
        assert node.inputs == []
        assert node.outputs == []
        assert node.modifiers == {}

    def test_creation_full(self):
        inp = NodeSlot(name="a", type="float")
        out = NodeSlot(name="result", type="float")
        node = Node(
            id="n2",
            type="math/multiply",
            x=100.0,
            y=200.0,
            title="Multiply",
            properties={"precision": 2},
            inputs=[inp],
            outputs=[out],
            modifiers={"collapsed": True},
        )
        assert node.title == "Multiply"
        assert node.properties == {"precision": 2}
        assert len(node.inputs) == 1
        assert len(node.outputs) == 1
        assert node.modifiers == {"collapsed": True}

    def test_to_dict(self):
        node = Node(
            id="n1",
            type="const",
            x=5.0,
            y=10.0,
            title="Constant",
            inputs=[NodeSlot(name="in", type="any")],
        )
        d = node.to_dict()
        assert d["id"] == "n1"
        assert d["type"] == "const"
        assert d["x"] == 5.0
        assert d["y"] == 10.0
        assert d["title"] == "Constant"
        assert d["inputs"] == [{"name": "in", "type": "any"}]

    def test_from_dict(self):
        data = {
            "id": "n3",
            "type": "display",
            "x": 50.0,
            "y": 75.0,
            "title": "Display",
            "properties": {"format": "hex"},
            "inputs": [{"name": "value", "type": "string"}],
            "outputs": [],
            "modifiers": {},
        }
        node = Node.from_dict(data)
        assert node.id == "n3"
        assert node.type == "display"
        assert node.title == "Display"
        assert node.properties == {"format": "hex"}
        assert len(node.inputs) == 1
        assert node.inputs[0].name == "value"

    def test_round_trip(self):
        original = Node(
            id="n4",
            type="filter",
            x=1.5,
            y=2.5,
            title="Filter",
            properties={"mode": "lowpass"},
            inputs=[NodeSlot(name="signal", type="float")],
            outputs=[NodeSlot(name="filtered", type="float")],
            modifiers={"color": "#ff0000"},
        )
        restored = Node.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.x == original.x
        assert restored.y == original.y
        assert restored.title == original.title
        assert restored.properties == original.properties
        assert len(restored.inputs) == len(original.inputs)
        assert restored.inputs[0].name == original.inputs[0].name
        assert len(restored.outputs) == len(original.outputs)
        assert restored.modifiers == original.modifiers

    def test_default_mutable_isolation(self):
        """Default mutable fields should not be shared between instances."""
        a = Node(id="a", type="t", x=0.0, y=0.0)
        b = Node(id="b", type="t", x=0.0, y=0.0)
        a.properties["key"] = "val"
        assert "key" not in b.properties


# ── Edge ──────────────────────────────────────────────────────────────


class TestEdge:
    def test_creation(self):
        edge = Edge(id="e1", from_node="n1", from_slot=0, to_node="n2", to_slot=0)
        assert edge.id == "e1"
        assert edge.from_node == "n1"
        assert edge.from_slot == 0
        assert edge.to_node == "n2"
        assert edge.to_slot == 0

    def test_default_edge_type(self):
        edge = Edge(id="e1", from_node="n1", from_slot=0, to_node="n2", to_slot=0)
        assert edge.edge_type == EdgeType.DATA_FLOW

    def test_dependency_edge_type(self):
        edge = Edge(
            id="e2",
            from_node="n1",
            from_slot=0,
            to_node="n2",
            to_slot=1,
            edge_type=EdgeType.DEPENDENCY,
        )
        assert edge.edge_type == EdgeType.DEPENDENCY

    def test_to_dict(self):
        edge = Edge(id="e1", from_node="n1", from_slot=0, to_node="n2", to_slot=1)
        d = edge.to_dict()
        assert d["id"] == "e1"
        assert d["from_node"] == "n1"
        assert d["from_slot"] == 0
        assert d["to_node"] == "n2"
        assert d["to_slot"] == 1
        assert d["edge_type"] == "data_flow"

    def test_to_dict_dependency(self):
        edge = Edge(
            id="e2",
            from_node="n1",
            from_slot=0,
            to_node="n2",
            to_slot=0,
            edge_type=EdgeType.DEPENDENCY,
        )
        assert edge.to_dict()["edge_type"] == "dependency"

    def test_from_dict(self):
        data = {
            "id": "e3",
            "from_node": "n5",
            "from_slot": 2,
            "to_node": "n6",
            "to_slot": 0,
            "edge_type": "dependency",
        }
        edge = Edge.from_dict(data)
        assert edge.id == "e3"
        assert edge.from_node == "n5"
        assert edge.from_slot == 2
        assert edge.edge_type == EdgeType.DEPENDENCY

    def test_round_trip(self):
        original = Edge(
            id="e4",
            from_node="n10",
            from_slot=1,
            to_node="n11",
            to_slot=3,
            edge_type=EdgeType.DEPENDENCY,
        )
        restored = Edge.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.from_node == original.from_node
        assert restored.from_slot == original.from_slot
        assert restored.to_node == original.to_node
        assert restored.to_slot == original.to_slot
        assert restored.edge_type == original.edge_type


# ── Graph ─────────────────────────────────────────────────────────────


class TestGraph:
    @staticmethod
    def _make_node(nid: str = "n1") -> Node:
        return Node(id=nid, type="basic", x=0.0, y=0.0)

    @staticmethod
    def _make_edge(eid: str = "e1", fn: str = "n1", tn: str = "n2") -> Edge:
        return Edge(id=eid, from_node=fn, from_slot=0, to_node=tn, to_slot=0)

    def test_empty_graph(self):
        g = Graph()
        assert g.nodes == {}
        assert g.edges == {}

    def test_add_node(self):
        g = Graph()
        node = self._make_node("n1")
        g.add_node(node)
        assert "n1" in g.nodes
        assert g.nodes["n1"] is node

    def test_add_node_duplicate_raises(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        with pytest.raises(ValueError):
            g.add_node(self._make_node("n1"))

    def test_remove_node(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        g.remove_node("n1")
        assert "n1" not in g.nodes

    def test_remove_node_not_found_raises(self):
        g = Graph()
        with pytest.raises(KeyError):
            g.remove_node("nope")

    def test_remove_node_cascades_edges(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        g.add_node(self._make_node("n2"))
        g.add_node(self._make_node("n3"))
        g.add_edge(self._make_edge("e1", "n1", "n2"))
        g.add_edge(self._make_edge("e2", "n2", "n3"))
        g.remove_node("n2")
        assert "e1" not in g.edges
        assert "e2" not in g.edges

    def test_add_edge(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        g.add_node(self._make_node("n2"))
        edge = self._make_edge("e1", "n1", "n2")
        g.add_edge(edge)
        assert "e1" in g.edges
        assert g.edges["e1"] is edge

    def test_add_edge_duplicate_raises(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        g.add_node(self._make_node("n2"))
        g.add_edge(self._make_edge("e1", "n1", "n2"))
        with pytest.raises(ValueError):
            g.add_edge(self._make_edge("e1", "n1", "n2"))

    def test_add_edge_missing_from_node_raises(self):
        g = Graph()
        g.add_node(self._make_node("n2"))
        with pytest.raises(KeyError):
            g.add_edge(self._make_edge("e1", "n1", "n2"))

    def test_add_edge_missing_to_node_raises(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        with pytest.raises(KeyError):
            g.add_edge(self._make_edge("e1", "n1", "n2"))

    def test_remove_edge(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        g.add_node(self._make_node("n2"))
        g.add_edge(self._make_edge("e1", "n1", "n2"))
        g.remove_edge("e1")
        assert "e1" not in g.edges

    def test_remove_edge_not_found_raises(self):
        g = Graph()
        with pytest.raises(KeyError):
            g.remove_edge("nope")

    def test_clear(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        g.add_node(self._make_node("n2"))
        g.add_edge(self._make_edge("e1", "n1", "n2"))
        g.clear()
        assert g.nodes == {}
        assert g.edges == {}

    def test_to_dict(self):
        g = Graph()
        g.add_node(self._make_node("n1"))
        g.add_node(self._make_node("n2"))
        g.add_edge(self._make_edge("e1", "n1", "n2"))
        d = g.to_dict()
        assert "nodes" in d
        assert "edges" in d
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)
        assert len(d["nodes"]) == 2
        assert len(d["edges"]) == 1

    def test_from_dict(self):
        data = {
            "nodes": [
                {
                    "id": "n1",
                    "type": "basic",
                    "x": 0.0,
                    "y": 0.0,
                    "title": None,
                    "properties": {},
                    "inputs": [],
                    "outputs": [],
                    "modifiers": {},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "from_node": "n1",
                    "from_slot": 0,
                    "to_node": "n99",
                    "to_slot": 0,
                    "edge_type": "data_flow",
                },
            ],
        }
        g = Graph.from_dict(data)
        assert "n1" in g.nodes
        assert "e1" in g.edges
        # from_dict populates directly, no validation
        assert g.edges["e1"].to_node == "n99"

    def test_round_trip(self):
        g = Graph()
        g.add_node(
            Node(
                id="n1",
                type="math/add",
                x=10.0,
                y=20.0,
                title="Add",
                inputs=[NodeSlot(name="a", type="float")],
                outputs=[NodeSlot(name="sum", type="float")],
            )
        )
        g.add_node(Node(id="n2", type="const", x=0.0, y=0.0))
        g.add_edge(Edge(id="e1", from_node="n2", from_slot=0, to_node="n1", to_slot=0))
        restored = Graph.from_dict(g.to_dict())
        assert set(restored.nodes.keys()) == {"n1", "n2"}
        assert set(restored.edges.keys()) == {"e1"}
        assert restored.nodes["n1"].title == "Add"
        assert restored.edges["e1"].from_node == "n2"

    def test_default_mutable_isolation(self):
        """Default mutable fields should not be shared between Graph instances."""
        a = Graph()
        b = Graph()
        a.add_node(self._make_node("n1"))
        assert "n1" not in b.nodes


# ── Delta ─────────────────────────────────────────────────────────────


class TestDelta:
    def test_creation(self):
        delta = Delta(
            action=DeltaAction.ADD_NODE, target_id="n1", data={"type": "basic"}
        )
        assert delta.action == DeltaAction.ADD_NODE
        assert delta.target_id == "n1"
        assert delta.data == {"type": "basic"}

    def test_defaults(self):
        delta = Delta(action=DeltaAction.CLEAR)
        assert delta.target_id is None
        assert delta.data is None

    def test_to_dict(self):
        delta = Delta(action=DeltaAction.REMOVE_NODE, target_id="n5")
        d = delta.to_dict()
        assert d["action"] == "remove_node"
        assert d["target_id"] == "n5"
        assert d["data"] is None

    def test_from_dict(self):
        data = {"action": "add_edge", "target_id": "e1", "data": {"from_node": "n1"}}
        delta = Delta.from_dict(data)
        assert delta.action == DeltaAction.ADD_EDGE
        assert delta.target_id == "e1"
        assert delta.data == {"from_node": "n1"}

    def test_round_trip(self):
        original = Delta(
            action=DeltaAction.UPDATE_NODE,
            target_id="n3",
            data={"x": 100.0, "y": 200.0},
        )
        restored = Delta.from_dict(original.to_dict())
        assert restored.action == original.action
        assert restored.target_id == original.target_id
        assert restored.data == original.data

    def test_clear_round_trip(self):
        original = Delta(action=DeltaAction.CLEAR)
        restored = Delta.from_dict(original.to_dict())
        assert restored.action == DeltaAction.CLEAR
        assert restored.target_id is None
        assert restored.data is None
