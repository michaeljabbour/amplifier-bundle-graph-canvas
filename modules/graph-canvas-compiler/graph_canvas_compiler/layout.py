"""Auto-layout algorithm for graph nodes.

Assigns positions to nodes based on topological order,
arranging them left-to-right by dependency level.
"""

from __future__ import annotations

import copy
from collections import deque
from typing import Any


def auto_layout(
    graph: dict[str, Any],
    margin: int = 80,
    node_width: int = 200,
    node_height: int = 100,
) -> dict[str, Any]:
    """Assign positions to graph nodes based on topological order.

    Nodes are arranged left-to-right by dependency level.
    Nodes in the same topological level are stacked vertically.
    Stage container nodes get 1.5x width for extra spacing.

    Args:
        graph: Dict with 'nodes' and 'edges' lists (Graph.to_dict() format).
        margin: Spacing between nodes and from edges.
        node_width: Default width of a node for horizontal spacing.
        node_height: Default height of a node for vertical spacing.

    Returns:
        A copy of the graph dict with 'x' and 'y' fields set on each node.
    """
    result = copy.deepcopy(graph)
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])

    if not nodes:
        return result

    # Build node index
    node_by_id: dict[str, dict] = {n["id"]: n for n in nodes}
    node_ids = set(node_by_id.keys())

    # Build adjacency and in-degree
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}

    for edge in edges:
        src = edge["from_node"]
        dst = edge["to_node"]
        if src in node_ids and dst in node_ids:
            adjacency[src].append(dst)
            in_degree[dst] += 1

    # Assign topological levels using BFS (Kahn's algorithm)
    level: dict[str, int] = {}
    queue: deque[str] = deque()

    for nid, deg in in_degree.items():
        if deg == 0:
            queue.append(nid)
            level[nid] = 0

    while queue:
        nid = queue.popleft()
        for neighbor in adjacency[nid]:
            in_degree[neighbor] -= 1
            # Each node's level is max(parent levels) + 1
            level[neighbor] = max(level.get(neighbor, 0), level[nid] + 1)
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Nodes not reached (cycles or isolated) get level 0
    for nid in node_ids:
        if nid not in level:
            level[nid] = 0

    # Group nodes by level
    levels: dict[int, list[str]] = {}
    for nid, lvl in level.items():
        levels.setdefault(lvl, []).append(nid)

    # Sort nodes within each level by their original list order for stability
    node_order = {n["id"]: i for i, n in enumerate(nodes)}
    for lvl in levels:
        levels[lvl].sort(key=lambda nid: node_order.get(nid, 0))

    # Compute x offset for each level, accounting for stage node widths
    max_level = max(levels.keys()) if levels else 0
    level_x: dict[int, int] = {}
    current_x = margin

    for lvl in range(max_level + 1):
        level_x[lvl] = current_x
        # Find the max effective width in this level
        level_nodes = levels.get(lvl, [])
        max_width = node_width
        for nid in level_nodes:
            node = node_by_id[nid]
            if node.get("type") == "workflow/stage":
                max_width = max(max_width, int(node_width * 1.5))
        current_x += max_width + margin

    # Assign positions
    for lvl, nids in levels.items():
        x = level_x[lvl]
        for i, nid in enumerate(nids):
            node = node_by_id[nid]
            node["x"] = x
            node["y"] = margin + i * (node_height + margin)

    return result
