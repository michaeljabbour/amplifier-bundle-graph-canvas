"""Graph -> Recipe YAML compiler.

Walks a graph topologically and emits recipe YAML (schema v1.7.0).
"""

from __future__ import annotations

from collections import deque
from io import StringIO
from typing import Any

from ruamel.yaml import YAML

from .schema import CompileError, get_node_type

# Canonical key orderings for deterministic output
_TOP_LEVEL_KEY_ORDER = [
    "name",
    "version",
    "description",
    "context",
    "stages",
    "steps",
]
_STEP_KEY_ORDER = [
    "name",
    "type",
    "agent",
    "command",
    "recipe_path",
    "instructions",
    "context",
    "output_var",
    "condition",
    "foreach",
    "while_condition",
    "retry",
    "timeout",
    "depends_on",
    "working_dir",
    "model",
]
_MODIFIER_KEYS = {"condition", "foreach", "while_condition", "retry", "timeout"}


def compile_graph(graph: dict[str, Any], name: str = "untitled") -> str:
    """Compile a graph dict (Graph.to_dict() format) into recipe YAML.

    Args:
        graph: Plain dict with 'nodes' and 'edges' lists.
        name: Recipe name (default: 'untitled').

    Returns:
        Block-style YAML string (schema v1.7.0).

    Raises:
        CompileError: On cycles or unknown node types.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Index nodes by id, preserving original list position
    node_by_id: dict[str, dict] = {}
    node_position: dict[str, int] = {}
    for i, node in enumerate(nodes):
        node_by_id[node["id"]] = node
        node_position[node["id"]] = i

    # Classify nodes
    workflow_nodes: list[dict] = []
    context_nodes: list[dict] = []
    stage_nodes: list[dict] = []
    step_nodes: list[dict] = []  # workflow nodes that produce recipe steps

    for node in nodes:
        node_type = node["type"]
        spec = get_node_type(node_type)
        if spec.category.value != "workflow":
            # Computation node — silently skip
            continue
        workflow_nodes.append(node)
        if node_type == "workflow/context":
            context_nodes.append(node)
        elif node_type == "workflow/stage":
            stage_nodes.append(node)
        else:
            # Has recipe_step_type != None
            step_nodes.append(node)

    # Build step names for workflow nodes that produce steps or stages
    node_step_names: dict[str, str] = {}
    for node in workflow_nodes:
        node_step_names[node["id"]] = _make_step_name(node)

    # Build set of workflow node ids for filtering edges
    workflow_ids = {n["id"] for n in workflow_nodes}

    # Topological sort of workflow nodes
    sorted_workflow = _topological_sort(workflow_nodes, edges, node_position)

    # Build dependency map (dependency-type edges -> depends_on)
    dep_map = _build_dependency_map(edges, workflow_ids, node_step_names)

    # Determine which step nodes belong to which stage
    stage_children: dict[str, list[str]] = {}  # stage_id -> [child_node_ids]
    nodes_in_stages: set[str] = set()
    for stage in stage_nodes:
        stage_id = stage["id"]
        children = _get_stage_children(stage_id, edges, step_nodes)
        stage_children[stage_id] = children
        nodes_in_stages.update(children)

    # Build recipe dict
    recipe: dict[str, Any] = {
        "name": name,
        "version": "1.7.0",
    }

    # Context nodes -> top-level context
    if context_nodes:
        merged_context: dict[str, Any] = {}
        for ctx in context_nodes:
            variables = ctx.get("properties", {}).get("variables", {})
            if variables:
                merged_context.update(variables)
        if merged_context:
            recipe["context"] = merged_context

    # Stage nodes -> stages block
    if stage_nodes:
        stages_list: list[dict[str, Any]] = []
        for node in sorted_workflow:
            if node["type"] != "workflow/stage":
                continue
            stage_id = node["id"]
            props = node.get("properties", {})
            stage_dict: dict[str, Any] = {}

            stage_name = props.get("stage_name", "")
            if stage_name:
                stage_dict["name"] = stage_name
            else:
                stage_dict["name"] = _make_step_name(node)

            # Approval config
            if props.get("approval_required"):
                stage_dict["approval_required"] = True
            if props.get("approval_prompt"):
                stage_dict["approval_prompt"] = props["approval_prompt"]
            if props.get("approval_timeout") is not None:
                stage_dict["approval_timeout"] = props["approval_timeout"]

            # Nested steps
            child_ids = stage_children.get(stage_id, [])
            nested_steps: list[dict[str, Any]] = []
            for wn in sorted_workflow:
                if wn["id"] in child_ids:
                    step_name = node_step_names[wn["id"]]
                    depends = dep_map.get(wn["id"], [])
                    step = _node_to_step(wn, step_name, depends)
                    if step:
                        nested_steps.append(step)
            if nested_steps:
                stage_dict["steps"] = nested_steps

            stages_list.append(stage_dict)

        if stages_list:
            recipe["stages"] = stages_list

    # Top-level steps (not in any stage)
    top_steps: list[dict[str, Any]] = []
    for node in sorted_workflow:
        nid = node["id"]
        if node["type"] in ("workflow/context", "workflow/stage"):
            continue
        if nid in nodes_in_stages:
            continue
        step_name = node_step_names[nid]
        depends = dep_map.get(nid, [])
        step = _node_to_step(node, step_name, depends)
        if step:
            top_steps.append(step)

    if top_steps:
        recipe["steps"] = top_steps

    # Order keys canonically
    recipe = _order_dict(recipe, _TOP_LEVEL_KEY_ORDER)

    return _dump_yaml(recipe)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_step_name(node: dict) -> str:
    """Generate a step name from node title (lowered, spaces->underscores) or id."""
    title = node.get("title")
    if title:
        return title.lower().replace(" ", "_")
    return node["id"]


def _topological_sort(
    workflow_nodes: list[dict],
    edges: list[dict],
    node_position: dict[str, int],
) -> list[dict]:
    """Kahn's algorithm with stable ordering by original list position.

    Raises CompileError on cycles.
    """
    if not workflow_nodes:
        return []

    wf_ids = {n["id"] for n in workflow_nodes}
    node_map = {n["id"]: n for n in workflow_nodes}

    # Build adjacency and in-degree for workflow nodes only
    in_degree: dict[str, int] = {nid: 0 for nid in wf_ids}
    adjacency: dict[str, list[str]] = {nid: [] for nid in wf_ids}

    for edge in edges:
        src = edge["from_node"]
        dst = edge["to_node"]
        if src in wf_ids and dst in wf_ids:
            adjacency[src].append(dst)
            in_degree[dst] += 1

    # Seed queue with zero-indegree nodes, sorted by original position
    queue: deque[str] = deque(
        sorted(
            (nid for nid, deg in in_degree.items() if deg == 0),
            key=lambda nid: node_position.get(nid, 0),
        )
    )

    result: list[dict] = []
    while queue:
        nid = queue.popleft()
        result.append(node_map[nid])
        # Process neighbors sorted by position for stability
        neighbors = sorted(adjacency[nid], key=lambda n: node_position.get(n, 0))
        for neighbor in neighbors:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                # Insert in sorted position
                queue.append(neighbor)
        # Re-sort queue by position for stable ordering
        queue = deque(sorted(queue, key=lambda n: node_position.get(n, 0)))

    if len(result) != len(workflow_nodes):
        raise CompileError("Cycle detected in graph")

    return result


def _build_dependency_map(
    edges: list[dict],
    workflow_ids: set[str],
    node_step_names: dict[str, str],
) -> dict[str, list[str]]:
    """Build mapping from node_id -> list of depends_on step names.

    Only dependency-type edges between workflow nodes are considered.
    """
    dep_map: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("edge_type") != "dependency":
            continue
        src = edge["from_node"]
        dst = edge["to_node"]
        if src in workflow_ids and dst in workflow_ids:
            if dst not in dep_map:
                dep_map[dst] = []
            src_name = node_step_names[src] if src in node_step_names else src
            dep_map[dst].append(src_name)
    return dep_map


def _get_stage_children(
    stage_id: str,
    edges: list[dict],
    step_nodes: list[dict],
) -> list[str]:
    """Find step node ids that are direct children of a stage node via edges."""
    step_ids = {n["id"] for n in step_nodes}
    children: list[str] = []
    for edge in edges:
        if edge["from_node"] == stage_id and edge["to_node"] in step_ids:
            children.append(edge["to_node"])
    return children


def _node_to_step(
    node: dict,
    step_name: str,
    depends_on: list[str],
) -> dict[str, Any] | None:
    """Convert a workflow node dict to a recipe step dict.

    Returns None if the node has no recipe_step_type.
    """
    spec = get_node_type(node["type"])
    if spec.recipe_step_type is None:
        return None

    step: dict[str, Any] = {
        "name": step_name,
        "type": spec.recipe_step_type,
    }

    # Add non-empty properties
    props = node.get("properties", {})
    for key, value in props.items():
        if _is_empty(value):
            continue
        step[key] = value

    # Add modifiers
    modifiers = node.get("modifiers", {})
    for key, value in modifiers.items():
        if key in _MODIFIER_KEYS and not _is_empty(value):
            step[key] = value

    # Add depends_on
    if depends_on:
        step["depends_on"] = depends_on

    return _order_dict(step, _STEP_KEY_ORDER)


def _is_empty(value: Any) -> bool:
    """Check if a value is considered empty/default for omission."""
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, dict) and len(value) == 0:
        return True
    return False


def _order_dict(d: dict[str, Any], key_order: list[str]) -> dict[str, Any]:
    """Reorder dict keys according to canonical order. Unknown keys go last."""
    order_map = {k: i for i, k in enumerate(key_order)}
    max_idx = len(key_order)
    return dict(
        sorted(d.items(), key=lambda item: (order_map.get(item[0], max_idx), item[0]))
    )


def _dump_yaml(data: dict[str, Any]) -> str:
    """Dump dict to block-style YAML string, 2-space indent."""
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    stream = StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()
