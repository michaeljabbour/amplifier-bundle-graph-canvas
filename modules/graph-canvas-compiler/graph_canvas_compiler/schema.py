"""Node type schema registry for graph canvas compiler.

Defines all known node types for Phase 1 workflow nodes and Phase 2 computation nodes.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CompileError(Exception):
    """Raised for compilation/schema validation errors."""


class NodeCategory(Enum):
    """Categories of node types."""

    WORKFLOW = "workflow"
    MATH = "math"
    LOGIC = "logic"
    STRING = "string"
    EVENTS = "events"
    BASIC = "basic"


@dataclass
class SlotSpec:
    """Specification for a node input or output slot."""

    name: str
    type: str


@dataclass
class NodeTypeSpec:
    """Specification for a node type."""

    type_name: str
    category: NodeCategory
    title: str
    description: str
    inputs: list[SlotSpec] = field(default_factory=list)
    outputs: list[SlotSpec] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    supported_modifiers: list[str] = field(default_factory=list)
    recipe_step_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary."""
        return {
            "type_name": self.type_name,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "inputs": [{"name": s.name, "type": s.type} for s in self.inputs],
            "outputs": [{"name": s.name, "type": s.type} for s in self.outputs],
            "properties": copy.deepcopy(self.properties),
            "supported_modifiers": self.supported_modifiers,
            "recipe_step_type": self.recipe_step_type,
        }


# --- Registry ---

_REGISTRY: dict[str, NodeTypeSpec] = {}

_WORKFLOW_STEP_MODIFIERS = [
    "condition",
    "foreach",
    "while_condition",
    "retry",
    "timeout",
]


def _register(spec: NodeTypeSpec) -> None:
    """Register a node type spec in the registry."""
    _REGISTRY[spec.type_name] = spec


def get_node_type(type_name: str) -> NodeTypeSpec:
    """Look up a node type by name. Raises CompileError if unknown."""
    try:
        return _REGISTRY[type_name]
    except KeyError:
        raise CompileError(f"Unknown node type: {type_name}") from None


def list_node_types(category: str | NodeCategory | None = None) -> list[NodeTypeSpec]:
    """List registered node types, optionally filtered by category."""
    if category is None:
        return list(_REGISTRY.values())
    value = category.value if isinstance(category, NodeCategory) else category
    return [s for s in _REGISTRY.values() if s.category.value == value]


# =============================================================================
# Phase 1: Workflow nodes
# =============================================================================

_register(
    NodeTypeSpec(
        type_name="workflow/agent",
        category=NodeCategory.WORKFLOW,
        title="Agent Step",
        description="Delegates work to an AI agent",
        inputs=[SlotSpec(name="context_in", type="string")],
        outputs=[SlotSpec(name="result", type="string")],
        properties={
            "agent": "",
            "instructions": "",
            "model": "",
            "output_var": "",
        },
        supported_modifiers=_WORKFLOW_STEP_MODIFIERS,
        recipe_step_type="agent",
    )
)

_register(
    NodeTypeSpec(
        type_name="workflow/bash",
        category=NodeCategory.WORKFLOW,
        title="Bash Step",
        description="Executes a shell command",
        properties={
            "command": "",
            "output_var": "",
            "working_dir": "",
        },
        supported_modifiers=_WORKFLOW_STEP_MODIFIERS,
        recipe_step_type="bash",
    )
)

_register(
    NodeTypeSpec(
        type_name="workflow/subrecipe",
        category=NodeCategory.WORKFLOW,
        title="Sub-Recipe Step",
        description="Executes another recipe",
        properties={
            "recipe_path": "",
            "context": "",
            "output_var": "",
        },
        supported_modifiers=_WORKFLOW_STEP_MODIFIERS,
        recipe_step_type="recipe",
    )
)

_register(
    NodeTypeSpec(
        type_name="workflow/stage",
        category=NodeCategory.WORKFLOW,
        title="Stage",
        description="Groups steps into an approval stage",
        properties={
            "stage_name": "",
            "approval_required": False,
            "approval_prompt": "",
            "approval_timeout": None,
        },
    )
)

_register(
    NodeTypeSpec(
        type_name="workflow/context",
        category=NodeCategory.WORKFLOW,
        title="Context",
        description="Defines context variables for the recipe",
        properties={
            "variables": {},
        },
    )
)

# =============================================================================
# Phase 2: Computation nodes — Math
# =============================================================================

_register(
    NodeTypeSpec(
        type_name="math/operation",
        category=NodeCategory.MATH,
        title="Math Operation",
        description="Performs arithmetic on two numbers",
        inputs=[
            SlotSpec(name="A", type="number"),
            SlotSpec(name="B", type="number"),
        ],
        outputs=[SlotSpec(name="result", type="number")],
        properties={"op": "+"},
    )
)

_register(
    NodeTypeSpec(
        type_name="math/compare",
        category=NodeCategory.MATH,
        title="Math Compare",
        description="Compares two numbers",
        inputs=[
            SlotSpec(name="A", type="number"),
            SlotSpec(name="B", type="number"),
        ],
        outputs=[SlotSpec(name="result", type="boolean")],
        properties={"op": "=="},
    )
)

_register(
    NodeTypeSpec(
        type_name="math/condition",
        category=NodeCategory.MATH,
        title="Math Condition",
        description="Selects A or B based on a boolean condition",
        inputs=[
            SlotSpec(name="condition", type="boolean"),
            SlotSpec(name="A", type="number"),
            SlotSpec(name="B", type="number"),
        ],
        outputs=[SlotSpec(name="result", type="number")],
    )
)

# =============================================================================
# Phase 2: Computation nodes — Logic
# =============================================================================

_register(
    NodeTypeSpec(
        type_name="logic/AND",
        category=NodeCategory.LOGIC,
        title="Logic AND",
        description="Boolean AND of two inputs",
        inputs=[
            SlotSpec(name="A", type="boolean"),
            SlotSpec(name="B", type="boolean"),
        ],
        outputs=[SlotSpec(name="result", type="boolean")],
    )
)

_register(
    NodeTypeSpec(
        type_name="logic/OR",
        category=NodeCategory.LOGIC,
        title="Logic OR",
        description="Boolean OR of two inputs",
        inputs=[
            SlotSpec(name="A", type="boolean"),
            SlotSpec(name="B", type="boolean"),
        ],
        outputs=[SlotSpec(name="result", type="boolean")],
    )
)

_register(
    NodeTypeSpec(
        type_name="logic/NOT",
        category=NodeCategory.LOGIC,
        title="Logic NOT",
        description="Boolean NOT of input",
        inputs=[SlotSpec(name="in", type="boolean")],
        outputs=[SlotSpec(name="result", type="boolean")],
    )
)

_register(
    NodeTypeSpec(
        type_name="logic/IF",
        category=NodeCategory.LOGIC,
        title="Logic IF",
        description="Routes event based on boolean condition",
        inputs=[SlotSpec(name="condition", type="boolean")],
        outputs=[
            SlotSpec(name="true", type="event"),
            SlotSpec(name="false", type="event"),
        ],
    )
)

# =============================================================================
# Phase 2: Computation nodes — String
# =============================================================================

_register(
    NodeTypeSpec(
        type_name="string/toString",
        category=NodeCategory.STRING,
        title="To String",
        description="Converts any value to a string",
        inputs=[SlotSpec(name="value", type="any")],
        outputs=[SlotSpec(name="string", type="string")],
    )
)

_register(
    NodeTypeSpec(
        type_name="string/compare",
        category=NodeCategory.STRING,
        title="String Compare",
        description="Compares two strings for equality",
        inputs=[
            SlotSpec(name="A", type="string"),
            SlotSpec(name="B", type="string"),
        ],
        outputs=[SlotSpec(name="result", type="boolean")],
    )
)

# =============================================================================
# Phase 2: Computation nodes — Events
# =============================================================================

_register(
    NodeTypeSpec(
        type_name="events/log",
        category=NodeCategory.EVENTS,
        title="Event Log",
        description="Logs an event",
        inputs=[SlotSpec(name="event", type="event")],
    )
)

_register(
    NodeTypeSpec(
        type_name="events/delay",
        category=NodeCategory.EVENTS,
        title="Event Delay",
        description="Delays an event by a specified time",
        inputs=[SlotSpec(name="event", type="event")],
        outputs=[SlotSpec(name="event", type="event")],
        properties={"time_ms": 1000},
    )
)

# =============================================================================
# Phase 2: Computation nodes — Basic
# =============================================================================

_register(
    NodeTypeSpec(
        type_name="basic/const",
        category=NodeCategory.BASIC,
        title="Constant",
        description="Outputs a constant number",
        outputs=[SlotSpec(name="value", type="number")],
        properties={"value": 0},
    )
)

_register(
    NodeTypeSpec(
        type_name="basic/boolean",
        category=NodeCategory.BASIC,
        title="Boolean",
        description="Outputs a constant boolean",
        outputs=[SlotSpec(name="value", type="boolean")],
        properties={"value": True},
    )
)

_register(
    NodeTypeSpec(
        type_name="basic/string",
        category=NodeCategory.BASIC,
        title="String",
        description="Outputs a constant string",
        outputs=[SlotSpec(name="value", type="string")],
        properties={"value": ""},
    )
)

_register(
    NodeTypeSpec(
        type_name="basic/watch",
        category=NodeCategory.BASIC,
        title="Watch",
        description="Displays a value for debugging",
        inputs=[SlotSpec(name="value", type="any")],
    )
)
