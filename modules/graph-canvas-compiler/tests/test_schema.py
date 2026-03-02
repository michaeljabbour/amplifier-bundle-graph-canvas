"""Tests for the node type schema registry."""

import pytest

from graph_canvas_compiler.schema import (
    CompileError,
    NodeCategory,
    NodeTypeSpec,
    SlotSpec,
    get_node_type,
    list_node_types,
)


# --- SlotSpec tests ---


class TestSlotSpec:
    def test_slot_spec_has_name_and_type(self):
        slot = SlotSpec(name="value", type="number")
        assert slot.name == "value"
        assert slot.type == "number"


# --- NodeCategory tests ---


class TestNodeCategory:
    def test_workflow_category(self):
        assert NodeCategory.WORKFLOW.value == "workflow"

    def test_math_category(self):
        assert NodeCategory.MATH.value == "math"

    def test_logic_category(self):
        assert NodeCategory.LOGIC.value == "logic"

    def test_string_category(self):
        assert NodeCategory.STRING.value == "string"

    def test_events_category(self):
        assert NodeCategory.EVENTS.value == "events"

    def test_basic_category(self):
        assert NodeCategory.BASIC.value == "basic"


# --- NodeTypeSpec tests ---


class TestNodeTypeSpec:
    def test_spec_field_access(self):
        spec = NodeTypeSpec(
            type_name="test/node",
            category=NodeCategory.BASIC,
            title="Test Node",
            description="A test node",
            inputs=[SlotSpec(name="in", type="number")],
            outputs=[SlotSpec(name="out", type="string")],
            properties={"key": "val"},
            supported_modifiers=["condition"],
            recipe_step_type="agent",
        )
        assert spec.type_name == "test/node"
        assert spec.category == NodeCategory.BASIC
        assert spec.title == "Test Node"
        assert spec.description == "A test node"
        assert len(spec.inputs) == 1
        assert spec.inputs[0].name == "in"
        assert len(spec.outputs) == 1
        assert spec.outputs[0].name == "out"
        assert spec.properties == {"key": "val"}
        assert spec.supported_modifiers == ["condition"]
        assert spec.recipe_step_type == "agent"

    def test_spec_defaults(self):
        spec = NodeTypeSpec(
            type_name="test/defaults",
            category=NodeCategory.BASIC,
            title="Defaults",
            description="Test defaults",
        )
        assert spec.inputs == []
        assert spec.outputs == []
        assert spec.properties == {}
        assert spec.supported_modifiers == []
        assert spec.recipe_step_type is None

    def test_to_dict(self):
        spec = NodeTypeSpec(
            type_name="test/dict",
            category=NodeCategory.MATH,
            title="Dict Test",
            description="Testing to_dict",
            inputs=[SlotSpec(name="A", type="number")],
            outputs=[SlotSpec(name="result", type="number")],
            properties={"op": "+"},
            supported_modifiers=["condition"],
            recipe_step_type="agent",
        )
        d = spec.to_dict()
        assert d["type_name"] == "test/dict"
        assert d["category"] == "math"
        assert d["title"] == "Dict Test"
        assert d["description"] == "Testing to_dict"
        assert d["inputs"] == [{"name": "A", "type": "number"}]
        assert d["outputs"] == [{"name": "result", "type": "number"}]
        assert d["properties"] == {"op": "+"}
        assert d["supported_modifiers"] == ["condition"]
        assert d["recipe_step_type"] == "agent"

    def test_to_dict_properties_are_deepcopied(self):
        """Mutating to_dict() output must not corrupt the original spec."""
        spec = get_node_type("workflow/context")
        d = spec.to_dict()
        # Mutate the nested dict in the serialized output
        d["properties"]["variables"]["injected"] = "bad"
        # Original spec must be unaffected
        assert spec.properties["variables"] == {}

    def test_to_dict_supported_modifiers_are_copied(self):
        """Mutating to_dict() output must not corrupt the shared modifiers list."""
        spec = get_node_type("workflow/agent")
        d = spec.to_dict()
        original_modifiers = list(spec.supported_modifiers)
        # Mutate the serialized output
        d["supported_modifiers"].append("injected_modifier")
        # Original spec must be unaffected
        assert spec.supported_modifiers == original_modifiers


# --- CompileError tests ---


class TestCompileError:
    def test_compile_error_is_exception(self):
        err = CompileError("something went wrong")
        assert isinstance(err, Exception)
        assert str(err) == "something went wrong"


# --- Workflow node existence and properties ---

# Intentionally duplicated from implementation to test the contract independently
WORKFLOW_STEP_MODIFIERS = [
    "condition",
    "foreach",
    "while_condition",
    "retry",
    "timeout",
]


class TestWorkflowNodes:
    def test_agent_node_exists(self):
        spec = get_node_type("workflow/agent")
        assert spec.type_name == "workflow/agent"
        assert spec.category == NodeCategory.WORKFLOW
        assert spec.recipe_step_type == "agent"
        assert spec.supported_modifiers == WORKFLOW_STEP_MODIFIERS
        assert "agent" in spec.properties
        assert "instructions" in spec.properties
        assert "model" in spec.properties
        assert "output_var" in spec.properties
        assert any(i.name == "context_in" and i.type == "string" for i in spec.inputs)
        assert any(o.name == "result" and o.type == "string" for o in spec.outputs)

    def test_bash_node_exists(self):
        spec = get_node_type("workflow/bash")
        assert spec.type_name == "workflow/bash"
        assert spec.category == NodeCategory.WORKFLOW
        assert spec.recipe_step_type == "bash"
        assert spec.supported_modifiers == WORKFLOW_STEP_MODIFIERS
        assert "command" in spec.properties
        assert "output_var" in spec.properties
        assert "working_dir" in spec.properties

    def test_subrecipe_node_exists(self):
        spec = get_node_type("workflow/subrecipe")
        assert spec.type_name == "workflow/subrecipe"
        assert spec.category == NodeCategory.WORKFLOW
        assert spec.recipe_step_type == "recipe"
        assert spec.supported_modifiers == WORKFLOW_STEP_MODIFIERS
        assert "recipe_path" in spec.properties
        assert "context" in spec.properties
        assert "output_var" in spec.properties

    def test_stage_node_exists(self):
        spec = get_node_type("workflow/stage")
        assert spec.type_name == "workflow/stage"
        assert spec.category == NodeCategory.WORKFLOW
        assert spec.recipe_step_type is None
        assert spec.supported_modifiers == []
        assert "stage_name" in spec.properties
        assert "approval_required" in spec.properties
        assert "approval_prompt" in spec.properties
        assert "approval_timeout" in spec.properties

    def test_context_node_exists(self):
        spec = get_node_type("workflow/context")
        assert spec.type_name == "workflow/context"
        assert spec.category == NodeCategory.WORKFLOW
        assert spec.recipe_step_type is None
        assert spec.supported_modifiers == []
        assert "variables" in spec.properties


# --- Computation node existence ---


class TestComputationNodes:
    def test_math_operation_exists(self):
        spec = get_node_type("math/operation")
        assert spec.category == NodeCategory.MATH
        assert any(i.name == "A" and i.type == "number" for i in spec.inputs)
        assert any(i.name == "B" and i.type == "number" for i in spec.inputs)
        assert any(o.name == "result" and o.type == "number" for o in spec.outputs)
        assert spec.properties.get("op") == "+"
        assert spec.supported_modifiers == []
        assert spec.recipe_step_type is None

    def test_math_compare_exists(self):
        spec = get_node_type("math/compare")
        assert spec.category == NodeCategory.MATH
        assert any(o.name == "result" and o.type == "boolean" for o in spec.outputs)
        assert spec.properties.get("op") == "=="

    def test_math_condition_exists(self):
        spec = get_node_type("math/condition")
        assert spec.category == NodeCategory.MATH
        assert any(i.name == "condition" and i.type == "boolean" for i in spec.inputs)
        assert any(o.name == "result" and o.type == "number" for o in spec.outputs)

    def test_logic_and_exists(self):
        spec = get_node_type("logic/AND")
        assert spec.category == NodeCategory.LOGIC
        assert any(i.name == "A" and i.type == "boolean" for i in spec.inputs)
        assert any(o.name == "result" and o.type == "boolean" for o in spec.outputs)

    def test_logic_or_exists(self):
        spec = get_node_type("logic/OR")
        assert spec.category == NodeCategory.LOGIC
        assert any(o.name == "result" and o.type == "boolean" for o in spec.outputs)

    def test_logic_not_exists(self):
        spec = get_node_type("logic/NOT")
        assert spec.category == NodeCategory.LOGIC
        assert any(i.name == "in" and i.type == "boolean" for i in spec.inputs)
        assert any(o.name == "result" and o.type == "boolean" for o in spec.outputs)

    def test_logic_if_exists(self):
        spec = get_node_type("logic/IF")
        assert spec.category == NodeCategory.LOGIC
        assert any(i.name == "condition" and i.type == "boolean" for i in spec.inputs)
        assert any(o.name == "true" and o.type == "event" for o in spec.outputs)
        assert any(o.name == "false" and o.type == "event" for o in spec.outputs)

    def test_string_tostring_exists(self):
        spec = get_node_type("string/toString")
        assert spec.category == NodeCategory.STRING
        assert any(i.name == "value" and i.type == "any" for i in spec.inputs)
        assert any(o.name == "string" and o.type == "string" for o in spec.outputs)

    def test_string_compare_exists(self):
        spec = get_node_type("string/compare")
        assert spec.category == NodeCategory.STRING
        assert any(o.name == "result" and o.type == "boolean" for o in spec.outputs)

    def test_events_log_exists(self):
        spec = get_node_type("events/log")
        assert spec.category == NodeCategory.EVENTS
        assert any(i.name == "event" and i.type == "event" for i in spec.inputs)
        assert spec.outputs == []

    def test_events_delay_exists(self):
        spec = get_node_type("events/delay")
        assert spec.category == NodeCategory.EVENTS
        assert spec.properties.get("time_ms") == 1000

    def test_basic_const_exists(self):
        spec = get_node_type("basic/const")
        assert spec.category == NodeCategory.BASIC
        assert any(o.name == "value" and o.type == "number" for o in spec.outputs)
        assert spec.properties.get("value") == 0

    def test_basic_boolean_exists(self):
        spec = get_node_type("basic/boolean")
        assert spec.category == NodeCategory.BASIC
        assert any(o.name == "value" and o.type == "boolean" for o in spec.outputs)
        assert spec.properties.get("value") is True

    def test_basic_string_exists(self):
        spec = get_node_type("basic/string")
        assert spec.category == NodeCategory.BASIC
        assert any(o.name == "value" and o.type == "string" for o in spec.outputs)
        assert spec.properties.get("value") == ""

    def test_basic_watch_exists(self):
        spec = get_node_type("basic/watch")
        assert spec.category == NodeCategory.BASIC
        assert any(i.name == "value" and i.type == "any" for i in spec.inputs)
        assert spec.outputs == []


# --- list_node_types filtering ---


class TestListNodeTypes:
    def test_list_all_node_types(self):
        all_types = list_node_types()
        # 5 workflow + 14 computation = 19 total
        assert len(all_types) >= 19

    def test_list_workflow_nodes(self):
        workflow = list_node_types(category="workflow")
        assert len(workflow) == 5
        type_names = {s.type_name for s in workflow}
        assert "workflow/agent" in type_names
        assert "workflow/bash" in type_names
        assert "workflow/subrecipe" in type_names
        assert "workflow/stage" in type_names
        assert "workflow/context" in type_names

    def test_list_math_nodes(self):
        math_nodes = list_node_types(category="math")
        assert len(math_nodes) == 3

    def test_list_logic_nodes(self):
        logic_nodes = list_node_types(category="logic")
        assert len(logic_nodes) == 4

    def test_list_string_nodes(self):
        string_nodes = list_node_types(category="string")
        assert len(string_nodes) == 2

    def test_list_events_nodes(self):
        events_nodes = list_node_types(category="events")
        assert len(events_nodes) == 2

    def test_list_basic_nodes(self):
        basic_nodes = list_node_types(category="basic")
        assert len(basic_nodes) == 4

    def test_list_by_node_category_enum(self):
        """list_node_types should accept NodeCategory directly, not just strings."""
        workflow_nodes = list_node_types(category=NodeCategory.WORKFLOW)
        assert len(workflow_nodes) == 5
        assert all(n.category == NodeCategory.WORKFLOW for n in workflow_nodes)


# --- Unknown type error ---


class TestUnknownType:
    def test_unknown_type_raises_compile_error(self):
        with pytest.raises(CompileError):
            get_node_type("nonexistent/type")
