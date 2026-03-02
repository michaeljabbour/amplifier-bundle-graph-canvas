# Graph Canvas

You have access to the `graph_canvas` tool for creating and manipulating visual node graphs.

## Quick Reference

- Call `get_graph_state` to inspect the current graph before making changes
- Call `get_node_types` to discover available node types
- Use `add_node`, `connect_nodes`, `set_node_property` to build graphs
- Use `compile_recipe` to convert a graph into Amplifier recipe YAML
- Use `load_recipe` to populate the graph from existing recipe YAML

## When to Delegate

For complex graph design, workflow authoring, or debugging compilation issues, delegate to `graph-canvas:graph-canvas-expert`.

The expert agent carries full documentation on the graph protocol, node type registry, and recipe compilation rules.
