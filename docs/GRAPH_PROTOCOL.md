# Graph Protocol Specification

Version: 0.1.0

This document defines the canonical data model for the graph-canvas bundle. All Python modules and frontend consumers agree on this protocol.

## Node

A node represents a single operation or data source in the graph.

```json
{
  "id": "uuid-string",
  "type": "workflow/agent",
  "title": "Analyze Code",
  "pos": [200, 100],
  "properties": {
    "agent": "foundation:zen-architect",
    "prompt": "Analyze the codebase for {{topic}}",
    "output": "analysis"
  },
  "inputs": [
    {"name": "topic", "type": "string"}
  ],
  "outputs": [
    {"name": "analysis", "type": "string"}
  ],
  "modifiers": {
    "condition": null,
    "foreach": null,
    "while": null,
    "error_handling": null
  }
}
```

### Required Fields
- `id` -- Unique identifier (UUID string)
- `type` -- Node type from the registry (e.g., `workflow/agent`, `math/add`)

### Optional Fields
- `title` -- Display name (defaults to type name)
- `pos` -- Position as `[x, y]` (defaults to `[0, 0]`)
- `properties` -- Type-specific configuration
- `inputs` / `outputs` -- Slot definitions (populated from schema registry)
- `modifiers` -- Step field modifiers (condition, foreach, while, error_handling)

## Edge

An edge connects two node slots.

```json
{
  "id": "uuid-string",
  "type": "data_flow",
  "source_id": "node-uuid-1",
  "source_slot": 0,
  "target_id": "node-uuid-2",
  "target_slot": 0
}
```

### Edge Types
- `data_flow` -- Represents `{{variable}}` references between steps (rendered as solid lines)
- `dependency` -- Represents explicit `depends_on` relationships (rendered as dashed lines)

## Graph

A graph is a collection of nodes and edges.

```json
{
  "nodes": {
    "node-uuid-1": { ... },
    "node-uuid-2": { ... }
  },
  "edges": {
    "edge-uuid-1": { ... }
  },
  "metadata": {
    "name": "my-workflow",
    "created_at": "2026-03-01T00:00:00Z"
  }
}
```

## Delta

A delta describes a single mutation to a graph, used for real-time synchronization.

```json
{
  "action": "add_node",
  "node_id": "uuid-string",
  "data": { ... },
  "timestamp": "2026-03-01T00:00:00Z",
  "detail_level": "high"
}
```

### Delta Actions
- `add_node`, `remove_node`, `update_node`
- `add_edge`, `remove_edge`
- `clear`

### Detail Levels
- `high` -- Always displayed (tool calls, LLM turns, agent spawns)
- `drill_down` -- Displayed only when user expands a subgraph (streaming tokens, recipe sub-steps)

## Node Type Registry

See the schema module for the complete registry of 22 node types across 6 categories:
- `workflow/` -- agent, bash, subrecipe, stage, context
- `math/` -- add, subtract, multiply, divide, sin, cos, clamp, compare, lerp
- `logic/` -- and, or, not, conditional
- `strings/` -- concat, template
- `events/` -- log, delay, timer
- `basic/` -- const, watch
