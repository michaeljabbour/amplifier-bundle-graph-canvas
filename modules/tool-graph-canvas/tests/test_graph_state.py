"""Tests for the GraphState in-process graph state manager."""

import uuid

import pytest

from amplifier_module_tool_graph_canvas.graph_state import GraphState


class TestAddNode:
    def test_add_node_returns_valid_uuid(self):
        gs = GraphState()
        node_id = gs.add_node(type="workflow/agent", x=10.0, y=20.0)
        # Should be a valid hex UUID (32 hex chars)
        uuid.UUID(node_id)

    def test_add_node_appears_in_state(self):
        gs = GraphState()
        node_id = gs.add_node(type="workflow/agent", x=10.0, y=20.0)
        state = gs.get_state()
        node_ids = [n["id"] for n in state["nodes"]]
        assert node_id in node_ids

    def test_add_node_with_title_and_properties(self):
        gs = GraphState()
        node_id = gs.add_node(
            type="workflow/bash",
            x=0.0,
            y=0.0,
            title="Run Tests",
            properties={"command": "pytest"},
        )
        state = gs.get_state()
        node = next(n for n in state["nodes"] if n["id"] == node_id)
        assert node["title"] == "Run Tests"
        assert node["properties"]["command"] == "pytest"

    def test_add_node_populates_slots_from_schema(self):
        gs = GraphState()
        node_id = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        state = gs.get_state()
        node = next(n for n in state["nodes"] if n["id"] == node_id)
        # workflow/agent has inputs=[context_in] and outputs=[result]
        assert len(node["inputs"]) == 1
        assert node["inputs"][0]["name"] == "context_in"
        assert len(node["outputs"]) == 1
        assert node["outputs"][0]["name"] == "result"

    def test_add_node_invalid_type_raises_value_error(self):
        gs = GraphState()
        with pytest.raises(ValueError, match="Unknown node type"):
            gs.add_node(type="nonexistent/fake", x=0.0, y=0.0)

    def test_add_node_returns_delta(self):
        gs = GraphState()
        node_id, delta = gs.add_node(
            type="workflow/agent", x=10.0, y=20.0, _with_delta=True
        )
        assert delta["action"] == "add_node"
        assert delta["target_id"] == node_id


class TestRemoveNode:
    def test_remove_node_removes_from_state(self):
        gs = GraphState()
        node_id = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        gs.remove_node(node_id)
        state = gs.get_state()
        node_ids = [n["id"] for n in state["nodes"]]
        assert node_id not in node_ids

    def test_remove_node_removes_connected_edges(self):
        gs = GraphState()
        n1 = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        n2 = gs.add_node(type="workflow/bash", x=100.0, y=0.0)
        edge_id = gs.connect_nodes(n1, 0, n2, 0)
        gs.remove_node(n1)
        state = gs.get_state()
        edge_ids = [e["id"] for e in state["edges"]]
        assert edge_id not in edge_ids

    def test_remove_node_bad_id_raises_key_error(self):
        gs = GraphState()
        with pytest.raises(KeyError):
            gs.remove_node("nonexistent-id")

    def test_remove_node_returns_delta(self):
        gs = GraphState()
        node_id = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        delta = gs.remove_node(node_id)
        assert delta["action"] == "remove_node"
        assert delta["target_id"] == node_id


class TestConnectNodes:
    def test_connect_nodes_creates_edge(self):
        gs = GraphState()
        n1 = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        n2 = gs.add_node(type="workflow/bash", x=100.0, y=0.0)
        edge_id = gs.connect_nodes(n1, 0, n2, 0)
        state = gs.get_state()
        edge = next(e for e in state["edges"] if e["id"] == edge_id)
        assert edge["from_node"] == n1
        assert edge["to_node"] == n2
        assert edge["edge_type"] == "data_flow"

    def test_connect_nodes_dependency_type(self):
        gs = GraphState()
        n1 = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        n2 = gs.add_node(type="workflow/bash", x=100.0, y=0.0)
        edge_id = gs.connect_nodes(n1, 0, n2, 0, edge_type="dependency")
        state = gs.get_state()
        edge = next(e for e in state["edges"] if e["id"] == edge_id)
        assert edge["edge_type"] == "dependency"

    def test_connect_nodes_bad_from_id_raises_key_error(self):
        gs = GraphState()
        n2 = gs.add_node(type="workflow/bash", x=0.0, y=0.0)
        with pytest.raises(KeyError):
            gs.connect_nodes("bad-id", 0, n2, 0)

    def test_connect_nodes_bad_to_id_raises_key_error(self):
        gs = GraphState()
        n1 = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        with pytest.raises(KeyError):
            gs.connect_nodes(n1, 0, "bad-id", 0)

    def test_connect_nodes_returns_delta(self):
        gs = GraphState()
        n1 = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        n2 = gs.add_node(type="workflow/bash", x=100.0, y=0.0)
        edge_id, delta = gs.connect_nodes(n1, 0, n2, 0, _with_delta=True)
        assert delta["action"] == "add_edge"
        assert delta["target_id"] == edge_id


class TestDisconnect:
    def test_disconnect_removes_edge(self):
        gs = GraphState()
        n1 = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        n2 = gs.add_node(type="workflow/bash", x=100.0, y=0.0)
        edge_id = gs.connect_nodes(n1, 0, n2, 0)
        gs.disconnect(edge_id)
        state = gs.get_state()
        edge_ids = [e["id"] for e in state["edges"]]
        assert edge_id not in edge_ids

    def test_disconnect_bad_id_raises_key_error(self):
        gs = GraphState()
        with pytest.raises(KeyError):
            gs.disconnect("nonexistent-edge")

    def test_disconnect_returns_delta(self):
        gs = GraphState()
        n1 = gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        n2 = gs.add_node(type="workflow/bash", x=100.0, y=0.0)
        edge_id = gs.connect_nodes(n1, 0, n2, 0)
        delta = gs.disconnect(edge_id)
        assert delta["action"] == "remove_edge"
        assert delta["target_id"] == edge_id


class TestSetNodeProperty:
    def test_set_node_property_updates(self):
        gs = GraphState()
        node_id = gs.add_node(type="workflow/bash", x=0.0, y=0.0)
        gs.set_node_property(node_id, "command", "echo hello")
        state = gs.get_state()
        node = next(n for n in state["nodes"] if n["id"] == node_id)
        assert node["properties"]["command"] == "echo hello"

    def test_set_node_property_bad_id_raises_key_error(self):
        gs = GraphState()
        with pytest.raises(KeyError):
            gs.set_node_property("bad-id", "command", "echo hello")

    def test_set_node_property_returns_delta(self):
        gs = GraphState()
        node_id = gs.add_node(type="workflow/bash", x=0.0, y=0.0)
        delta = gs.set_node_property(node_id, "command", "echo hi")
        assert delta["action"] == "update_node"
        assert delta["target_id"] == node_id


class TestClear:
    def test_clear_resets_to_empty(self):
        gs = GraphState()
        gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        gs.add_node(type="workflow/bash", x=100.0, y=0.0)
        gs.clear()
        state = gs.get_state()
        assert state["nodes"] == []
        assert state["edges"] == []

    def test_clear_returns_delta(self):
        gs = GraphState()
        gs.add_node(type="workflow/agent", x=0.0, y=0.0)
        delta = gs.clear()
        assert delta["action"] == "clear"


class TestGetNodeTypes:
    def test_get_node_types_returns_list(self):
        gs = GraphState()
        types = gs.get_node_types()
        assert isinstance(types, list)
        assert len(types) > 0

    def test_get_node_types_entries_have_type_name(self):
        gs = GraphState()
        types = gs.get_node_types()
        for entry in types:
            assert "type_name" in entry

    def test_get_node_types_with_category_filter(self):
        gs = GraphState()
        types = gs.get_node_types(category="workflow")
        assert len(types) > 0
        for entry in types:
            assert entry["category"] == "workflow"

    def test_get_node_types_with_unknown_category(self):
        gs = GraphState()
        types = gs.get_node_types(category="nonexistent")
        assert types == []


class TestGetState:
    def test_get_state_empty(self):
        gs = GraphState()
        state = gs.get_state()
        assert "nodes" in state
        assert "edges" in state
        assert state["nodes"] == []
        assert state["edges"] == []

    def test_get_state_has_metadata(self):
        gs = GraphState()
        state = gs.get_state()
        assert "metadata" in state
