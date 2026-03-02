"""Tests for graph -> recipe YAML compiler."""

from __future__ import annotations

import pytest
from ruamel.yaml import YAML

from graph_canvas_compiler.compile import compile_graph
from graph_canvas_compiler.schema import CompileError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    id: str,
    type: str,
    title: str | None = None,
    properties: dict | None = None,
    modifiers: dict | None = None,
) -> dict:
    """Build a minimal node dict matching Graph.to_dict() format."""
    return {
        "id": id,
        "type": type,
        "x": 0.0,
        "y": 0.0,
        "title": title,
        "properties": properties or {},
        "inputs": [],
        "outputs": [],
        "modifiers": modifiers or {},
    }


def _edge(
    id: str,
    from_node: str,
    to_node: str,
    edge_type: str = "data_flow",
) -> dict:
    """Build a minimal edge dict."""
    return {
        "id": id,
        "from_node": from_node,
        "from_slot": 0,
        "to_node": to_node,
        "to_slot": 0,
        "edge_type": edge_type,
    }


def _parse(yaml_str: str) -> dict:
    """Parse YAML string to dict for assertions."""
    _yaml = YAML()
    return _yaml.load(yaml_str)


# ===========================================================================
# Tests
# ===========================================================================


class TestEmptyGraph:
    def test_empty_graph_minimal_recipe(self):
        result = compile_graph({"nodes": [], "edges": []})
        data = _parse(result)
        assert data["name"] == "untitled"
        assert data["version"] == "1.7.0"
        assert "steps" not in data or data["steps"] is None or data["steps"] == []

    def test_default_name(self):
        result = compile_graph({"nodes": [], "edges": []})
        data = _parse(result)
        assert data["name"] == "untitled"

    def test_custom_name(self):
        result = compile_graph({"nodes": [], "edges": []}, name="my-recipe")
        data = _parse(result)
        assert data["name"] == "my-recipe"


class TestSingleAgentNode:
    def test_agent_node_compiles(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Run Analysis",
                    properties={
                        "agent": "zen-architect",
                        "instructions": "Analyze the code",
                        "model": "claude-sonnet",
                        "output_var": "analysis_result",
                    },
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        steps = data["steps"]
        assert len(steps) == 1
        step = steps[0]
        assert step["name"] == "run_analysis"
        assert step["type"] == "agent"
        assert step["agent"] == "zen-architect"
        assert step["instructions"] == "Analyze the code"
        assert step["model"] == "claude-sonnet"
        assert step["output_var"] == "analysis_result"


class TestSingleBashNode:
    def test_bash_node_compiles(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/bash",
                    title="Run Tests",
                    properties={
                        "command": "pytest -x",
                        "output_var": "test_result",
                        "working_dir": "/app",
                    },
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        step = data["steps"][0]
        assert step["name"] == "run_tests"
        assert step["type"] == "bash"
        assert step["command"] == "pytest -x"
        assert step["working_dir"] == "/app"


class TestSingleSubrecipeNode:
    def test_subrecipe_node_compiles(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/subrecipe",
                    title="Deploy Step",
                    properties={
                        "recipe_path": "@recipes:deploy.yaml",
                        "context": "env=prod",
                        "output_var": "deploy_out",
                    },
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        step = data["steps"][0]
        assert step["name"] == "deploy_step"
        assert step["type"] == "recipe"
        assert step["recipe_path"] == "@recipes:deploy.yaml"


class TestStepNameFromId:
    def test_uses_id_when_no_title(self):
        graph = {
            "nodes": [
                _node(
                    "my_node_1",
                    "workflow/agent",
                    properties={"agent": "x", "instructions": "do stuff"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["steps"][0]["name"] == "my_node_1"


class TestModifiers:
    def test_condition_modifier(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Conditional Step",
                    properties={"agent": "x", "instructions": "do stuff"},
                    modifiers={"condition": "{{env}} == 'prod'"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["steps"][0]["condition"] == "{{env}} == 'prod'"

    def test_foreach_modifier(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/bash",
                    title="Loop Step",
                    properties={"command": "echo {{item}}"},
                    modifiers={"foreach": "{{file_list}}"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["steps"][0]["foreach"] == "{{file_list}}"

    def test_while_condition_modifier(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="While Step",
                    properties={"agent": "x", "instructions": "loop"},
                    modifiers={"while_condition": "{{done}} != true"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["steps"][0]["while_condition"] == "{{done}} != true"

    def test_retry_modifier(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/bash",
                    title="Retry Step",
                    properties={"command": "curl http://example.com"},
                    modifiers={"retry": 3},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["steps"][0]["retry"] == 3

    def test_multiple_modifiers(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Multi Mod",
                    properties={"agent": "x", "instructions": "go"},
                    modifiers={
                        "condition": "{{flag}}",
                        "retry": 2,
                        "timeout": 60,
                    },
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        step = data["steps"][0]
        assert step["condition"] == "{{flag}}"
        assert step["retry"] == 2
        assert step["timeout"] == 60


class TestTopologicalOrder:
    def test_sequential_edges_order(self):
        """Nodes connected by data_flow edges should be topologically ordered."""
        graph = {
            "nodes": [
                _node(
                    "b",
                    "workflow/bash",
                    title="Step B",
                    properties={"command": "echo B"},
                ),
                _node(
                    "a",
                    "workflow/bash",
                    title="Step A",
                    properties={"command": "echo A"},
                ),
                _node(
                    "c",
                    "workflow/bash",
                    title="Step C",
                    properties={"command": "echo C"},
                ),
            ],
            "edges": [
                _edge("e1", "a", "b"),  # A -> B
                _edge("e2", "b", "c"),  # B -> C
            ],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        names = [s["name"] for s in data["steps"]]
        assert names == ["step_a", "step_b", "step_c"]


class TestDependencyEdges:
    def test_dependency_creates_depends_on(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/bash",
                    title="First",
                    properties={"command": "echo 1"},
                ),
                _node(
                    "n2",
                    "workflow/bash",
                    title="Second",
                    properties={"command": "echo 2"},
                ),
            ],
            "edges": [
                _edge("e1", "n1", "n2", edge_type="dependency"),
            ],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        second = [s for s in data["steps"] if s["name"] == "second"][0]
        assert second["depends_on"] == ["first"]


class TestContextNode:
    def test_context_becomes_top_level(self):
        graph = {
            "nodes": [
                _node(
                    "ctx1",
                    "workflow/context",
                    properties={"variables": {"env": "production", "debug": False}},
                ),
                _node(
                    "n1",
                    "workflow/bash",
                    title="Build",
                    properties={"command": "make build"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["context"] == {"env": "production", "debug": False}
        # Context node should NOT appear as a step
        step_names = [s["name"] for s in data.get("steps", [])]
        assert all("ctx" not in n for n in step_names)


class TestStageNode:
    def test_stage_creates_stages_block(self):
        graph = {
            "nodes": [
                _node(
                    "s1",
                    "workflow/stage",
                    properties={
                        "stage_name": "review",
                        "approval_required": True,
                        "approval_prompt": "Approve?",
                        "approval_timeout": 300,
                    },
                ),
                _node(
                    "n1",
                    "workflow/agent",
                    title="Review Code",
                    properties={"agent": "reviewer", "instructions": "Review"},
                ),
            ],
            "edges": [
                _edge("e1", "s1", "n1"),
            ],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert "stages" in data
        stages = data["stages"]
        assert len(stages) == 1
        stage = stages[0]
        assert stage["name"] == "review"
        assert stage["approval_required"] is True
        assert stage["approval_prompt"] == "Approve?"
        assert stage["approval_timeout"] == 300
        # The agent step should be nested inside the stage
        assert len(stage["steps"]) == 1
        assert stage["steps"][0]["name"] == "review_code"


class TestComputationNodesSkipped:
    def test_math_node_skipped(self):
        graph = {
            "nodes": [
                _node("m1", "math/operation", properties={"op": "+"}),
                _node(
                    "n1",
                    "workflow/bash",
                    title="Real Step",
                    properties={"command": "echo hi"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        step_names = [s["name"] for s in data.get("steps", [])]
        assert len(step_names) == 1
        assert step_names[0] == "real_step"

    def test_logic_node_skipped(self):
        graph = {
            "nodes": [
                _node("l1", "logic/AND"),
                _node(
                    "n1",
                    "workflow/agent",
                    title="Work",
                    properties={"agent": "x", "instructions": "y"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert len(data.get("steps", [])) == 1

    def test_mixed_computation_nodes_all_skipped(self):
        graph = {
            "nodes": [
                _node("m1", "math/compare"),
                _node("l1", "logic/IF"),
                _node("s1", "string/toString"),
                _node("e1", "events/log"),
                _node("b1", "basic/const"),
                _node(
                    "n1",
                    "workflow/bash",
                    title="Only Step",
                    properties={"command": "ls"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert len(data.get("steps", [])) == 1


class TestEmptyPropertiesOmitted:
    def test_empty_strings_omitted(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Minimal",
                    properties={
                        "agent": "zen",
                        "instructions": "do work",
                        "model": "",
                        "output_var": "",
                    },
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        step = data["steps"][0]
        assert "model" not in step
        assert "output_var" not in step
        assert step["agent"] == "zen"

    def test_none_values_omitted(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Test",
                    properties={
                        "agent": "a",
                        "instructions": "b",
                        "model": None,
                        "output_var": None,
                    },
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        step = data["steps"][0]
        assert "model" not in step
        assert "output_var" not in step


class TestYamlFormatValidity:
    def test_output_is_valid_yaml(self):
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Step One",
                    properties={"agent": "x", "instructions": "y"},
                ),
                _node(
                    "n2",
                    "workflow/bash",
                    title="Step Two",
                    properties={"command": "echo done"},
                ),
            ],
            "edges": [_edge("e1", "n1", "n2")],
        }
        result = compile_graph(graph, name="valid-yaml")
        data = _parse(result)
        assert isinstance(data, dict)
        assert data["name"] == "valid-yaml"


class TestCycleDetection:
    def test_cycle_raises_compile_error(self):
        graph = {
            "nodes": [
                _node(
                    "a", "workflow/bash", title="A", properties={"command": "echo A"}
                ),
                _node(
                    "b", "workflow/bash", title="B", properties={"command": "echo B"}
                ),
            ],
            "edges": [
                _edge("e1", "a", "b"),
                _edge("e2", "b", "a"),
            ],
        }
        with pytest.raises(CompileError, match="[Cc]ycle"):
            compile_graph(graph, name="cyclic")


class TestMultipleContextNodesMerge:
    def test_two_context_nodes_merge_variables(self):
        """Multiple context nodes should merge their variables into one top-level context."""
        graph = {
            "nodes": [
                _node(
                    "ctx1",
                    "workflow/context",
                    properties={
                        "variables": {"env": "production", "region": "us-east"}
                    },
                ),
                _node(
                    "ctx2",
                    "workflow/context",
                    properties={"variables": {"debug": True, "timeout": 30}},
                ),
                _node(
                    "n1",
                    "workflow/bash",
                    title="Build",
                    properties={"command": "make build"},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["context"] == {
            "env": "production",
            "region": "us-east",
            "debug": True,
            "timeout": 30,
        }

    def test_overlapping_context_nodes_last_wins(self):
        """When context nodes have overlapping keys, later node overwrites."""
        graph = {
            "nodes": [
                _node(
                    "ctx1",
                    "workflow/context",
                    properties={"variables": {"env": "staging"}},
                ),
                _node(
                    "ctx2",
                    "workflow/context",
                    properties={"variables": {"env": "production"}},
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        assert data["context"]["env"] == "production"


class TestEmptyDictPropertiesOmitted:
    def test_empty_dict_properties_omitted(self):
        """Empty dict values in properties should be omitted from output."""
        graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Minimal",
                    properties={
                        "agent": "zen",
                        "instructions": "do work",
                        "context": {},
                    },
                ),
            ],
            "edges": [],
        }
        result = compile_graph(graph, name="test")
        data = _parse(result)
        step = data["steps"][0]
        assert "context" not in step
        assert step["agent"] == "zen"
        assert step["instructions"] == "do work"
