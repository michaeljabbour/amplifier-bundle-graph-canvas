---
name: graph-authoring
version: 0.1.0
description: Patterns and best practices for visual workflow authoring with the graph canvas
---

# Graph Authoring Patterns

## Pipeline Structures

### Linear Pipeline
The simplest pattern: each step feeds into the next.
- Node A (output: analysis) → Node B (prompt references {{analysis}}) → Node C

### Fan-Out / Fan-In
One step produces data consumed by multiple parallel steps, then results are collected:
- Use `foreach` modifier with `parallel: true` on a step node
- Set `collect: "all_results"` to gather outputs into a list

### Convergence Loop
Iterative refinement until a condition is met:
- Use `while_condition` modifier on a step node
- Set `break_when` for early exit
- Use `update_context` to feed iteration results back

## Context Variable Best Practices

- Name output variables descriptively: `code_analysis` not `result1`
- Each node's output slot name becomes the `{{variable}}` downstream nodes reference
- Sub-recipe nodes require explicit context wiring (not auto-connected)

## Stages vs Flat Steps

- Use **flat steps** for simple linear or parallel workflows
- Use **stages** when you need human approval gates between phases
- Stages and flat steps are mutually exclusive in a single recipe

## Common Mistakes

- Forgetting to set `output` on a node (downstream references will be undefined)
- Creating cycles in non-foreach contexts (compiler will reject)
- Mixing stages and flat steps in the same graph
- Using computation nodes where workflow nodes are needed (computation nodes don't compile to recipes)
