"""Tests for recipe YAML -> graph decompiler."""

from __future__ import annotations

from ruamel.yaml import YAML

from amplifier_module_graph_canvas_compiler.compile import compile_graph
from amplifier_module_graph_canvas_compiler.decompile import decompile_recipe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_yaml = YAML()


def _dump(data: dict) -> str:
    """Dump dict to YAML string."""
    from io import StringIO

    stream = StringIO()
    _yaml.dump(data, stream)
    return stream.getvalue()


def _node(
    node_id: str,
    node_type: str,
    title: str | None = None,
    properties: dict | None = None,
    modifiers: dict | None = None,
) -> dict:
    """Build a minimal node dict matching Graph.to_dict() format."""
    return {
        "id": node_id,
        "type": node_type,
        "x": 0.0,
        "y": 0.0,
        "title": title,
        "properties": properties or {},
        "inputs": [],
        "outputs": [],
        "modifiers": modifiers or {},
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
# Test 1: Simple flat recipe (2 agent steps) -> 2 nodes + 1 data-flow edge
# ===========================================================================


class TestSimpleFlatRecipe:
    def test_two_agent_steps_produce_two_nodes(self):
        yaml_str = _dump(
            {
                "name": "test",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "analyze",
                        "type": "agent",
                        "agent": "reviewer",
                        "instructions": "Review the code",
                        "output_var": "analysis",
                    },
                    {
                        "name": "summarize",
                        "type": "agent",
                        "agent": "writer",
                        "instructions": "Summarize {{analysis}}",
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        nodes = result["nodes"]

        assert len(nodes) == 2
        # Both should be workflow/agent type
        assert all(n["type"] == "workflow/agent" for n in nodes)
        # Node titles should match step names
        titles = {n["title"] for n in nodes}
        assert "analyze" in titles
        assert "summarize" in titles

    def test_variable_reference_creates_data_flow_edge(self):
        """{{analysis}} in step 2 references output_var of step 1 -> edge."""
        yaml_str = _dump(
            {
                "name": "test",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "analyze",
                        "type": "agent",
                        "agent": "reviewer",
                        "instructions": "Review",
                        "output_var": "analysis",
                    },
                    {
                        "name": "summarize",
                        "type": "agent",
                        "agent": "writer",
                        "instructions": "Summarize {{analysis}}",
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        edges = result["edges"]

        # Should have at least one data_flow edge from analyze -> summarize
        data_flow_edges = [e for e in edges if e["edge_type"] == "data_flow"]
        assert len(data_flow_edges) >= 1

        # Find node ids by title
        node_by_title = {n["title"]: n["id"] for n in result["nodes"]}
        edge = data_flow_edges[0]
        assert edge["from_node"] == node_by_title["analyze"]
        assert edge["to_node"] == node_by_title["summarize"]


# ===========================================================================
# Test 2: Mixed step types (agent + bash) -> correct node types
# ===========================================================================


class TestMixedStepTypes:
    def test_agent_and_bash_types(self):
        yaml_str = _dump(
            {
                "name": "mixed",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "build",
                        "type": "bash",
                        "command": "make build",
                        "output_var": "build_result",
                    },
                    {
                        "name": "review",
                        "type": "agent",
                        "agent": "reviewer",
                        "instructions": "Review {{build_result}}",
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        node_by_title = {n["title"]: n for n in result["nodes"]}

        assert node_by_title["build"]["type"] == "workflow/bash"
        assert node_by_title["review"]["type"] == "workflow/agent"

    def test_subrecipe_type(self):
        yaml_str = _dump(
            {
                "name": "sub",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "deploy",
                        "type": "recipe",
                        "recipe_path": "@recipes:deploy.yaml",
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        assert result["nodes"][0]["type"] == "workflow/subrecipe"

    def test_default_type_is_agent(self):
        """Steps without explicit type default to agent."""
        yaml_str = _dump(
            {
                "name": "default",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "do_work",
                        "agent": "helper",
                        "instructions": "Do something",
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        assert result["nodes"][0]["type"] == "workflow/agent"


# ===========================================================================
# Test 3: Recipe with condition modifier
# ===========================================================================


class TestConditionModifier:
    def test_condition_stored_in_modifiers(self):
        yaml_str = _dump(
            {
                "name": "conditional",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "deploy",
                        "type": "bash",
                        "command": "deploy.sh",
                        "condition": "{{env}} == 'prod'",
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        node = result["nodes"][0]
        assert "condition" in node["modifiers"]
        assert node["modifiers"]["condition"] == "{{env}} == 'prod'"


# ===========================================================================
# Test 4: Recipe with foreach modifier
# ===========================================================================


class TestForeachModifier:
    def test_foreach_stored_in_modifiers(self):
        yaml_str = _dump(
            {
                "name": "loop",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "process",
                        "type": "agent",
                        "agent": "processor",
                        "instructions": "Process {{item}}",
                        "foreach": "{{file_list}}",
                        "as": "item",
                        "collect": "results",
                        "parallel": True,
                        "max_iterations": 10,
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        node = result["nodes"][0]
        mods = node["modifiers"]
        assert "foreach" in mods
        foreach = mods["foreach"]
        assert foreach["foreach"] == "{{file_list}}"
        assert foreach["as"] == "item"
        assert foreach["collect"] == "results"
        assert foreach["parallel"] is True
        assert foreach["max_iterations"] == 10


# ===========================================================================
# Test 5: Recipe with stages + approval
# ===========================================================================


class TestStagesWithApproval:
    def test_stages_create_stage_container_nodes(self):
        yaml_str = _dump(
            {
                "name": "staged",
                "version": "1.7.0",
                "stages": [
                    {
                        "name": "review",
                        "approval_required": True,
                        "approval_prompt": "Approve deployment?",
                        "steps": [
                            {
                                "name": "check",
                                "type": "agent",
                                "agent": "reviewer",
                                "instructions": "Review code",
                            },
                        ],
                    },
                    {
                        "name": "deploy",
                        "steps": [
                            {
                                "name": "run_deploy",
                                "type": "bash",
                                "command": "deploy.sh",
                            },
                        ],
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        nodes = result["nodes"]

        # Should have stage nodes
        stage_nodes = [n for n in nodes if n["type"] == "workflow/stage"]
        assert len(stage_nodes) == 2

        # First stage should have approval properties
        review_stage = next(
            n for n in stage_nodes if n["properties"]["stage_name"] == "review"
        )
        assert review_stage["properties"]["approval_required"] is True
        assert review_stage["properties"]["approval_prompt"] == "Approve deployment?"

        # Should also have the step nodes
        step_nodes = [n for n in nodes if n["type"] != "workflow/stage"]
        assert len(step_nodes) == 2

    def test_stage_to_step_edges_exist(self):
        yaml_str = _dump(
            {
                "name": "staged",
                "version": "1.7.0",
                "stages": [
                    {
                        "name": "build_stage",
                        "steps": [
                            {
                                "name": "build",
                                "type": "bash",
                                "command": "make",
                            },
                        ],
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        nodes = result["nodes"]
        edges = result["edges"]

        stage_node = next(n for n in nodes if n["type"] == "workflow/stage")
        step_node = next(n for n in nodes if n["type"] == "workflow/bash")

        # There should be an edge from the stage to its child step
        containment_edges = [
            e
            for e in edges
            if e["from_node"] == stage_node["id"] and e["to_node"] == step_node["id"]
        ]
        assert len(containment_edges) == 1


# ===========================================================================
# Test 6: Recipe with top-level context
# ===========================================================================


class TestTopLevelContext:
    def test_context_creates_context_node(self):
        yaml_str = _dump(
            {
                "name": "ctx_recipe",
                "version": "1.7.0",
                "context": {
                    "env": "production",
                    "debug": False,
                },
                "steps": [
                    {
                        "name": "build",
                        "type": "bash",
                        "command": "make",
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        nodes = result["nodes"]

        context_nodes = [n for n in nodes if n["type"] == "workflow/context"]
        assert len(context_nodes) == 1
        ctx = context_nodes[0]
        assert ctx["properties"]["variables"] == {"env": "production", "debug": False}


# ===========================================================================
# Test 7: Round-trip structural equivalence
# ===========================================================================


class TestRoundTrip:
    def test_compile_then_decompile_structural_equivalence(self):
        """decompile(compile(graph)) should produce structurally equivalent graph."""
        original_graph = {
            "nodes": [
                _node(
                    "n1",
                    "workflow/agent",
                    title="Analyze",
                    properties={
                        "agent": "reviewer",
                        "instructions": "Analyze code",
                        "output_var": "analysis",
                    },
                ),
                _node(
                    "n2",
                    "workflow/bash",
                    title="Build",
                    properties={
                        "command": "make build",
                    },
                ),
            ],
            "edges": [
                _edge("e1", "n1", "n2"),
            ],
        }

        # Compile graph to YAML
        yaml_str = compile_graph(original_graph, name="round-trip")

        # Decompile back to graph
        result = decompile_recipe(yaml_str)

        # Structural checks (not byte-identical)
        assert len(result["nodes"]) == len(original_graph["nodes"])

        result_types = sorted(n["type"] for n in result["nodes"])
        original_types = sorted(n["type"] for n in original_graph["nodes"])
        assert result_types == original_types

        # Check that properties survived the round-trip
        result_by_title = {n["title"]: n for n in result["nodes"]}
        assert "analyze" in result_by_title
        assert result_by_title["analyze"]["properties"]["agent"] == "reviewer"
        assert (
            result_by_title["analyze"]["properties"]["instructions"] == "Analyze code"
        )


# ===========================================================================
# Test: depends_on creates dependency edges
# ===========================================================================


class TestDependsOn:
    def test_depends_on_creates_dependency_edge(self):
        yaml_str = _dump(
            {
                "name": "deps",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "first",
                        "type": "bash",
                        "command": "echo 1",
                    },
                    {
                        "name": "second",
                        "type": "bash",
                        "command": "echo 2",
                        "depends_on": ["first"],
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        edges = result["edges"]

        dep_edges = [e for e in edges if e["edge_type"] == "dependency"]
        assert len(dep_edges) == 1

        node_by_title = {n["title"]: n["id"] for n in result["nodes"]}
        assert dep_edges[0]["from_node"] == node_by_title["first"]
        assert dep_edges[0]["to_node"] == node_by_title["second"]


# ===========================================================================
# Test: While modifier
# ===========================================================================


class TestWhileModifier:
    def test_while_fields_stored_in_modifiers(self):
        yaml_str = _dump(
            {
                "name": "while_test",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "loop",
                        "type": "agent",
                        "agent": "looper",
                        "instructions": "iterate",
                        "while_condition": "{{done}} != true",
                        "max_while_iterations": 5,
                        "break_when": "{{success}}",
                        "update_context": {"counter": "{{counter + 1}}"},
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        node = result["nodes"][0]
        mods = node["modifiers"]
        assert "while" in mods
        w = mods["while"]
        assert w["while_condition"] == "{{done}} != true"
        assert w["max_while_iterations"] == 5
        assert w["break_when"] == "{{success}}"
        assert w["update_context"] == {"counter": "{{counter + 1}}"}


# ===========================================================================
# Test: Error handling modifiers
# ===========================================================================


class TestErrorHandlingModifiers:
    def test_retry_timeout_on_error(self):
        yaml_str = _dump(
            {
                "name": "error_handling",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "flaky",
                        "type": "bash",
                        "command": "curl http://example.com",
                        "retry": 3,
                        "on_error": "continue",
                        "timeout": 60,
                    },
                ],
            }
        )
        result = decompile_recipe(yaml_str)
        node = result["nodes"][0]
        mods = node["modifiers"]
        assert "error_handling" in mods
        eh = mods["error_handling"]
        assert eh["retry"] == 3
        assert eh["on_error"] == "continue"
        assert eh["timeout"] == 60


# ===========================================================================
# Test: Layout data restoration
# ===========================================================================


class TestLayoutDataRestoration:
    def test_layout_data_restores_positions(self):
        yaml_str = _dump(
            {
                "name": "positioned",
                "version": "1.7.0",
                "steps": [
                    {
                        "name": "step_one",
                        "type": "bash",
                        "command": "echo hi",
                    },
                ],
            }
        )
        layout_data = {
            "step_one": {"x": 500, "y": 300},
        }
        result = decompile_recipe(yaml_str, layout_data=layout_data)
        node = result["nodes"][0]
        assert node["x"] == 500
        assert node["y"] == 300
