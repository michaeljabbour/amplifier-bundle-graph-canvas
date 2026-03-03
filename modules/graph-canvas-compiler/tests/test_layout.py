"""Tests for auto-layout algorithm."""

from __future__ import annotations

from amplifier_module_graph_canvas_compiler.layout import auto_layout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    node_id: str,
    node_type: str = "workflow/agent",
    title: str | None = None,
) -> dict:
    """Build a minimal node dict (no position set)."""
    return {
        "id": node_id,
        "type": node_type,
        "x": 0.0,
        "y": 0.0,
        "title": title,
        "properties": {},
        "inputs": [],
        "outputs": [],
        "modifiers": {},
    }


def _edge(
    edge_id: str,
    from_node: str,
    to_node: str,
    edge_type: str = "data_flow",
) -> dict:
    return {
        "id": edge_id,
        "from_node": from_node,
        "from_slot": 0,
        "to_node": to_node,
        "to_slot": 0,
        "edge_type": edge_type,
    }


# ===========================================================================
# Tests
# ===========================================================================


class TestSingleNode:
    def test_single_node_at_origin(self):
        """A single node should be positioned at (margin, margin)."""
        graph = {"nodes": [_node("n1")], "edges": []}
        result = auto_layout(graph)
        node = result["nodes"][0]
        # Default margin is 80
        assert node["x"] == 80
        assert node["y"] == 80


class TestLinearChain:
    def test_abc_left_to_right(self):
        """A->B->C should be arranged left to right with increasing x."""
        graph = {
            "nodes": [_node("a"), _node("b"), _node("c")],
            "edges": [
                _edge("e1", "a", "b"),
                _edge("e2", "b", "c"),
            ],
        }
        result = auto_layout(graph)
        nodes_by_id = {n["id"]: n for n in result["nodes"]}
        assert nodes_by_id["a"]["x"] < nodes_by_id["b"]["x"]
        assert nodes_by_id["b"]["x"] < nodes_by_id["c"]["x"]
        # All on the same y since they are each the sole node in their level
        assert nodes_by_id["a"]["y"] == nodes_by_id["b"]["y"]
        assert nodes_by_id["b"]["y"] == nodes_by_id["c"]["y"]


class TestParallelNodes:
    def test_parallel_nodes_same_x_different_y(self):
        """Nodes at the same topo level share x, differ in y."""
        graph = {
            "nodes": [_node("a"), _node("b"), _node("c")],
            "edges": [
                _edge("e1", "a", "b"),
                _edge("e2", "a", "c"),
            ],
        }
        result = auto_layout(graph)
        nodes_by_id = {n["id"]: n for n in result["nodes"]}
        # B and C are in the same topo level (both depend only on A)
        assert nodes_by_id["b"]["x"] == nodes_by_id["c"]["x"]
        assert nodes_by_id["b"]["y"] != nodes_by_id["c"]["y"]
        # A is earlier
        assert nodes_by_id["a"]["x"] < nodes_by_id["b"]["x"]


class TestCustomSpacing:
    def test_custom_margin_and_dimensions(self):
        """Custom margin, node_width, node_height should be respected."""
        graph = {
            "nodes": [_node("a"), _node("b")],
            "edges": [_edge("e1", "a", "b")],
        }
        result = auto_layout(graph, margin=50, node_width=300, node_height=150)
        nodes_by_id = {n["id"]: n for n in result["nodes"]}
        # First node at (margin, margin)
        assert nodes_by_id["a"]["x"] == 50
        assert nodes_by_id["a"]["y"] == 50
        # Second node offset by node_width + margin
        assert nodes_by_id["b"]["x"] == 50 + 300 + 50
        assert nodes_by_id["b"]["y"] == 50


class TestStageNodesExtraSpacing:
    def test_stage_nodes_get_extra_width(self):
        """Stage container nodes should get extra spacing."""
        graph = {
            "nodes": [
                _node("s1", node_type="workflow/stage"),
                _node("n1", node_type="workflow/agent"),
            ],
            "edges": [_edge("e1", "s1", "n1")],
        }
        result = auto_layout(graph)
        nodes_by_id = {n["id"]: n for n in result["nodes"]}
        stage_x = nodes_by_id["s1"]["x"]
        agent_x = nodes_by_id["n1"]["x"]
        # Stage nodes get 1.5x width, so gap should be bigger than default
        assert agent_x - stage_x > 200 + 80  # default node_width + margin


class TestEmptyGraph:
    def test_empty_graph_returns_empty(self):
        graph = {"nodes": [], "edges": []}
        result = auto_layout(graph)
        assert result["nodes"] == []
        assert result["edges"] == []


class TestEdgesPreserved:
    def test_edges_unchanged(self):
        """auto_layout should not modify edges."""
        edge = _edge("e1", "a", "b")
        graph = {"nodes": [_node("a"), _node("b")], "edges": [edge]}
        result = auto_layout(graph)
        assert len(result["edges"]) == 1
        assert result["edges"][0]["id"] == "e1"
