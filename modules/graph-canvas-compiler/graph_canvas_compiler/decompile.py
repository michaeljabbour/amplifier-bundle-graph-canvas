"""Recipe YAML -> Graph decompiler.

Parses recipe YAML and generates a graph dict (same format as protocol.py's
Graph.to_dict()).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from ruamel.yaml import YAML

from .layout import auto_layout

# Module-level YAML instance
_YAML = YAML()

# Step type -> node type mapping
_STEP_TYPE_TO_NODE_TYPE: dict[str, str] = {
    "agent": "workflow/agent",
    "bash": "workflow/bash",
    "recipe": "workflow/subrecipe",
}

# Agent step property keys (stored in node properties)
_AGENT_PROP_KEYS = {"agent", "instructions", "model", "output_var"}
# Bash step property keys
_BASH_PROP_KEYS = {"command", "output_var", "working_dir"}
# Subrecipe step property keys
_SUBRECIPE_PROP_KEYS = {"recipe_path", "context", "output_var"}

# All known property keys per step type
_PROP_KEYS_BY_TYPE: dict[str, set[str]] = {
    "agent": _AGENT_PROP_KEYS,
    "bash": _BASH_PROP_KEYS,
    "recipe": _SUBRECIPE_PROP_KEYS,
}

# Modifier field groups
_CONDITION_KEY = "condition"
_FOREACH_KEYS = {"foreach", "as", "collect", "parallel", "max_iterations"}
_WHILE_KEYS = {
    "while_condition",
    "max_while_iterations",
    "break_when",
    "update_context",
}
_ERROR_HANDLING_KEYS = {"retry", "on_error", "timeout"}

# Regex to find {{variable}} references
_VAR_REF_PATTERN = re.compile(r"\{\{(\w+)\}\}")

# Keys that are not properties or modifiers (structural keys)
_STRUCTURAL_KEYS = {"name", "type", "depends_on"}


def decompile_recipe(
    yaml_string: str,
    layout_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse recipe YAML and generate a graph dict.

    Args:
        yaml_string: Recipe YAML string.
        layout_data: Optional dict mapping step names to {x, y} positions
            (from .litegraph.json sidecar). If None, auto_layout() is used.

    Returns:
        Graph dict with 'nodes' and 'edges' lists (Graph.to_dict() format).
    """
    recipe = _YAML.load(yaml_string)
    if not isinstance(recipe, dict):
        return {"nodes": [], "edges": []}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Track step name -> node id for edge resolution
    step_name_to_node_id: dict[str, str] = {}
    # Track output_var -> node id for data-flow edge resolution
    output_var_to_node_id: dict[str, str] = {}

    # --- Context node ---
    context = recipe.get("context")
    if isinstance(context, dict) and context:
        ctx_node = _make_node(
            node_type="workflow/context",
            title="context",
            properties={"variables": dict(context)},
        )
        nodes.append(ctx_node)

    # --- Stages mode ---
    stages = recipe.get("stages")
    if stages:
        for stage_def in stages:
            stage_name = stage_def.get("name", "stage")
            stage_props: dict[str, Any] = {"stage_name": stage_name}
            if stage_def.get("approval_required"):
                stage_props["approval_required"] = True
            if stage_def.get("approval_prompt"):
                stage_props["approval_prompt"] = stage_def["approval_prompt"]
            if stage_def.get("approval_timeout") is not None:
                stage_props["approval_timeout"] = stage_def["approval_timeout"]

            stage_node = _make_node(
                node_type="workflow/stage",
                title=stage_name,
                properties=stage_props,
            )
            nodes.append(stage_node)

            # Process steps within the stage
            for step in stage_def.get("steps", []):
                step_node = _step_to_node(step)
                nodes.append(step_node)

                sname = step.get("name", step_node["id"])
                step_name_to_node_id[sname] = step_node["id"]
                ovar = step.get("output_var")
                if ovar:
                    output_var_to_node_id[ovar] = step_node["id"]

                # Edge from stage to step (containment)
                edges.append(
                    _make_edge(
                        from_node=stage_node["id"],
                        to_node=step_node["id"],
                        edge_type="data_flow",
                    )
                )

    # --- Flat steps ---
    flat_steps = recipe.get("steps")
    if flat_steps:
        for step in flat_steps:
            step_node = _step_to_node(step)
            nodes.append(step_node)

            sname = step.get("name", step_node["id"])
            step_name_to_node_id[sname] = step_node["id"]
            ovar = step.get("output_var")
            if ovar:
                output_var_to_node_id[ovar] = step_node["id"]

    # --- Resolve edges ---
    # 1. depends_on -> dependency edges
    all_steps = list(flat_steps or [])
    if stages:
        for stage_def in stages:
            all_steps.extend(stage_def.get("steps", []))

    for step in all_steps:
        sname = step.get("name")
        if not sname:
            continue
        target_id = step_name_to_node_id.get(sname)
        if not target_id:
            continue

        depends_on = step.get("depends_on", [])
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        for dep_name in depends_on:
            dep_id = step_name_to_node_id.get(dep_name)
            if dep_id:
                edges.append(
                    _make_edge(
                        from_node=dep_id,
                        to_node=target_id,
                        edge_type="dependency",
                    )
                )

    # 2. {{variable}} references -> data-flow edges
    _resolve_variable_edges(
        all_steps, step_name_to_node_id, output_var_to_node_id, edges
    )

    graph: dict[str, Any] = {"nodes": nodes, "edges": edges}

    # --- Layout ---
    if layout_data:
        for node in nodes:
            title = node.get("title", "")
            if title in layout_data:
                pos = layout_data[title]
                node["x"] = pos["x"]
                node["y"] = pos["y"]
    else:
        graph = auto_layout(graph)

    return graph


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_node(
    node_type: str,
    title: str,
    properties: dict[str, Any] | None = None,
    modifiers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a node dict."""
    return {
        "id": _gen_id(),
        "type": node_type,
        "x": 0.0,
        "y": 0.0,
        "title": title,
        "properties": properties or {},
        "inputs": [],
        "outputs": [],
        "modifiers": modifiers or {},
    }


def _make_edge(
    from_node: str,
    to_node: str,
    edge_type: str = "data_flow",
) -> dict[str, Any]:
    """Create an edge dict."""
    return {
        "id": _gen_id(),
        "from_node": from_node,
        "from_slot": 0,
        "to_node": to_node,
        "to_slot": 0,
        "edge_type": edge_type,
    }


def _gen_id() -> str:
    """Generate a unique node/edge id."""
    return uuid.uuid4().hex[:12]


def _step_to_node(step: dict[str, Any]) -> dict[str, Any]:
    """Convert a recipe step dict to a graph node dict."""
    step_type = step.get("type", "agent")
    node_type = _STEP_TYPE_TO_NODE_TYPE.get(step_type, "workflow/agent")
    step_name = step.get("name", "step")

    # Extract properties
    prop_keys = _PROP_KEYS_BY_TYPE.get(step_type, set())
    properties: dict[str, Any] = {}
    for key in prop_keys:
        if key in step:
            properties[key] = step[key]

    # Extract modifiers
    modifiers: dict[str, Any] = {}

    # Condition
    if _CONDITION_KEY in step:
        modifiers["condition"] = step[_CONDITION_KEY]

    # Foreach group
    foreach_vals: dict[str, Any] = {}
    for key in _FOREACH_KEYS:
        if key in step:
            foreach_vals[key] = step[key]
    if foreach_vals:
        modifiers["foreach"] = foreach_vals

    # While group
    while_vals: dict[str, Any] = {}
    for key in _WHILE_KEYS:
        if key in step:
            while_vals[key] = step[key]
    if while_vals:
        modifiers["while"] = while_vals

    # Error handling group
    error_vals: dict[str, Any] = {}
    for key in _ERROR_HANDLING_KEYS:
        if key in step:
            error_vals[key] = step[key]
    if error_vals:
        modifiers["error_handling"] = error_vals

    return _make_node(
        node_type=node_type,
        title=step_name,
        properties=properties,
        modifiers=modifiers,
    )


def _resolve_variable_edges(
    steps: list[dict[str, Any]],
    step_name_to_node_id: dict[str, str],
    output_var_to_node_id: dict[str, str],
    edges: list[dict[str, Any]],
) -> None:
    """Find {{variable}} references in step fields and create data-flow edges."""
    # Fields to scan for variable references
    scan_fields = (
        "instructions",
        "command",
        "condition",
        "prompt",
        "context",
        "foreach",
        "while_condition",
        "break_when",
    )

    # Track edges already created to avoid duplicates
    seen_edges: set[tuple[str, str]] = set()
    # Also track existing edges
    for e in edges:
        seen_edges.add((e["from_node"], e["to_node"]))

    for step in steps:
        sname = step.get("name")
        if not sname:
            continue
        target_id = step_name_to_node_id.get(sname)
        if not target_id:
            continue

        # Collect all string values from scannable fields
        for field_name in scan_fields:
            value = step.get(field_name)
            if not isinstance(value, str):
                continue
            for match in _VAR_REF_PATTERN.finditer(value):
                var_name = match.group(1)
                source_id = output_var_to_node_id.get(var_name)
                if source_id and source_id != target_id:
                    edge_key = (source_id, target_id)
                    if edge_key not in seen_edges:
                        edges.append(
                            _make_edge(
                                from_node=source_id,
                                to_node=target_id,
                                edge_type="data_flow",
                            )
                        )
                        seen_edges.add(edge_key)
