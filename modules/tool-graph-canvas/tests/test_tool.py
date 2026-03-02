"""Tests for the GraphCanvasTool LLM-callable tool module."""

import pytest

from tool_graph_canvas import mount
from tool_graph_canvas.tool import GraphCanvasTool


# ---------------------------------------------------------------------------
# Helpers for transport tests
# ---------------------------------------------------------------------------
class FakeTransport:
    """Minimal transport stub that does nothing."""

    async def emit(self, delta: dict) -> None:
        pass


class CaptureTransport:
    """Transport stub that records every emitted delta."""

    def __init__(self) -> None:
        self.emitted: list[dict] = []

    async def emit(self, delta: dict) -> None:
        self.emitted.append(delta)


@pytest.fixture
def tool():
    return GraphCanvasTool(config={})


class TestToolProperties:
    def test_name(self, tool):
        assert tool.name == "graph_canvas"

    def test_description_is_nonempty_string(self, tool):
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0

    def test_parameters_is_valid_json_schema(self, tool):
        params = tool.parameters
        assert params["type"] == "object"
        assert "action" in params["properties"]
        action_prop = params["properties"]["action"]
        assert "enum" in action_prop
        # Should include all known actions
        expected = {
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
        }
        assert expected == set(action_prop["enum"])


class TestExecuteAddNode:
    async def test_add_node_returns_node_id(self, tool):
        result = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 10.0,
                "y": 20.0,
            }
        )
        assert "result" in result
        assert "node_id" in result["result"]
        assert "delta" in result

    async def test_add_node_with_title(self, tool):
        result = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/bash",
                "x": 0.0,
                "y": 0.0,
                "title": "Build Step",
            }
        )
        assert "error" not in result
        assert result["result"]["node_id"]


class TestExecuteRemoveNode:
    async def test_remove_node(self, tool):
        add_result = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
            }
        )
        node_id = add_result["result"]["node_id"]
        result = await tool.execute(
            arguments={"action": "remove_node", "node_id": node_id}
        )
        assert "result" in result
        assert "delta" in result


class TestExecuteInvalidNodeId:
    async def test_remove_invalid_node_returns_error_dict(self, tool):
        result = await tool.execute(
            arguments={"action": "remove_node", "node_id": "nonexistent"}
        )
        assert "error" in result
        # Should NOT raise an exception, just return error dict

    async def test_set_property_invalid_node_returns_error_dict(self, tool):
        result = await tool.execute(
            arguments={
                "action": "set_node_property",
                "node_id": "nonexistent",
                "property": "command",
                "value": "echo hi",
            }
        )
        assert "error" in result


class TestExecuteConnectAndDisconnect:
    async def test_connect_nodes(self, tool):
        r1 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
            }
        )
        r2 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/bash",
                "x": 200.0,
                "y": 0.0,
            }
        )
        n1 = r1["result"]["node_id"]
        n2 = r2["result"]["node_id"]
        result = await tool.execute(
            arguments={
                "action": "connect_nodes",
                "from_id": n1,
                "from_slot": 0,
                "to_id": n2,
                "to_slot": 0,
            }
        )
        assert "result" in result
        assert "edge_id" in result["result"]

    async def test_disconnect(self, tool):
        r1 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
            }
        )
        r2 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/bash",
                "x": 200.0,
                "y": 0.0,
            }
        )
        n1 = r1["result"]["node_id"]
        n2 = r2["result"]["node_id"]
        conn = await tool.execute(
            arguments={
                "action": "connect_nodes",
                "from_id": n1,
                "from_slot": 0,
                "to_id": n2,
                "to_slot": 0,
            }
        )
        edge_id = conn["result"]["edge_id"]
        result = await tool.execute(
            arguments={"action": "disconnect", "edge_id": edge_id}
        )
        assert "result" in result
        assert "delta" in result


class TestExecuteGetState:
    async def test_get_graph_state(self, tool):
        result = await tool.execute(arguments={"action": "get_graph_state"})
        assert "result" in result
        assert "nodes" in result["result"]
        assert "edges" in result["result"]


class TestExecuteGetNodeTypes:
    async def test_get_node_types(self, tool):
        result = await tool.execute(arguments={"action": "get_node_types"})
        assert "result" in result
        assert isinstance(result["result"], list)
        assert len(result["result"]) > 0

    async def test_get_node_types_with_category(self, tool):
        result = await tool.execute(
            arguments={"action": "get_node_types", "category": "workflow"}
        )
        assert "result" in result
        for entry in result["result"]:
            assert entry["category"] == "workflow"


class TestExecuteClearGraph:
    async def test_clear_graph(self, tool):
        await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
            }
        )
        result = await tool.execute(arguments={"action": "clear_graph"})
        assert "result" in result
        # Verify actually cleared
        state = await tool.execute(arguments={"action": "get_graph_state"})
        assert state["result"]["nodes"] == []


class TestExecuteCompileRecipe:
    async def test_compile_recipe_returns_yaml(self, tool):
        await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
                "title": "analyze",
                "properties": {"agent": "coder", "instructions": "Do things"},
            }
        )
        result = await tool.execute(arguments={"action": "compile_recipe"})
        assert "result" in result
        yaml_str = result["result"]["yaml"]
        assert isinstance(yaml_str, str)
        assert "steps:" in yaml_str or "name:" in yaml_str


class TestExecuteLoadRecipe:
    async def test_load_recipe_populates_state(self, tool):
        yaml_str = """
name: test_recipe
version: "1.7.0"
steps:
  - name: greet
    type: bash
    command: echo hello
"""
        result = await tool.execute(
            arguments={"action": "load_recipe", "yaml": yaml_str}
        )
        assert "result" in result
        assert "error" not in result
        # Verify state was populated
        state = await tool.execute(arguments={"action": "get_graph_state"})
        assert len(state["result"]["nodes"]) > 0


class TestExecuteUnknownAction:
    async def test_unknown_action_returns_error(self, tool):
        result = await tool.execute(arguments={"action": "fly_to_moon"})
        assert "error" in result
        assert "fly_to_moon" in result["error"]


class TestExecuteGraph:
    async def test_execute_graph_returns_not_implemented(self, tool):
        result = await tool.execute(arguments={"action": "execute_graph"})
        assert result["result"]["status"] == "not_implemented"


class TestFullWorkflow:
    async def test_add_connect_compile(self, tool):
        """Full workflow: add 2 nodes -> connect -> compile -> verify valid YAML."""
        # Add agent node
        r1 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
                "title": "analyze",
                "properties": {
                    "agent": "coder",
                    "instructions": "Analyze the code",
                    "output_var": "analysis",
                },
            }
        )
        n1 = r1["result"]["node_id"]

        # Add bash node
        r2 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/bash",
                "x": 300.0,
                "y": 0.0,
                "title": "run_tests",
                "properties": {"command": "pytest"},
            }
        )
        n2 = r2["result"]["node_id"]

        # Connect them
        conn = await tool.execute(
            arguments={
                "action": "connect_nodes",
                "from_id": n1,
                "from_slot": 0,
                "to_id": n2,
                "to_slot": 0,
                "edge_type": "dependency",
            }
        )
        assert "error" not in conn

        # Compile
        compile_result = await tool.execute(arguments={"action": "compile_recipe"})
        assert "error" not in compile_result
        yaml_str = compile_result["result"]["yaml"]
        assert "steps:" in yaml_str
        assert "analyze" in yaml_str
        assert "run_tests" in yaml_str
        # The bash step should depend on the agent step
        assert "depends_on" in yaml_str


# ---------------------------------------------------------------------------
# mount() function tests
# ---------------------------------------------------------------------------
class TestMountFunction:
    def test_mount_returns_graph_canvas_tool(self):
        tool = mount()
        assert isinstance(tool, GraphCanvasTool)

    def test_mount_with_no_transport_does_not_broadcast(self):
        tool = mount()
        assert tool._transport is None

    def test_mount_passes_transport_to_tool(self):
        fake = FakeTransport()
        tool = mount(config={"transport": fake})
        assert tool._transport is fake


# ---------------------------------------------------------------------------
# Transport broadcast tests
# ---------------------------------------------------------------------------
class TestTransportBroadcast:
    async def test_add_node_broadcasts_delta_via_transport(self):
        capture = CaptureTransport()
        tool = GraphCanvasTool(config={}, transport=capture)
        await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
            }
        )
        assert len(capture.emitted) == 1
        assert capture.emitted[0]["action"] == "add_node"

    async def test_no_broadcast_when_transport_is_none(self):
        tool = GraphCanvasTool(config={}, transport=None)
        result = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "x": 0.0,
                "y": 0.0,
            }
        )
        assert "result" in result

    async def test_get_graph_state_does_not_broadcast(self):
        capture = CaptureTransport()
        tool = GraphCanvasTool(config={}, transport=capture)
        await tool.execute(arguments={"action": "get_graph_state"})
        assert len(capture.emitted) == 0

    @pytest.mark.parametrize(
        "action_name, expected_delta_action",
        [
            ("add_node", "add_node"),
            ("remove_node", "remove_node"),
            ("set_node_property", "update_node"),
            ("connect_nodes", "add_edge"),
            ("disconnect", "remove_edge"),
            ("clear_graph", "clear"),
        ],
        ids=[
            "add_node",
            "remove_node",
            "set_node_property",
            "connect_nodes",
            "disconnect",
            "clear_graph",
        ],
    )
    async def test_mutating_action_broadcasts(self, action_name, expected_delta_action):
        """Every mutating action broadcasts exactly one delta via transport."""
        capture = CaptureTransport()
        tool = GraphCanvasTool(config={}, transport=capture)

        # Some actions require pre-existing nodes/edges — set them up.
        if action_name == "add_node":
            await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/agent",
                    "x": 0.0,
                    "y": 0.0,
                }
            )
        elif action_name == "remove_node":
            r = await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/agent",
                    "x": 0.0,
                    "y": 0.0,
                }
            )
            capture.emitted.clear()
            await tool.execute(
                arguments={
                    "action": "remove_node",
                    "node_id": r["result"]["node_id"],
                }
            )
        elif action_name == "set_node_property":
            r = await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/agent",
                    "x": 0.0,
                    "y": 0.0,
                }
            )
            capture.emitted.clear()
            await tool.execute(
                arguments={
                    "action": "set_node_property",
                    "node_id": r["result"]["node_id"],
                    "property": "title",
                    "value": "updated",
                }
            )
        elif action_name == "connect_nodes":
            r1 = await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/agent",
                    "x": 0.0,
                    "y": 0.0,
                }
            )
            r2 = await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/bash",
                    "x": 200.0,
                    "y": 0.0,
                }
            )
            capture.emitted.clear()
            await tool.execute(
                arguments={
                    "action": "connect_nodes",
                    "from_id": r1["result"]["node_id"],
                    "from_slot": 0,
                    "to_id": r2["result"]["node_id"],
                    "to_slot": 0,
                }
            )
        elif action_name == "disconnect":
            r1 = await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/agent",
                    "x": 0.0,
                    "y": 0.0,
                }
            )
            r2 = await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/bash",
                    "x": 200.0,
                    "y": 0.0,
                }
            )
            conn = await tool.execute(
                arguments={
                    "action": "connect_nodes",
                    "from_id": r1["result"]["node_id"],
                    "from_slot": 0,
                    "to_id": r2["result"]["node_id"],
                    "to_slot": 0,
                }
            )
            capture.emitted.clear()
            await tool.execute(
                arguments={
                    "action": "disconnect",
                    "edge_id": conn["result"]["edge_id"],
                }
            )
        elif action_name == "clear_graph":
            await tool.execute(
                arguments={
                    "action": "add_node",
                    "type": "workflow/agent",
                    "x": 0.0,
                    "y": 0.0,
                }
            )
            capture.emitted.clear()
            await tool.execute(arguments={"action": "clear_graph"})

        assert len(capture.emitted) == 1
        assert capture.emitted[0]["action"] == expected_delta_action
