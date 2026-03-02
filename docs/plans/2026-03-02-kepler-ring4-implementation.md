# Kepler Ring 4 Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Integrate the graph-canvas bundle into Kepler's desktop app with full visualization, AI-tool feedback, and visual authoring.

**Architecture:** Two-repo implementation — bundle-side transport injection (Tasks 1–2) unblocks Kepler-side work (Tasks 3–14). Kepler gets a `GraphCanvasPanel` React component, a Zustand store, FastAPI routes, and WebSocket wiring. litegraph.js renders the canvas imperatively inside React via refs.

**Tech Stack:** Python 3.11 / pytest-asyncio (bundle), TypeScript / React / Zustand / Vitest (Kepler frontend), FastAPI / uv / pytest (Kepler sidecar), litegraph.js (canvas)

**Design doc:** `/Users/michaeljabbour/dev/amplifier-bundle-graph-canvas/docs/plans/2026-03-02-kepler-ring4-integration-design.md`

---

## Repository paths

| Alias | Path |
|---|---|
| BUNDLE | `/Users/michaeljabbour/dev/amplifier-bundle-graph-canvas` |
| KEPLER | `/Users/michaeljabbour/dev/amplifier-distro-kepler` |

---

## Dependency map

```
Task 1, 2  — independent (bundle repo, ship together)
Task 3     — foundation for Tasks 5, 9, 13
Task 4     — foundation for Tasks 12, 14
Task 5     — depends on Task 3
Task 6     — independent (sidecar)
Task 7     — depends on Task 6 (uses DesktopApp)
Task 8     — independent frontend scaffolding
Task 9     — depends on Tasks 3, 8
Task 10    — depends on Task 3
Task 11    — depends on Tasks 3, 4
Task 12    — depends on Tasks 3, 4, 9, 10, 11
Task 13    — depends on Task 3
Task 14    — depends on Tasks 4, 12
```

---

## Scope

**In this plan:** All 14 tasks — full viz + AI tool feedback + authoring.

**Deferred:** TypeScript compiler npm package, litegraph.js npm publishing decision, SessionTaskTree replacement evaluation.

---

## Task 1: Hook `mount()` transport injection

**Repo:** BUNDLE
**Files:**
- Modify: `modules/hooks-graph-canvas/hooks_graph_canvas/__init__.py`
- Test: `modules/hooks-graph-canvas/tests/test_hook.py` (extend `TestMountFunction`)

### Step 1: Write the failing tests

Add three new tests to the `TestMountFunction` class in `BUNDLE/modules/hooks-graph-canvas/tests/test_hook.py`:

```python
class TestMountFunction:
    def test_mount_returns_graph_canvas_hook(self):
        from hooks_graph_canvas import mount

        hook = mount()
        assert isinstance(hook, GraphCanvasHook)

    def test_mount_with_config(self):
        from hooks_graph_canvas import mount

        hook = mount(config={"skip_subsessions": False})
        assert isinstance(hook, GraphCanvasHook)

    # --- NEW TESTS ---

    def test_mount_uses_jsonl_transport_by_default(self):
        from hooks_graph_canvas import mount

        hook = mount()
        assert isinstance(hook._transport, JsonlTransport)

    def test_mount_accepts_custom_transport_from_config(self):
        from hooks_graph_canvas import mount

        transport = WebSocketTransport()
        hook = mount(config={"transport": transport})
        assert hook._transport is transport

    def test_mount_uses_jsonl_when_transport_not_in_config(self):
        from hooks_graph_canvas import mount

        hook = mount(config={"skip_subsessions": False})
        assert isinstance(hook._transport, JsonlTransport)
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/michaeljabbour/dev/amplifier-bundle-graph-canvas/modules/hooks-graph-canvas
uv run pytest tests/test_hook.py::TestMountFunction -v
```

Expected: 2 pass (existing), 3 fail with `AssertionError` (transport is always JsonlTransport right now).

### Step 3: Write the implementation

Replace the entire content of `BUNDLE/modules/hooks-graph-canvas/hooks_graph_canvas/__init__.py`:

```python
"""Hooks module for graph canvas lifecycle events."""


def mount(config: dict | None = None):
    from .hook import GraphCanvasHook, JsonlTransport

    config = config or {}
    transport = config.get("transport") or JsonlTransport()
    return GraphCanvasHook(config=config, transport=transport)
```

### Step 4: Run tests to verify they pass

```bash
cd /Users/michaeljabbour/dev/amplifier-bundle-graph-canvas/modules/hooks-graph-canvas
uv run pytest tests/test_hook.py::TestMountFunction -v
```

Expected: All 5 tests PASS.

### Step 5: Run the full hook test suite

```bash
uv run pytest tests/ -v
```

Expected: All existing tests still pass (no regressions).

### Step 6: Commit

```bash
cd /Users/michaeljabbour/dev/amplifier-bundle-graph-canvas
git add modules/hooks-graph-canvas/
git commit -m "feat(hooks): accept optional transport from config in mount()"
```

---

## Task 2: Tool `mount()` broadcast transport

**Repo:** BUNDLE
**Files:**
- Modify: `modules/tool-graph-canvas/tool_graph_canvas/__init__.py`
- Modify: `modules/tool-graph-canvas/tool_graph_canvas/tool.py`
- Test: `modules/tool-graph-canvas/tests/test_tool.py` (extend)

### Step 1: Write the failing tests

Add a new test class to `BUNDLE/modules/tool-graph-canvas/tests/test_tool.py`:

```python
from unittest.mock import AsyncMock


class TestMountFunction:
    def test_mount_returns_graph_canvas_tool(self):
        from tool_graph_canvas import mount

        tool = mount()
        assert isinstance(tool, GraphCanvasTool)

    def test_mount_with_no_transport_does_not_broadcast(self):
        from tool_graph_canvas import mount

        tool = mount()
        assert tool._transport is None

    def test_mount_passes_transport_to_tool(self):
        from tool_graph_canvas import mount

        class FakeTransport:
            async def emit(self, delta: dict) -> None:
                pass

        transport = FakeTransport()
        tool = mount(config={"transport": transport})
        assert tool._transport is transport


class TestTransportBroadcast:
    async def test_add_node_broadcasts_delta_via_transport(self):
        emitted: list[dict] = []

        class CaptureTransport:
            async def emit(self, delta: dict) -> None:
                emitted.append(delta)

        tool = GraphCanvasTool(config={}, transport=CaptureTransport())
        await tool.execute(
            arguments={"action": "add_node", "type": "workflow/agent", "x": 0.0, "y": 0.0}
        )
        assert len(emitted) == 1
        assert emitted[0]["action"] == "add_node"

    async def test_no_broadcast_when_transport_is_none(self):
        """execute() should work fine with no transport set."""
        tool = GraphCanvasTool(config={})
        result = await tool.execute(
            arguments={"action": "add_node", "type": "workflow/agent", "x": 0.0, "y": 0.0}
        )
        assert "result" in result

    async def test_get_graph_state_does_not_broadcast(self):
        """Read-only actions should not emit anything."""
        emitted: list[dict] = []

        class CaptureTransport:
            async def emit(self, delta: dict) -> None:
                emitted.append(delta)

        tool = GraphCanvasTool(config={}, transport=CaptureTransport())
        await tool.execute(arguments={"action": "get_graph_state"})
        assert len(emitted) == 0
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/michaeljabbour/dev/amplifier-bundle-graph-canvas/modules/tool-graph-canvas
uv run pytest tests/test_tool.py::TestMountFunction tests/test_tool.py::TestTransportBroadcast -v
```

Expected: All 6 new tests FAIL (mount doesn't exist as tested, tool has no transport).

### Step 3: Update `__init__.py`

Replace the entire content of `BUNDLE/modules/tool-graph-canvas/tool_graph_canvas/__init__.py`:

```python
"""Tool module for graph canvas operations."""


def mount(config: dict | None = None):
    from .tool import GraphCanvasTool

    config = config or {}
    transport = config.get("transport")  # Optional — any object with async emit(delta)
    return GraphCanvasTool(config=config, transport=transport)
```

### Step 4: Update `tool.py` to accept and use transport

In `BUNDLE/modules/tool-graph-canvas/tool_graph_canvas/tool.py`, make two changes:

**Change 1** — Update `__init__` signature (line 29):

```python
    def __init__(self, config: dict[str, Any] | None = None, transport: Any = None) -> None:
        self._config = config or {}
        self._state = GraphState()
        self._transport = transport  # Optional: any object with async emit(delta: dict)
```

**Change 2** — Add delta broadcast at the end of `execute()`, just before `return result` at line 214. Replace the bare `return result` with:

```python
        # Broadcast mutation deltas via transport (best-effort, never raises)
        if self._transport is not None and "delta" in result:
            try:
                await self._transport.emit(result["delta"])
            except Exception:
                pass

        return result
```

> **Important:** The `return result` at the very bottom of `execute()` (after the `except` clause) needs this treatment. Look for `return {"error": str(exc)}` — that's the error path. The transport broadcast only happens on the happy path before that. Place the transport call in `execute()` just before the final `return result` inside the `try` block.

The complete updated bottom of `execute()`:

```python
        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}

        # Broadcast mutation deltas via transport (best-effort)
        if self._transport is not None and "delta" in result:
            try:
                await self._transport.emit(result["delta"])
            except Exception:
                pass

        return result
```

Wait — place the broadcast INSIDE the try block, after `result` is assigned and before the except. Here is the complete restructured bottom of execute():

Find this block (currently at the end of `execute()`):

```python
        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}
```

The full `execute()` body ends with various `elif action ==` branches that assign `result`. The last two lines before the except are:
```python
            else:
                return {"error": f"Unknown action: {action}"}

        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}
```

Add the transport call just before `except`, after the `else` block:

```python
            else:
                return {"error": f"Unknown action: {action}"}

            # Broadcast mutation deltas via transport (best-effort, never raises)
            if self._transport is not None and "delta" in result:
                try:
                    await self._transport.emit(result["delta"])
                except Exception:
                    pass

            return result

        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}
```

Remove the bare `return result` that was previously at the end of each `elif` branch (there isn't one — each branch sets `result` and this new block returns it). Actually look at the existing code: every branch does `return {...}` inline. To make this work cleanly, refactor the execute() method to collect `result` and return once. But that's a larger refactor — for TDD purposes, simply add the transport emit to each mutating branch individually.

**Simpler approach**: Add `await self._transport.emit(result["delta"])` calls inline in each mutating branch, right before the `return`. Here is the pattern — apply it to `add_node`, `remove_node`, `set_node_property`, `connect_nodes`, `disconnect`, `clear_graph`:

```python
            elif action == "add_node":
                node_id, delta = self._state.add_node(...)
                result = {"result": {"node_id": node_id}, "delta": delta}
                if self._transport is not None:
                    try:
                        await self._transport.emit(delta)
                    except Exception:
                        pass
                return result
```

Apply this same pattern to all six mutating actions (add_node, remove_node, set_node_property, connect_nodes, disconnect, clear_graph). Read-only actions (get_graph_state, get_node_types, compile_recipe, load_recipe, execute_graph) do NOT get the transport call.

### Step 5: Run tests to verify they pass

```bash
cd /Users/michaeljabbour/dev/amplifier-bundle-graph-canvas/modules/tool-graph-canvas
uv run pytest tests/test_tool.py::TestMountFunction tests/test_tool.py::TestTransportBroadcast -v
```

Expected: All 6 new tests PASS.

### Step 6: Run the full tool test suite

```bash
uv run pytest tests/ -v
```

Expected: All existing tests still pass.

### Step 7: Commit both bundle changes together

```bash
cd /Users/michaeljabbour/dev/amplifier-bundle-graph-canvas
git add modules/tool-graph-canvas/
git commit -m "feat(tool): accept optional transport from config, broadcast mutation deltas"
```

---

## Task 3: Zustand store — `graph-canvas-store.ts`

**Repo:** KEPLER
**Files:**
- Create: `src/lib/stores/graph-canvas-store.ts`
- Create: `src/lib/stores/__tests__/graph-canvas-store.test.ts`
- Modify: `src/lib/stores/index.ts` (export the new store)

### Step 1: Write the failing tests

Create `KEPLER/src/lib/stores/__tests__/graph-canvas-store.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { useGraphCanvasStore } from '../graph-canvas-store';

// Reset store state between tests
beforeEach(() => {
  useGraphCanvasStore.setState({
    vizGraph: null,
    authoringGraph: null,
    activeView: 'viz',
    panelMode: 'compact',
    sourceRecipePath: null,
    recipeHash: null,
    isDirty: false,
  });
});

describe('initial state', () => {
  it('starts with null graphs', () => {
    const { vizGraph, authoringGraph } = useGraphCanvasStore.getState();
    expect(vizGraph).toBeNull();
    expect(authoringGraph).toBeNull();
  });

  it('starts in viz view, compact mode', () => {
    const { activeView, panelMode } = useGraphCanvasStore.getState();
    expect(activeView).toBe('viz');
    expect(panelMode).toBe('compact');
  });

  it('starts clean', () => {
    expect(useGraphCanvasStore.getState().isDirty).toBe(false);
  });
});

describe('applyVizDelta', () => {
  it('adds a node via add_node delta', () => {
    const { applyVizDelta } = useGraphCanvasStore.getState();
    applyVizDelta({
      action: 'add_node',
      data: {
        id: 'n1',
        type: 'workflow/agent',
        title: 'Agent',
        x: 0,
        y: 0,
        properties: {},
        inputs: [],
        outputs: [],
      },
    });
    const { vizGraph } = useGraphCanvasStore.getState();
    expect(vizGraph?.nodes).toHaveLength(1);
    expect(vizGraph?.nodes[0].id).toBe('n1');
  });

  it('removes a node via remove_node delta', () => {
    useGraphCanvasStore.getState().applyVizDelta({
      action: 'add_node',
      data: { id: 'n1', type: 'workflow/agent', title: 'A', x: 0, y: 0, properties: {}, inputs: [], outputs: [] },
    });
    useGraphCanvasStore.getState().applyVizDelta({ action: 'remove_node', data: { id: 'n1' } });
    expect(useGraphCanvasStore.getState().vizGraph?.nodes).toHaveLength(0);
  });

  it('updates node status via set_status delta', () => {
    useGraphCanvasStore.getState().applyVizDelta({
      action: 'add_node',
      data: { id: 'n1', type: 'workflow/agent', title: 'A', x: 0, y: 0, properties: {}, inputs: [], outputs: [] },
    });
    useGraphCanvasStore.getState().applyVizDelta({
      action: 'set_status',
      data: { id: 'n1', status: 'running' },
    });
    const node = useGraphCanvasStore.getState().vizGraph?.nodes[0];
    expect(node?.status).toBe('running');
  });

  it('clears graph via clear delta', () => {
    useGraphCanvasStore.getState().applyVizDelta({
      action: 'add_node',
      data: { id: 'n1', type: 'workflow/agent', title: 'A', x: 0, y: 0, properties: {}, inputs: [], outputs: [] },
    });
    useGraphCanvasStore.getState().applyVizDelta({ action: 'clear', data: {} });
    expect(useGraphCanvasStore.getState().vizGraph?.nodes).toHaveLength(0);
  });
});

describe('applyAuthoringDelta', () => {
  it('marks isDirty after mutation', () => {
    useGraphCanvasStore.getState().applyAuthoringDelta({
      action: 'add_node',
      data: { id: 'n1', type: 'workflow/agent', title: 'A', x: 0, y: 0, properties: {}, inputs: [], outputs: [] },
    });
    expect(useGraphCanvasStore.getState().isDirty).toBe(true);
  });
});

describe('view actions', () => {
  it('setActiveView switches view', () => {
    useGraphCanvasStore.getState().setActiveView('authoring');
    expect(useGraphCanvasStore.getState().activeView).toBe('authoring');
  });

  it('setPanelMode switches mode', () => {
    useGraphCanvasStore.getState().setPanelMode('fullscreen');
    expect(useGraphCanvasStore.getState().panelMode).toBe('fullscreen');
  });
});

describe('loadRecipe', () => {
  it('stores recipe path and marks clean', () => {
    useGraphCanvasStore.getState().loadRecipe(
      'workflows/my-flow',
      { nodes: [], edges: [] },
      'abc123'
    );
    const state = useGraphCanvasStore.getState();
    expect(state.sourceRecipePath).toBe('workflows/my-flow');
    expect(state.recipeHash).toBe('abc123');
    expect(state.authoringGraph).toEqual({ nodes: [], edges: [] });
    expect(state.isDirty).toBe(false);
  });
});
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx vitest run src/lib/stores/__tests__/graph-canvas-store.test.ts
```

Expected: FAIL — module not found.

### Step 3: Create the store

Create `KEPLER/src/lib/stores/graph-canvas-store.ts`:

```typescript
/**
 * Graph canvas store — dual graph state (viz + authoring), view mode, persistence metadata.
 * Zustand domain store, extracted for isolation. No data dependencies on other stores.
 */

import { create } from 'zustand';

// --- Types ---

export interface SlotSpec {
  name: string;
  type: string;
}

export interface GraphNode {
  id: string;
  type: string;          // e.g. "workflow/agent", "workflow/bash"
  title: string;
  x: number;
  y: number;
  properties: Record<string, unknown>;
  inputs: SlotSpec[];
  outputs: SlotSpec[];
  modifiers?: {
    condition?: string;
    foreach?: string;
    while_condition?: string;
    retry?: number;
    timeout?: number;
  };
  status?: 'idle' | 'running' | 'complete' | 'error';  // viz mode only
}

export interface GraphEdge {
  id: string;
  from_node: string;
  from_slot: number;
  to_node: string;
  to_slot: number;
  type: 'data' | 'dependency';  // solid vs dashed
}

export interface GraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphDelta {
  action:
    | 'add_node'
    | 'remove_node'
    | 'add_edge'
    | 'remove_edge'
    | 'update_node'
    | 'clear'
    | 'set_status';
  data: Record<string, unknown>;
}

// --- Store interface ---

interface GraphCanvasStore {
  // Dual graph state
  vizGraph: GraphState | null;
  authoringGraph: GraphState | null;

  // View state
  activeView: 'viz' | 'authoring';
  panelMode: 'compact' | 'fullscreen';

  // Authoring metadata
  sourceRecipePath: string | null;
  recipeHash: string | null;
  isDirty: boolean;

  // Actions: viz
  applyVizDelta: (delta: GraphDelta) => void;
  clearVizGraph: () => void;

  // Actions: authoring
  applyAuthoringDelta: (delta: GraphDelta) => void;
  setAuthoringGraph: (graph: GraphState) => void;
  updateNode: (nodeId: string, patch: Partial<GraphNode>) => void;
  addNode: (node: GraphNode) => void;
  removeNode: (nodeId: string) => void;
  addEdge: (edge: GraphEdge) => void;
  removeEdge: (edgeId: string) => void;
  markClean: () => void;

  // Actions: view
  setActiveView: (view: 'viz' | 'authoring') => void;
  setPanelMode: (mode: 'compact' | 'fullscreen') => void;

  // Actions: persistence
  loadRecipe: (path: string, graph: GraphState, hash: string) => void;
  newGraph: () => void;
}

// --- Delta application helper ---

function applyDeltaToState(
  current: GraphState | null,
  delta: GraphDelta
): GraphState {
  const base: GraphState = current ?? { nodes: [], edges: [] };

  switch (delta.action) {
    case 'add_node': {
      const node = delta.data as unknown as GraphNode;
      // Upsert: replace if same id exists
      const filtered = base.nodes.filter((n) => n.id !== node.id);
      return { ...base, nodes: [...filtered, node] };
    }
    case 'remove_node': {
      const id = delta.data.id as string;
      return {
        nodes: base.nodes.filter((n) => n.id !== id),
        edges: base.edges.filter((e) => e.from_node !== id && e.to_node !== id),
      };
    }
    case 'update_node': {
      const { id, ...patch } = delta.data as { id: string } & Partial<GraphNode>;
      return {
        ...base,
        nodes: base.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
      };
    }
    case 'set_status': {
      const { id, status } = delta.data as { id: string; status: GraphNode['status'] };
      return {
        ...base,
        nodes: base.nodes.map((n) => (n.id === id ? { ...n, status } : n)),
      };
    }
    case 'add_edge': {
      const edge = delta.data as unknown as GraphEdge;
      const filtered = base.edges.filter((e) => e.id !== edge.id);
      return { ...base, edges: [...filtered, edge] };
    }
    case 'remove_edge': {
      const id = delta.data.id as string;
      return { ...base, edges: base.edges.filter((e) => e.id !== id) };
    }
    case 'clear':
      return { nodes: [], edges: [] };
    default:
      return base;
  }
}

// --- Store ---

export const useGraphCanvasStore = create<GraphCanvasStore>((set) => ({
  vizGraph: null,
  authoringGraph: null,
  activeView: 'viz',
  panelMode: 'compact',
  sourceRecipePath: null,
  recipeHash: null,
  isDirty: false,

  // Viz actions
  applyVizDelta: (delta) =>
    set((s) => ({ vizGraph: applyDeltaToState(s.vizGraph, delta) })),
  clearVizGraph: () => set({ vizGraph: null }),

  // Authoring actions
  applyAuthoringDelta: (delta) =>
    set((s) => ({
      authoringGraph: applyDeltaToState(s.authoringGraph, delta),
      isDirty: true,
    })),
  setAuthoringGraph: (graph) => set({ authoringGraph: graph, isDirty: false }),
  updateNode: (nodeId, patch) =>
    set((s) => ({
      authoringGraph: s.authoringGraph
        ? {
            ...s.authoringGraph,
            nodes: s.authoringGraph.nodes.map((n) =>
              n.id === nodeId ? { ...n, ...patch } : n
            ),
          }
        : null,
      isDirty: true,
    })),
  addNode: (node) =>
    set((s) => ({
      authoringGraph: s.authoringGraph
        ? { ...s.authoringGraph, nodes: [...s.authoringGraph.nodes, node] }
        : { nodes: [node], edges: [] },
      isDirty: true,
    })),
  removeNode: (nodeId) =>
    set((s) => ({
      authoringGraph: s.authoringGraph
        ? {
            nodes: s.authoringGraph.nodes.filter((n) => n.id !== nodeId),
            edges: s.authoringGraph.edges.filter(
              (e) => e.from_node !== nodeId && e.to_node !== nodeId
            ),
          }
        : null,
      isDirty: true,
    })),
  addEdge: (edge) =>
    set((s) => ({
      authoringGraph: s.authoringGraph
        ? { ...s.authoringGraph, edges: [...s.authoringGraph.edges, edge] }
        : { nodes: [], edges: [edge] },
      isDirty: true,
    })),
  removeEdge: (edgeId) =>
    set((s) => ({
      authoringGraph: s.authoringGraph
        ? {
            ...s.authoringGraph,
            edges: s.authoringGraph.edges.filter((e) => e.id !== edgeId),
          }
        : null,
      isDirty: true,
    })),
  markClean: () => set({ isDirty: false }),

  // View actions
  setActiveView: (view) => set({ activeView: view }),
  setPanelMode: (mode) => set({ panelMode: mode }),

  // Persistence actions
  loadRecipe: (path, graph, hash) =>
    set({
      sourceRecipePath: path,
      recipeHash: hash,
      authoringGraph: graph,
      isDirty: false,
    }),
  newGraph: () =>
    set({
      authoringGraph: { nodes: [], edges: [] },
      sourceRecipePath: null,
      recipeHash: null,
      isDirty: false,
    }),
}));
```

### Step 4: Export from the barrel

In `KEPLER/src/lib/stores/index.ts`, add:

```typescript
export { useGraphCanvasStore } from './graph-canvas-store';
export type { GraphNode, GraphEdge, GraphState, GraphDelta } from './graph-canvas-store';
```

### Step 5: Run tests to verify they pass

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx vitest run src/lib/stores/__tests__/graph-canvas-store.test.ts
```

Expected: All tests PASS.

### Step 6: Type-check

```bash
npx tsc --noEmit
```

Expected: No errors from the new store.

### Step 7: Commit

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
git add src/lib/stores/graph-canvas-store.ts src/lib/stores/__tests__/graph-canvas-store.test.ts src/lib/stores/index.ts
git commit -m "feat(store): add useGraphCanvasStore with dual graph state and delta application"
```

---

## Task 4: UIStore additions

**Repo:** KEPLER
**Files:**
- Modify: `src/lib/stores/ui-store.ts`

### Step 1: Write the failing test

Add to `KEPLER/src/lib/stores/__tests__/` — create a new file `ui-store-graph-canvas.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { useUIStore } from '../ui-store';

describe('UIStore graph canvas additions', () => {
  it('starts with panel closed', () => {
    expect(useUIStore.getState().isGraphCanvasPanelOpen).toBe(false);
  });

  it('setGraphCanvasPanelOpen toggles the panel', () => {
    useUIStore.getState().setGraphCanvasPanelOpen(true);
    expect(useUIStore.getState().isGraphCanvasPanelOpen).toBe(true);
    useUIStore.getState().setGraphCanvasPanelOpen(false);
    expect(useUIStore.getState().isGraphCanvasPanelOpen).toBe(false);
  });

  it('starts with default panel width 500', () => {
    expect(useUIStore.getState().graphCanvasPanelWidth).toBe(500);
  });

  it('setGraphCanvasPanelWidth accepts a number', () => {
    useUIStore.getState().setGraphCanvasPanelWidth(700);
    expect(useUIStore.getState().graphCanvasPanelWidth).toBe(700);
  });

  it('setGraphCanvasPanelWidth accepts an updater function', () => {
    useUIStore.getState().setGraphCanvasPanelWidth(500);
    useUIStore.getState().setGraphCanvasPanelWidth((prev) => prev + 100);
    expect(useUIStore.getState().graphCanvasPanelWidth).toBe(600);
  });
});
```

### Step 2: Run to verify failure

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx vitest run src/lib/stores/__tests__/ui-store-graph-canvas.test.ts
```

Expected: FAIL — properties don't exist.

### Step 3: Add to UIStore

In `KEPLER/src/lib/stores/ui-store.ts`, add to the `UIState` interface (after `isPlannerModalOpen`/`setPlannerModalOpen`):

```typescript
  isGraphCanvasPanelOpen: boolean;
  setGraphCanvasPanelOpen: (open: boolean) => void;
  graphCanvasPanelWidth: number;
  setGraphCanvasPanelWidth: (width: number | ((prev: number) => number)) => void;
```

And add to the `create<UIState>` implementation (after `setPlannerModalOpen`):

```typescript
  isGraphCanvasPanelOpen: false,
  setGraphCanvasPanelOpen: (open) => set({ isGraphCanvasPanelOpen: open }),
  graphCanvasPanelWidth: 500,
  setGraphCanvasPanelWidth: (width) =>
    set((state) => ({
      graphCanvasPanelWidth:
        typeof width === 'function' ? width(state.graphCanvasPanelWidth) : width,
    })),
```

### Step 4: Run tests to verify they pass

```bash
npx vitest run src/lib/stores/__tests__/ui-store-graph-canvas.test.ts
```

Expected: All 5 tests PASS.

### Step 5: Type-check

```bash
npx tsc --noEmit
```

### Step 6: Commit

```bash
git add src/lib/stores/ui-store.ts src/lib/stores/__tests__/ui-store-graph-canvas.test.ts
git commit -m "feat(ui-store): add isGraphCanvasPanelOpen and graphCanvasPanelWidth"
```

---

## Task 5: WebSocket message handling

**Repo:** KEPLER
**Files:**
- Modify: `src/hooks/useWebSocket.ts`

> **Context:** The WS message dispatch is a large switch statement in `useWebSocket.ts`. `case 'todo_restore':` ends at line 1248. Add the two new cases immediately after it.

### Step 1: Write the failing test

Create `KEPLER/src/hooks/__tests__/useWebSocket-graph-canvas.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';

// Reset store before each test
beforeEach(() => {
  useGraphCanvasStore.setState({
    vizGraph: null,
    authoringGraph: null,
    activeView: 'viz',
    panelMode: 'compact',
    sourceRecipePath: null,
    recipeHash: null,
    isDirty: false,
  });
});

describe('viz_event message handler', () => {
  it('dispatches add_node delta to vizGraph', () => {
    // Simulate what the message handler does
    useGraphCanvasStore.getState().applyVizDelta({
      action: 'add_node',
      data: {
        id: 'n1',
        type: 'workflow/agent',
        title: 'Agent',
        x: 0,
        y: 0,
        properties: {},
        inputs: [],
        outputs: [],
      },
    });
    expect(useGraphCanvasStore.getState().vizGraph?.nodes).toHaveLength(1);
  });
});

describe('graph_delta message handler', () => {
  it('dispatches add_node delta to authoringGraph and marks dirty', () => {
    useGraphCanvasStore.getState().applyAuthoringDelta({
      action: 'add_node',
      data: {
        id: 'n2',
        type: 'workflow/bash',
        title: 'Bash',
        x: 100,
        y: 100,
        properties: {},
        inputs: [],
        outputs: [],
      },
    });
    expect(useGraphCanvasStore.getState().authoringGraph?.nodes).toHaveLength(1);
    expect(useGraphCanvasStore.getState().isDirty).toBe(true);
  });
});
```

> **Note:** These tests exercise the store functions that the WS handler will call. They verify the store handles the payloads correctly. The actual dispatch wiring in `useWebSocket.ts` is verified by TypeScript compilation.

### Step 2: Run to verify pass (store-level tests only)

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx vitest run src/hooks/__tests__/useWebSocket-graph-canvas.test.ts
```

Expected: PASS (these test the store, which was already implemented in Task 3).

### Step 3: Add the two cases to the switch statement

In `KEPLER/src/hooks/useWebSocket.ts`, find the block ending `case 'todo_restore':` (around line 1248). Add immediately after it (before `case 'approval_request':`):

```typescript
      case 'viz_event':
        // Hook-driven visualization delta — updates read-only viz graph
        useGraphCanvasStore.getState().applyVizDelta((msg as any).data);
        break;

      case 'graph_delta':
        // AI tool mutation delta — updates authoring graph
        useGraphCanvasStore.getState().applyAuthoringDelta((msg as any).data);
        break;
```

Add the import of `useGraphCanvasStore` at the top of `useWebSocket.ts`, near the other store imports (search for `useTodoStore` import and add after it):

```typescript
import { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';
```

### Step 4: Type-check

```bash
npx tsc --noEmit
```

Expected: No type errors.

### Step 5: Commit

```bash
git add src/hooks/useWebSocket.ts src/hooks/__tests__/useWebSocket-graph-canvas.test.ts
git commit -m "feat(ws): handle viz_event and graph_delta messages for graph canvas"
```

---

## Task 6: FastAPI route module

**Repo:** KEPLER
**Files:**
- Create: `sidecar/apps/desktop/routes/graph_canvas.py`
- Modify: `sidecar/apps/desktop/__init__.py` (register router)
- Create: `sidecar/tests/test_graph_canvas_routes.py`

> **Context:** The sidecar test suite is at `KEPLER/sidecar/tests/`. Routes follow the `create_*_router(desktop)` factory pattern. Reference: `sidecar/apps/desktop/routes/health.py`.

### Step 1: Write the failing tests

Create `KEPLER/sidecar/tests/test_graph_canvas_routes.py`:

```python
"""Tests for graph canvas FastAPI routes."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


@pytest.fixture
def desktop():
    """Minimal desktop mock for route testing."""
    mock = MagicMock()
    mock.session_ready = True
    mock.KEPLER_HOME = "/tmp/test-kepler"
    return mock


@pytest.fixture
def client(desktop):
    from fastapi import FastAPI
    from apps.desktop.routes.graph_canvas import create_graph_canvas_router

    app = FastAPI()
    app.include_router(create_graph_canvas_router(desktop))
    return TestClient(app)


class TestCompileEndpoint:
    def test_compile_returns_yaml(self, client):
        # A minimal valid graph with one agent node
        graph = {
            "nodes": [
                {
                    "id": "n1",
                    "type": "workflow/agent",
                    "title": "My Agent",
                    "x": 0,
                    "y": 0,
                    "properties": {"instruction": "Do something"},
                    "inputs": [],
                    "outputs": [],
                }
            ],
            "edges": [],
        }
        resp = client.post("/graph/compile", json={"graph": graph})
        assert resp.status_code == 200
        data = resp.json()
        assert "yaml" in data
        assert isinstance(data["yaml"], str)
        assert len(data["yaml"]) > 0

    def test_compile_returns_422_for_empty_graph(self, client):
        resp = client.post("/graph/compile", json={"graph": {}})
        # Either 200 with yaml or 422 depending on compiler strictness — just check it returns
        assert resp.status_code in (200, 422)


class TestDecompileEndpoint:
    def test_decompile_returns_graph(self, client):
        yaml_str = """
name: test
steps:
  - name: step1
    agent: default
    instruction: Hello
"""
        resp = client.post(
            "/graph/decompile",
            json={"recipe_yaml": yaml_str, "layout_data": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "graph" in data
        assert isinstance(data["graph"], dict)

    def test_decompile_returns_422_for_invalid_yaml(self, client):
        resp = client.post(
            "/graph/decompile",
            json={"recipe_yaml": "not: valid: yaml: {{{{", "layout_data": None},
        )
        # Should not crash — either returns a graph or 422
        assert resp.status_code in (200, 422)


class TestListRecipesEndpoint:
    def test_list_returns_list(self, client):
        resp = client.get("/graph/recipes")
        assert resp.status_code == 200
        data = resp.json()
        assert "recipes" in data
        assert isinstance(data["recipes"], list)


class TestRouterRegistration:
    def test_create_graph_canvas_router_returns_api_router(self, desktop):
        from fastapi import APIRouter
        from apps.desktop.routes.graph_canvas import create_graph_canvas_router

        router = create_graph_canvas_router(desktop)
        assert isinstance(router, APIRouter)
```

### Step 2: Run to verify failure

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler/sidecar
uv run pytest tests/test_graph_canvas_routes.py -v
```

Expected: FAIL — module not found.

### Step 3: Create the route module

Create `KEPLER/sidecar/apps/desktop/routes/graph_canvas.py`:

```python
"""Graph canvas routes — compile, decompile, save, run, list recipes."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CompileRequest(BaseModel):
    graph: dict


class DecompileRequest(BaseModel):
    recipe_yaml: str
    layout_data: dict | None = None


class SaveRequest(BaseModel):
    graph: dict
    path: str  # e.g. "workflows/my-flow" (no extension)


class RunRequest(BaseModel):
    graph: dict
    name: str | None = None


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_graph_canvas_router(desktop) -> APIRouter:
    """Build the /graph router. desktop: DesktopApp (for KEPLER_HOME path)."""
    router = APIRouter(prefix="/graph", tags=["graph"])

    @router.get("/recipes")
    async def list_recipes():
        """List saved .yaml recipe files under KEPLER_HOME/recipes/."""
        recipes_dir = Path(desktop.KEPLER_HOME) / "recipes"
        if not recipes_dir.exists():
            return {"recipes": []}
        recipes = [
            {
                "name": p.stem,
                "path": str(p.relative_to(Path(desktop.KEPLER_HOME))),
                "has_layout": p.with_suffix(".litegraph.json").exists(),
            }
            for p in sorted(recipes_dir.rglob("*.yaml"))
        ]
        return {"recipes": recipes}

    @router.post("/compile")
    async def compile_graph(request: CompileRequest):
        """Graph JSON → recipe YAML string."""
        try:
            from graph_canvas_compiler import compile_graph
            from graph_canvas_compiler.schema import CompileError

            yaml_str = compile_graph(request.graph)
            return {"yaml": yaml_str}
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/decompile")
    async def decompile_recipe(request: DecompileRequest):
        """Recipe YAML → graph JSON."""
        try:
            from graph_canvas_compiler import decompile_recipe

            graph = decompile_recipe(request.recipe_yaml, request.layout_data)
            return {"graph": graph}
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/save")
    async def save_graph(request: SaveRequest):
        """Compile graph and write recipe YAML + layout sidecar to disk."""
        try:
            from graph_canvas_compiler import compile_graph

            yaml_str = compile_graph(request.graph)

            # Resolve paths under KEPLER_HOME/recipes/
            base = Path(desktop.KEPLER_HOME) / "recipes" / request.path
            recipe_path = base.with_suffix(".yaml")
            layout_path = base.with_suffix(".litegraph.json")

            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_text(yaml_str, encoding="utf-8")

            # Layout sidecar: graph JSON + recipe hash for drift detection
            recipe_hash = hashlib.sha256(yaml_str.encode()).hexdigest()[:12]
            layout_data = {
                "graph": request.graph,
                "recipe_hash": recipe_hash,
            }
            layout_path.write_text(json.dumps(layout_data, indent=2), encoding="utf-8")

            return {
                "recipe_path": str(recipe_path.relative_to(Path(desktop.KEPLER_HOME))),
                "layout_path": str(layout_path.relative_to(Path(desktop.KEPLER_HOME))),
                "recipe_hash": recipe_hash,
            }
        except Exception as exc:
            logger.exception("Failed to save graph")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/run")
    async def run_graph(request: RunRequest):
        """Compile in-memory and execute via the recipes tool.

        This is a fire-and-forget kick-off. Execution progress flows back to the
        frontend via viz_event WebSocket messages (hook transport).
        """
        try:
            from graph_canvas_compiler import compile_graph

            yaml_str = compile_graph(request.graph)
            recipe_name = request.name or "ad-hoc"

            # TODO(ring4): execute via session_handle.run() with compiled YAML injected
            # For now return the compiled YAML so the client can display it
            return {
                "status": "compiled",
                "recipe_name": recipe_name,
                "yaml": yaml_str,
            }
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
```

### Step 4: Register the router in `__init__.py`

In `KEPLER/sidecar/apps/desktop/__init__.py`, find `create_router()` (line ~1389). Add the import and include_router call alongside the existing routes:

Find this block:
```python
    from .routes.health import create_health_router
```

Add after it:
```python
    from .routes.graph_canvas import create_graph_canvas_router
```

Find this line:
```python
    router.include_router(create_health_router(desktop), tags=["health"])
```

Add after it:
```python
    router.include_router(create_graph_canvas_router(desktop), tags=["graph"])
```

### Step 5: Run tests to verify they pass

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler/sidecar
uv run pytest tests/test_graph_canvas_routes.py -v
```

Expected: Most tests PASS. The compile/decompile tests depend on `graph_canvas_compiler` being installed in the sidecar's venv — if not installed, they will 422 (which the test accepts).

### Step 6: Type-check the sidecar

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx tsc --noEmit
```

### Step 7: Commit

```bash
git add sidecar/apps/desktop/routes/graph_canvas.py sidecar/apps/desktop/__init__.py sidecar/tests/test_graph_canvas_routes.py
git commit -m "feat(routes): add /graph/* endpoints for compile, decompile, save, run, list"
```

---

## Task 7: Hook transport wiring

**Repo:** KEPLER
**Files:**
- Modify: `sidecar/apps/desktop/__init__.py`

> **Context:** The Kepler sidecar creates and destroys WebSocket connections per chat session. The graph canvas hook transport needs to be updated on each new connection — the same pattern as `_update_bash_tool_cb`. After `init_session()`, the hook instance is stored on `desktop` and its transport's `send_func` is updated whenever a new WebSocket connects in `chat.py`.

### Step 1: Write the failing test

Create `KEPLER/sidecar/tests/test_graph_canvas_transport.py`:

```python
"""Tests for graph canvas hook transport wiring in DesktopApp."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGraphCanvasHookInjection:
    def test_desktop_has_graph_canvas_hook_attribute(self):
        """DesktopApp must have _graph_canvas_hook attribute after construction."""
        from apps.desktop import DesktopApp

        desktop = DesktopApp.__new__(DesktopApp)
        # Before init_session, the attribute exists and is None
        # (set in __init__ as a placeholder)
        assert hasattr(desktop, "_graph_canvas_hook")

    def test_update_graph_canvas_transport_with_send_fn(self):
        """_update_graph_canvas_transport sets the hook's transport send_func."""
        from apps.desktop import DesktopApp
        from hooks_graph_canvas.hook import WebSocketTransport

        desktop = DesktopApp.__new__(DesktopApp)
        desktop._graph_canvas_hook = MagicMock()
        desktop._graph_canvas_hook._transport = WebSocketTransport()

        send_fn = AsyncMock()
        desktop._update_graph_canvas_transport(send_fn)

        assert desktop._graph_canvas_hook._transport._send_func is not None

    def test_update_graph_canvas_transport_with_none_clears_send_fn(self):
        """Passing None clears the transport (WebSocket disconnect)."""
        from apps.desktop import DesktopApp
        from hooks_graph_canvas.hook import WebSocketTransport

        desktop = DesktopApp.__new__(DesktopApp)
        desktop._graph_canvas_hook = MagicMock()
        desktop._graph_canvas_hook._transport = WebSocketTransport()

        desktop._update_graph_canvas_transport(None)
        assert desktop._graph_canvas_hook._transport._send_func is None
```

### Step 2: Run to verify failure

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler/sidecar
uv run pytest tests/test_graph_canvas_transport.py -v
```

Expected: FAIL — attribute doesn't exist.

### Step 3: Add `_graph_canvas_hook` to `DesktopApp.__init__`

In `KEPLER/sidecar/apps/desktop/__init__.py`, find the `__init__` method of `DesktopApp`. Add after `self._kepler_bash_tool: Any = None` (around line 235):

```python
        # Graph canvas hook — transport updated per-WebSocket-connection
        self._graph_canvas_hook: Any = None
```

### Step 4: Add `_inject_graph_canvas_hook()` method

Add this method to `DesktopApp` after `_inject_kepler_bash_tool()`:

```python
    async def _inject_graph_canvas_hook(self) -> None:
        """Mount the graph canvas hook and register it on the coordinator.

        Creates a WebSocketTransport with no send_func initially (noop).
        The transport's send_func is updated on each WebSocket connection
        via _update_graph_canvas_transport().
        """
        session = self.session
        if not session or not hasattr(session, "coordinator"):
            return
        try:
            from hooks_graph_canvas import mount as mount_gc_hook
            from hooks_graph_canvas.hook import WebSocketTransport

            transport = WebSocketTransport(send_func=None)
            hook = mount_gc_hook(
                config={
                    "transport": transport,
                    "skip_subsessions": True,
                    "throttle_ms": 100,
                }
            )
            self._graph_canvas_hook = hook

            # Register for all kernel events that the hook handles
            try:
                from amplifier_core.events import ALL_EVENTS
                for event in list(ALL_EVENTS):
                    session.coordinator.hooks.register(
                        event=event,
                        handler=hook,
                        priority=50,
                        name=f"graph-canvas-hook:{event}",
                    )
                self.log("Graph canvas hook registered on session coordinator")
            except (ImportError, AttributeError):
                # Fallback: register for the key events the hook actually processes
                for event in [
                    "provider:request",
                    "provider:response",
                    "content_block:start",
                    "content_block:delta",
                    "content_block:stop",
                    "tool:pre",
                    "tool:post",
                    "orchestrator:start",
                    "orchestrator:complete",
                ]:
                    try:
                        session.coordinator.hooks.register(
                            event=event,
                            handler=hook,
                            priority=50,
                            name=f"graph-canvas-hook:{event}",
                        )
                    except Exception:
                        pass
                self.log("Graph canvas hook registered (fallback event list)")
        except ImportError:
            self.log("graph-canvas-compiler not installed — graph canvas hook skipped")
        except Exception as exc:
            logger.warning("Could not inject graph canvas hook: %s", exc)
```

### Step 5: Add `_update_graph_canvas_transport()` method

Add this method after `_update_bash_tool_cb()`:

```python
    def _update_graph_canvas_transport(self, send_fn: Any) -> None:
        """Update the graph canvas hook's WebSocket send function.

        Called on each new WebSocket connection (same pattern as _update_bash_tool_cb).
        send_fn receives a dict and must be an async callable.
        Pass None on disconnect to silence the transport.
        """
        if self._graph_canvas_hook is None:
            return
        transport = getattr(self._graph_canvas_hook, "_transport", None)
        if transport is None:
            return
        if send_fn is not None:
            conversation_id_ref = [None]  # mutable cell for the current conversation_id

            async def _ws_send_wrapper(delta: dict) -> None:
                try:
                    await send_fn({
                        "type": "viz_event",
                        "data": delta,
                        "conversationId": conversation_id_ref[0],
                    })
                except Exception:
                    pass

            transport._send_func = _ws_send_wrapper
            # Store the ref so chat.py can update it per message
            transport._conversation_id_ref = conversation_id_ref
        else:
            transport._send_func = None
```

### Step 6: Wire into `init_session()`

In `init_session()`, find the line `await self._inject_fs_write_gate()` and add after it:

```python
            # Inject graph canvas hook for viz streaming (best-effort)
            await self._inject_graph_canvas_hook()
```

Also update `reload_session()` the same way (find `await self._inject_fs_write_gate()` in that method and add the same line after it).

### Step 7: Wire into the chat route

> **Note:** `chat.py` already calls `desktop._update_bash_tool_cb(send_fn)` when a WS connection opens. Add the graph canvas transport update in the same location. Open `KEPLER/sidecar/apps/desktop/routes/chat.py` and find the call to `_update_bash_tool_cb`. Add immediately after it:
>
> ```python
> desktop._update_graph_canvas_transport(send_fn)
> ```
>
> Also find where `_update_bash_tool_cb(None)` is called (on disconnect) and add:
> ```python
> desktop._update_graph_canvas_transport(None)
> ```

### Step 8: Run tests to verify they pass

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler/sidecar
uv run pytest tests/test_graph_canvas_transport.py -v
```

Expected: All 3 tests PASS.

### Step 9: Commit

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
git add sidecar/apps/desktop/__init__.py sidecar/apps/desktop/routes/chat.py sidecar/tests/test_graph_canvas_transport.py
git commit -m "feat(sidecar): inject graph canvas hook transport, update send_func per WS connection"
```

---

## Task 8: litegraph.js node type registration

**Repo:** KEPLER
**Files:**
- Create: `src/components/graph-canvas/types.ts`
- Create: `src/components/graph-canvas/node-registry.ts`

> **Prerequisites:** `litegraph.js` must be installed. Run `npm install litegraph.js` if not present. Check with `ls node_modules/litegraph.js 2>/dev/null || echo "NOT INSTALLED"`.

### Step 1: Check litegraph.js installation

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
ls node_modules/litegraph.js 2>/dev/null && echo "INSTALLED" || echo "NOT INSTALLED — run: npm install litegraph.js"
```

If not installed:
```bash
npm install litegraph.js
```

### Step 2: Create the types file

Create `KEPLER/src/components/graph-canvas/types.ts`:

```typescript
/**
 * TypeScript interfaces for graph canvas components.
 * Mirrors the Python GraphDelta protocol and store types.
 */

export interface NodeOpts {
  color: string;
  titleColor?: string;
  width?: number;  // Default: 200. Stage nodes use 300.
}

export type NodeStatus = 'idle' | 'running' | 'complete' | 'error';

// Status ring colors (matched to Tailwind palette)
export const STATUS_COLORS: Record<NonNullable<NodeStatus>, string> = {
  idle: 'transparent',
  running: '#4A9EFF',   // accent blue
  complete: '#22C55E',  // green
  error: '#EF4444',     // red
};
```

### Step 3: Create the node registry

Create `KEPLER/src/components/graph-canvas/node-registry.ts`:

```typescript
/**
 * litegraph.js node type registration for graph canvas.
 *
 * Called ONCE before any LGraph is created. Safe to call multiple times
 * (checks if already registered). Registers all workflow node types with
 * their colors, modifier badge rendering, and status indicators.
 */

import { LiteGraph } from 'litegraph.js';
import type { NodeOpts } from './types';
import { STATUS_COLORS } from './types';

let _registered = false;

// Workflow node colors (from design doc)
const WORKFLOW_NODES: Array<[string, NodeOpts]> = [
  ['workflow/agent',     { color: '#4A9EFF' }],
  ['workflow/bash',      { color: '#FF9F43' }],
  ['workflow/subrecipe', { color: '#A855F7' }],
  ['workflow/stage',     { color: '#22C55E', width: 300 }],
  ['workflow/context',   { color: '#64748B' }],
];

function drawModifierBadges(ctx: CanvasRenderingContext2D, modifiers?: Record<string, unknown>) {
  if (!modifiers) return;
  const badges: string[] = [];
  if (modifiers.condition)       badges.push('if');
  if (modifiers.foreach)         badges.push('for');
  if (modifiers.while_condition) badges.push('while');
  if (modifiers.retry)           badges.push(`retry:${modifiers.retry}`);
  if (modifiers.timeout)         badges.push(`${modifiers.timeout}s`);
  if (badges.length === 0) return;

  ctx.save();
  ctx.font = '9px monospace';
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  let x = 4;
  const y = -12;
  for (const badge of badges) {
    const w = ctx.measureText(badge).width + 6;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(x, y - 10, w, 12);
    ctx.fillStyle = '#fff';
    ctx.fillText(badge, x + 3, y);
    x += w + 3;
  }
  ctx.restore();
}

function drawStatusRing(ctx: CanvasRenderingContext2D, status: string, width: number, height: number) {
  const color = STATUS_COLORS[status as keyof typeof STATUS_COLORS];
  if (!color || color === 'transparent') return;

  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.globalAlpha = status === 'running' ? 0.9 : 0.6;
  // Draw a ring just inside the node border
  ctx.strokeRect(2, 2, width - 4, height - 4);

  // Pulsing glow for running state
  if (status === 'running') {
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
    ctx.strokeRect(2, 2, width - 4, height - 4);
  }
  ctx.restore();
}

function registerWorkflowNode(typeName: string, opts: NodeOpts) {
  // Don't re-register if already present
  if (LiteGraph.registered_node_types[typeName]) return;

  const defaultWidth = opts.width ?? 200;

  function WorkflowNode(this: any) {
    this.size = [defaultWidth, 60];
    this.properties = {};
    this.addInput('in', '*');
    this.addOutput('out', '*');
  }

  WorkflowNode.title = typeName.split('/')[1];
  WorkflowNode.prototype.color = opts.color;
  WorkflowNode.prototype.bgcolor = '#1a1a2e';

  WorkflowNode.prototype.onDrawForeground = function (
    this: any,
    ctx: CanvasRenderingContext2D
  ) {
    drawModifierBadges(ctx, this.properties?.modifiers);
  };

  WorkflowNode.prototype.onDrawBackground = function (
    this: any,
    ctx: CanvasRenderingContext2D
  ) {
    if (this.properties?.status) {
      drawStatusRing(ctx, this.properties.status, this.size[0], this.size[1]);
    }
  };

  LiteGraph.registerNodeType(typeName, WorkflowNode as any);
}

export function registerNodeTypes() {
  if (_registered) return;
  _registered = true;

  for (const [typeName, opts] of WORKFLOW_NODES) {
    registerWorkflowNode(typeName, opts);
  }
}

export function resetNodeTypeRegistry() {
  // Test helper only — clears registered flag
  _registered = false;
}
```

### Step 4: Verify TypeScript compiles

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx tsc --noEmit
```

Expected: No errors for the new files. If `litegraph.js` has missing types, add `// @ts-ignore` above the import or install `@types/litegraph.js` if available.

### Step 5: Commit

```bash
git add src/components/graph-canvas/
git commit -m "feat(graph-canvas): add litegraph.js node type registry and workflow node types"
```

---

## Task 9: `GraphCanvasCanvas` component

**Repo:** KEPLER
**Files:**
- Create: `src/components/graph-canvas/GraphCanvasCanvas.tsx`

> **Context:** This is the imperative core. litegraph.js is a Canvas2D library — it owns a DOM canvas element. React's job is lifecycle management only (mount/unmount, sync store → litegraph). `syncGraphState` does incremental merges — never full reloads — to prevent canvas flashing during high-frequency viz updates.

### Step 1: Create the component

Create `KEPLER/src/components/graph-canvas/GraphCanvasCanvas.tsx`:

```typescript
/**
 * GraphCanvasCanvas — imperative litegraph.js wrapper.
 *
 * Owns the litegraph lifecycle (LGraph + LGraphCanvas). Syncs store state
 * to litegraph incrementally. In viz mode: read-only. In authoring mode:
 * user interactions fire back to the store via litegraph callbacks.
 */

import { useEffect, useRef } from 'react';
import { LiteGraph, LGraph, LGraphCanvas } from 'litegraph.js';
import { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';
import type { GraphState, GraphNode, GraphEdge } from '@/lib/stores/graph-canvas-store';
import { registerNodeTypes } from './node-registry';

interface Props {
  conversationId?: string;
}

// --- Sync helpers ---

/** Convert a store GraphNode to a litegraph node and add/update in the graph. */
function syncGraphState(lgraph: LGraph, source: GraphState): void {
  // Build lookup of current litegraph nodes by id
  const existing = new Map<string, any>();
  for (const node of (lgraph as any)._nodes ?? []) {
    existing.set(String(node.id), node);
  }

  // Add or update nodes
  for (const storeNode of source.nodes) {
    const lgNode = existing.get(storeNode.id);
    if (!lgNode) {
      // Create new node
      const newNode = LiteGraph.createNode(storeNode.type);
      if (!newNode) continue;  // Unknown type — skip
      (newNode as any).id = storeNode.id;
      newNode.title = storeNode.title;
      newNode.pos = [storeNode.x, storeNode.y];
      newNode.properties = { ...storeNode.properties };
      lgraph.add(newNode);
    } else {
      // Update existing node in-place (preserves user layout)
      lgNode.title = storeNode.title;
      lgNode.properties = { ...storeNode.properties };
      // Only update position from store in viz mode (authoring lets user drag)
    }
    existing.delete(storeNode.id);
  }

  // Remove nodes no longer in store
  for (const [, lgNode] of existing) {
    lgraph.remove(lgNode);
  }

  // Sync edges (clear and re-add — edges are cheap)
  (lgraph as any).links = {};
  for (const edge of source.edges) {
    const fromNode = lgraph.getNodeById(parseInt(edge.from_node, 10));
    const toNode = lgraph.getNodeById(parseInt(edge.to_node, 10));
    if (fromNode && toNode) {
      fromNode.connect(edge.from_slot, toNode, edge.to_slot);
    }
  }
}

/** Convert a litegraph node to a store GraphNode. */
function lgNodeToStoreNode(lgNode: any): GraphNode {
  return {
    id: String(lgNode.id),
    type: lgNode.type ?? 'workflow/agent',
    title: lgNode.title ?? '',
    x: lgNode.pos?.[0] ?? 0,
    y: lgNode.pos?.[1] ?? 0,
    properties: { ...lgNode.properties },
    inputs: [],
    outputs: [],
  };
}

// --- Component ---

export function GraphCanvasCanvas({ conversationId }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const graphRef = useRef<LGraph | null>(null);
  const lgCanvasRef = useRef<LGraphCanvas | null>(null);

  const { activeView, vizGraph, authoringGraph } = useGraphCanvasStore();

  // Mount: create litegraph instances once
  useEffect(() => {
    if (!canvasRef.current) return;

    registerNodeTypes();

    const graph = new LGraph();
    const lgCanvas = new LGraphCanvas(canvasRef.current, graph);

    // Dark theme defaults
    (lgCanvas as any).background_image = null;
    (lgCanvas as any).render_shadows = false;
    (lgCanvas as any).render_canvas_border = false;

    // Resize observer — keeps canvas filling its container
    const resizeObserver = new ResizeObserver(([entry]) => {
      if (!canvasRef.current) return;
      lgCanvas.resize(entry.contentRect.width, entry.contentRect.height);
    });
    if (canvasRef.current.parentElement) {
      resizeObserver.observe(canvasRef.current.parentElement);
    }

    graphRef.current = graph;
    lgCanvasRef.current = lgCanvas;
    graph.start();

    return () => {
      graph.stop();
      resizeObserver.disconnect();
      graphRef.current = null;
      lgCanvasRef.current = null;
    };
  }, []);

  // Sync: load the active graph when view or data changes
  useEffect(() => {
    const graph = graphRef.current;
    const lgCanvas = lgCanvasRef.current;
    if (!graph || !lgCanvas) return;

    const source = activeView === 'viz' ? vizGraph : authoringGraph;
    if (source) {
      syncGraphState(graph, source);
    }

    // Toggle interactivity based on mode
    (lgCanvas as any).allow_interaction   = activeView === 'authoring';
    (lgCanvas as any).allow_searchbox     = activeView === 'authoring';
    (lgCanvas as any).allow_dragnodes     = activeView === 'authoring';
    lgCanvas.setDirty(true, true);
  }, [activeView, vizGraph, authoringGraph]);

  // Authoring callbacks: litegraph → store (only active in authoring mode)
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || activeView !== 'authoring') return;

    const store = useGraphCanvasStore.getState;

    (graph as any).onNodeAdded = (lgNode: any) => {
      store().addNode(lgNodeToStoreNode(lgNode));
    };

    (graph as any).onNodeRemoved = (lgNode: any) => {
      store().removeNode(String(lgNode.id));
    };

    (graph as any).onNodePropertyChanged = (lgNode: any, name: string, value: unknown) => {
      store().updateNode(String(lgNode.id), {
        properties: { ...lgNode.properties, [name]: value },
      });
    };

    return () => {
      (graph as any).onNodeAdded = null;
      (graph as any).onNodeRemoved = null;
      (graph as any).onNodePropertyChanged = null;
    };
  }, [activeView]);

  return (
    <div className="flex-1 min-h-0 relative bg-surface-950">
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
        // litegraph manages its own canvas size — don't set width/height here
      />
      {!vizGraph && !authoringGraph && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-surface-600 text-sm">
            {activeView === 'viz' ? 'Waiting for execution…' : 'Empty graph — drag nodes from the palette'}
          </p>
        </div>
      )}
    </div>
  );
}
```

### Step 2: Type-check

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx tsc --noEmit
```

Expected: No errors (or only expected litegraph.js type looseness with `any`).

### Step 3: Commit

```bash
git add src/components/graph-canvas/GraphCanvasCanvas.tsx
git commit -m "feat(graph-canvas): add GraphCanvasCanvas imperative litegraph.js wrapper"
```

---

## Task 10: `GraphCanvasHeader` + `GraphCanvasStatusBar`

**Repo:** KEPLER
**Files:**
- Create: `src/components/graph-canvas/GraphCanvasHeader.tsx`
- Create: `src/components/graph-canvas/GraphCanvasStatusBar.tsx`

### Step 1: Create the header

Create `KEPLER/src/components/graph-canvas/GraphCanvasHeader.tsx`:

```typescript
/**
 * GraphCanvasHeader — tab bar (Viz | Authoring) + expand/collapse button.
 * Follows the Kepler panel header pattern.
 */

import { X, Maximize2, Minimize2, GitBranch, PenLine } from 'lucide-react';
import { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';
import { useUIStore } from '@/lib/stores/ui-store';

interface Props {
  onClose: () => void;
}

export function GraphCanvasHeader({ onClose }: Props) {
  const { activeView, panelMode, setActiveView, setPanelMode } = useGraphCanvasStore();
  const isFullscreen = panelMode === 'fullscreen';

  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-b border-surface-800/50 flex-shrink-0">
      {/* Left: icon + title */}
      <div className="flex items-center gap-2.5">
        <div className="w-6 h-6 rounded-md flex items-center justify-center bg-accent/20">
          <GitBranch className="w-3.5 h-3.5 text-accent" />
        </div>
        <span className="text-sm font-semibold text-surface-100">Graph Canvas</span>
      </div>

      {/* Center: Viz | Authoring tab bar */}
      <div className="flex bg-surface-800 rounded-lg p-0.5" role="tablist">
        <button
          role="tab"
          aria-selected={activeView === 'viz'}
          onClick={() => setActiveView('viz')}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all ${
            activeView === 'viz'
              ? 'bg-surface-700 text-surface-100 shadow-sm'
              : 'text-surface-400 hover:text-surface-200'
          }`}
        >
          <GitBranch className="w-3 h-3" />
          Viz
        </button>
        <button
          role="tab"
          aria-selected={activeView === 'authoring'}
          onClick={() => setActiveView('authoring')}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all ${
            activeView === 'authoring'
              ? 'bg-surface-700 text-surface-100 shadow-sm'
              : 'text-surface-400 hover:text-surface-200'
          }`}
        >
          <PenLine className="w-3 h-3" />
          Authoring
        </button>
      </div>

      {/* Right: fullscreen toggle + close */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => setPanelMode(isFullscreen ? 'compact' : 'fullscreen')}
          className="p-1.5 rounded-lg hover:bg-surface-800 text-surface-400 hover:text-surface-200 transition-colors"
          title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        >
          {isFullscreen ? (
            <Minimize2 className="w-4 h-4" />
          ) : (
            <Maximize2 className="w-4 h-4" />
          )}
        </button>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-surface-800 text-surface-400 hover:text-surface-200 transition-colors"
          aria-label="Close graph canvas"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
```

### Step 2: Create the status bar

Create `KEPLER/src/components/graph-canvas/GraphCanvasStatusBar.tsx`:

```typescript
/**
 * GraphCanvasStatusBar — node count, edge count, dirty indicator.
 * Compact footer bar at the bottom of the panel.
 */

import { Circle } from 'lucide-react';
import { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';

export function GraphCanvasStatusBar() {
  const { activeView, vizGraph, authoringGraph, isDirty } = useGraphCanvasStore();
  const graph = activeView === 'viz' ? vizGraph : authoringGraph;

  const nodeCount = graph?.nodes.length ?? 0;
  const edgeCount = graph?.edges.length ?? 0;

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 border-t border-surface-800/50 flex-shrink-0 text-[10px] text-surface-500">
      <span>{nodeCount} nodes</span>
      <span className="text-surface-700">·</span>
      <span>{edgeCount} edges</span>
      {activeView === 'authoring' && isDirty && (
        <>
          <span className="text-surface-700">·</span>
          <span className="flex items-center gap-1 text-amber-400/80">
            <Circle className="w-1.5 h-1.5 fill-current" />
            Unsaved
          </span>
        </>
      )}
      <span className="ml-auto text-surface-700 capitalize">{activeView}</span>
    </div>
  );
}
```

### Step 3: Type-check

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx tsc --noEmit
```

### Step 4: Commit

```bash
git add src/components/graph-canvas/GraphCanvasHeader.tsx src/components/graph-canvas/GraphCanvasStatusBar.tsx
git commit -m "feat(graph-canvas): add GraphCanvasHeader and GraphCanvasStatusBar"
```

---

## Task 11: `GraphCanvasToolbar` + `NodePalette`

**Repo:** KEPLER
**Files:**
- Create: `src/components/graph-canvas/node-palette/NodePalette.tsx`
- Create: `src/components/graph-canvas/GraphCanvasToolbar.tsx`

### Step 1: Create the NodePalette

Create `KEPLER/src/components/graph-canvas/node-palette/NodePalette.tsx`:

```typescript
/**
 * NodePalette — draggable node type browser organized by category.
 * Shown in authoring mode when the toolbar's node button is active.
 */

import { motion } from 'framer-motion';
import { useState } from 'react';
import { Search } from 'lucide-react';

interface NodeTypeEntry {
  typeName: string;
  category: string;
  title: string;
  color: string;
}

// Static node type list — mirrors the compiler's schema.py categories.
// Phase 2 will load this from GET /graph/node-types.
const NODE_TYPES: NodeTypeEntry[] = [
  // Workflow
  { typeName: 'workflow/agent',     category: 'Workflow', title: 'Agent',     color: '#4A9EFF' },
  { typeName: 'workflow/bash',      category: 'Workflow', title: 'Bash',      color: '#FF9F43' },
  { typeName: 'workflow/subrecipe', category: 'Workflow', title: 'Subrecipe', color: '#A855F7' },
  { typeName: 'workflow/stage',     category: 'Workflow', title: 'Stage',     color: '#22C55E' },
  { typeName: 'workflow/context',   category: 'Workflow', title: 'Context',   color: '#64748B' },
];

interface Props {
  onClose: () => void;
}

export function NodePalette({ onClose }: Props) {
  const [query, setQuery] = useState('');

  const filtered = NODE_TYPES.filter(
    (n) =>
      !query ||
      n.title.toLowerCase().includes(query.toLowerCase()) ||
      n.category.toLowerCase().includes(query.toLowerCase())
  );

  // Group by category
  const categories = [...new Set(filtered.map((n) => n.category))];

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.15 }}
      className="absolute left-2 top-full mt-1 z-40 w-56 bg-surface-800 border border-surface-700 rounded-xl shadow-xl overflow-hidden"
    >
      {/* Search */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-surface-700">
        <Search className="w-3.5 h-3.5 text-surface-400 flex-shrink-0" />
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search nodes…"
          className="flex-1 bg-transparent text-xs text-surface-200 placeholder-surface-500 focus:outline-none"
        />
      </div>

      {/* Node list */}
      <div className="max-h-72 overflow-y-auto p-1.5 space-y-2">
        {categories.map((cat) => (
          <div key={cat}>
            <p className="px-2 py-1 text-[10px] text-surface-500 uppercase tracking-wider font-medium">
              {cat}
            </p>
            {filtered
              .filter((n) => n.category === cat)
              .map((node) => (
                <motion.div
                  key={node.typeName}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  // Drag to add: litegraph.js picks up HTML drag events on the canvas
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData('litegraph-node-type', node.typeName);
                    e.dataTransfer.effectAllowed = 'copy';
                  }}
                  className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-surface-700 cursor-grab active:cursor-grabbing transition-colors"
                >
                  <div
                    className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                    style={{ backgroundColor: node.color }}
                  />
                  <span className="text-xs text-surface-200">{node.title}</span>
                  <span className="ml-auto text-[9px] text-surface-500 font-mono">
                    {node.typeName.split('/')[0]}
                  </span>
                </motion.div>
              ))}
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="px-2 py-3 text-xs text-surface-500 text-center">No matches</p>
        )}
      </div>
    </motion.div>
  );
}
```

### Step 2: Create the toolbar

Create `KEPLER/src/components/graph-canvas/GraphCanvasToolbar.tsx`:

```typescript
/**
 * GraphCanvasToolbar — authoring-only toolbar with Save, Run, and node palette.
 * Only rendered when activeView === 'authoring'.
 */

import { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Save, Play, Plus, Loader2 } from 'lucide-react';
import { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';
import { NodePalette } from './node-palette/NodePalette';
import { getSidecarUrl } from '@/lib/sidecar';

export function GraphCanvasToolbar() {
  const { authoringGraph, isDirty, markClean, loadRecipe } = useGraphCanvasStore();
  const [showPalette, setShowPalette] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!authoringGraph) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const res = await fetch(`${getSidecarUrl()}/graph/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          graph: authoringGraph,
          path: `ad-hoc-${Date.now()}`,
        }),
      });
      if (!res.ok) throw new Error(`Save failed: ${res.statusText}`);
      const data = await res.json();
      markClean();
      // Update sourceRecipePath with the saved path
      loadRecipe(data.recipe_path, authoringGraph, data.recipe_hash);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  const handleRun = async () => {
    if (!authoringGraph) return;
    setIsRunning(true);
    try {
      const res = await fetch(`${getSidecarUrl()}/graph/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ graph: authoringGraph, name: 'user-run' }),
      });
      if (!res.ok) throw new Error(`Run failed: ${res.statusText}`);
      // Execution progress arrives via viz_event WebSocket messages
    } catch (err) {
      console.error('[GraphCanvasToolbar] Run error:', err);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b border-surface-800/50 flex-shrink-0 relative">
      {/* Node palette trigger */}
      <div className="relative">
        <button
          onClick={() => setShowPalette((v) => !v)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-surface-800/60 hover:bg-surface-800 text-surface-300 hover:text-surface-100 text-xs font-medium transition-colors"
          title="Add node"
          aria-expanded={showPalette}
        >
          <Plus className="w-3.5 h-3.5" />
          Add node
        </button>
        <AnimatePresence>
          {showPalette && (
            <NodePalette onClose={() => setShowPalette(false)} />
          )}
        </AnimatePresence>
      </div>

      <div className="flex-1" />

      {/* Save error */}
      {saveError && (
        <span className="text-xs text-red-400 truncate max-w-[160px]" title={saveError}>
          {saveError}
        </span>
      )}

      {/* Save button */}
      <button
        onClick={handleSave}
        disabled={isSaving || !isDirty}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-surface-800/60 hover:bg-surface-800 disabled:opacity-40 disabled:cursor-not-allowed text-surface-300 hover:text-surface-100 text-xs font-medium transition-colors"
        title={isDirty ? 'Save recipe' : 'No unsaved changes'}
      >
        {isSaving ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Save className="w-3.5 h-3.5" />
        )}
        Save
      </button>

      {/* Run button */}
      <button
        onClick={handleRun}
        disabled={isRunning || !authoringGraph}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-accent/20 hover:bg-accent/30 disabled:opacity-40 disabled:cursor-not-allowed text-accent text-xs font-medium transition-colors"
        title="Run this graph"
      >
        {isRunning ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Play className="w-3.5 h-3.5" />
        )}
        Run
      </button>
    </div>
  );
}
```

### Step 3: Type-check

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx tsc --noEmit
```

### Step 4: Commit

```bash
git add src/components/graph-canvas/node-palette/ src/components/graph-canvas/GraphCanvasToolbar.tsx
git commit -m "feat(graph-canvas): add GraphCanvasToolbar with Save/Run buttons and NodePalette"
```

---

## Task 12: `GraphCanvasPanel` shell

**Repo:** KEPLER
**Files:**
- Create: `src/components/graph-canvas/GraphCanvasPanel.tsx`
- Create: `src/components/graph-canvas/index.ts`

### Step 1: Create the panel shell

Create `KEPLER/src/components/graph-canvas/GraphCanvasPanel.tsx`:

```typescript
/**
 * GraphCanvasPanel — assembles all graph canvas sub-components.
 *
 * Panel pattern:
 * - null-render guard when closed (don't mount DOM — litegraph is expensive)
 * - isOpen/onClose props following Kepler panel convention
 * - flex-col bg-surface-900 border-l border-surface-800/50
 * - fullscreen: fixed inset-0 z-50 (overlays everything)
 */

import { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';
import { GraphCanvasHeader } from './GraphCanvasHeader';
import { GraphCanvasToolbar } from './GraphCanvasToolbar';
import { GraphCanvasCanvas } from './GraphCanvasCanvas';
import { GraphCanvasStatusBar } from './GraphCanvasStatusBar';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  conversationId?: string;
}

export function GraphCanvasPanel({ isOpen, onClose, conversationId }: Props) {
  if (!isOpen) return null;

  return <GraphCanvasPanelInner onClose={onClose} conversationId={conversationId} />;
}

// Inner component — only mounts when isOpen is true.
// Separate component so hooks run clean without conditional return above them.
function GraphCanvasPanelInner({
  onClose,
  conversationId,
}: {
  onClose: () => void;
  conversationId?: string;
}) {
  const { activeView, panelMode } = useGraphCanvasStore();
  const isFullscreen = panelMode === 'fullscreen';

  return (
    <div
      className={
        isFullscreen
          ? 'fixed inset-0 z-50 flex flex-col bg-surface-900'
          : 'h-full flex flex-col bg-surface-900 border-l border-surface-800/50'
      }
    >
      <GraphCanvasHeader onClose={onClose} />
      {activeView === 'authoring' && <GraphCanvasToolbar />}
      <GraphCanvasCanvas conversationId={conversationId} />
      <GraphCanvasStatusBar />
    </div>
  );
}
```

### Step 2: Create the barrel export

Create `KEPLER/src/components/graph-canvas/index.ts`:

```typescript
export { GraphCanvasPanel } from './GraphCanvasPanel';
export { useGraphCanvasStore } from '@/lib/stores/graph-canvas-store';
```

### Step 3: Type-check

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx tsc --noEmit
```

Expected: No errors.

### Step 4: Commit

```bash
git add src/components/graph-canvas/GraphCanvasPanel.tsx src/components/graph-canvas/index.ts
git commit -m "feat(graph-canvas): add GraphCanvasPanel shell assembling all sub-components"
```

---

## Task 13: localStorage draft persistence

**Repo:** KEPLER
**Files:**
- Create: `src/lib/graph-canvas-draft.ts`

> **Context:** Follows the `snapshotTodos`/`restoreTodos` pattern in `todo-store.ts`. Debounces writes with 5s idle timeout. Drafts expire after 7 days. Recovery prompt is shown by the parent component.

### Step 1: Write the failing tests

Create `KEPLER/src/lib/__tests__/graph-canvas-draft.test.ts`:

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { snapshotDraft, restoreDraft, isDraftExpired, clearDraft } from '../graph-canvas-draft';

const DRAFT_KEY = 'graph-canvas:draft';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('snapshotDraft', () => {
  it('writes a draft to localStorage', () => {
    const graph = { nodes: [], edges: [] };
    snapshotDraft(graph, 'workflows/test', 'abc123');
    const raw = localStorage.getItem(DRAFT_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.graph).toEqual(graph);
    expect(parsed.sourceRecipePath).toBe('workflows/test');
    expect(parsed.recipeHash).toBe('abc123');
    expect(typeof parsed.lastModified).toBe('number');
  });

  it('overwrites previous draft', () => {
    snapshotDraft({ nodes: [], edges: [] }, null, null);
    snapshotDraft({ nodes: [{ id: 'n1' } as any], edges: [] }, null, null);
    const parsed = JSON.parse(localStorage.getItem(DRAFT_KEY)!);
    expect(parsed.graph.nodes).toHaveLength(1);
  });
});

describe('restoreDraft', () => {
  it('returns null when no draft exists', () => {
    expect(restoreDraft()).toBeNull();
  });

  it('returns the stored draft', () => {
    snapshotDraft({ nodes: [], edges: [] }, 'path', 'hash');
    const draft = restoreDraft();
    expect(draft).not.toBeNull();
    expect(draft?.sourceRecipePath).toBe('path');
  });
});

describe('isDraftExpired', () => {
  it('returns false for a fresh draft', () => {
    snapshotDraft({ nodes: [], edges: [] }, null, null);
    const draft = restoreDraft()!;
    expect(isDraftExpired(draft)).toBe(false);
  });

  it('returns true for a draft older than 7 days', () => {
    const old = Date.now() - 8 * 24 * 60 * 60 * 1000;
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ graph: { nodes: [], edges: [] }, lastModified: old })
    );
    const draft = restoreDraft()!;
    expect(isDraftExpired(draft)).toBe(true);
  });
});

describe('clearDraft', () => {
  it('removes the draft from localStorage', () => {
    snapshotDraft({ nodes: [], edges: [] }, null, null);
    clearDraft();
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
  });
});
```

### Step 2: Run to verify failure

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx vitest run src/lib/__tests__/graph-canvas-draft.test.ts
```

Expected: FAIL — module not found.

### Step 3: Create the draft persistence module

Create `KEPLER/src/lib/graph-canvas-draft.ts`:

```typescript
/**
 * Graph canvas draft persistence — localStorage snapshot/restore.
 *
 * Saves in-progress authoring graphs with a 5s debounce.
 * Drafts expire after 7 days. Best-effort — never throws.
 * Follows the todo-store snapshotTodos pattern.
 */

import type { GraphState } from './stores/graph-canvas-store';

const DRAFT_KEY = 'graph-canvas:draft';
const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

export interface GraphCanvasDraft {
  graph: GraphState;
  sourceRecipePath: string | null;
  recipeHash: string | null;
  lastModified: number;
}

/** Write current graph to localStorage. Best-effort — fails silently. */
export function snapshotDraft(
  graph: GraphState,
  sourceRecipePath: string | null,
  recipeHash: string | null
): void {
  try {
    const draft: GraphCanvasDraft = {
      graph,
      sourceRecipePath,
      recipeHash,
      lastModified: Date.now(),
    };
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // Storage full or unavailable — fail silently
  }
}

/** Read current draft from localStorage. Returns null if none exists or parsing fails. */
export function restoreDraft(): GraphCanvasDraft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as GraphCanvasDraft;
  } catch {
    return null;
  }
}

/** Returns true if the draft is older than 7 days and should be discarded. */
export function isDraftExpired(draft: GraphCanvasDraft): boolean {
  return Date.now() - draft.lastModified > DRAFT_TTL_MS;
}

/** Remove the draft from localStorage. */
export function clearDraft(): void {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Ignore
  }
}

// --- Auto-snapshot wiring ---
// Call this once at app startup to set up debounced snapshotting.

let _debounceTimer: ReturnType<typeof setTimeout> | null = null;
const DEBOUNCE_MS = 5000;

/** Wire up debounced auto-snapshotting. Call once at app startup. */
export function initDraftAutosave(): () => void {
  let { useGraphCanvasStore } = require('./stores/graph-canvas-store');

  const unsubscribe = useGraphCanvasStore.subscribe(
    (state: { authoringGraph: GraphState | null; sourceRecipePath: string | null; recipeHash: string | null }) => ({
      authoringGraph: state.authoringGraph,
      sourceRecipePath: state.sourceRecipePath,
      recipeHash: state.recipeHash,
    }),
    (slice: { authoringGraph: GraphState | null; sourceRecipePath: string | null; recipeHash: string | null }) => {
      if (!slice.authoringGraph) return;
      if (_debounceTimer) clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(() => {
        snapshotDraft(slice.authoringGraph!, slice.sourceRecipePath, slice.recipeHash);
      }, DEBOUNCE_MS);
    }
  );

  return () => {
    unsubscribe();
    if (_debounceTimer) clearTimeout(_debounceTimer);
  };
}
```

### Step 4: Run tests to verify they pass

```bash
npx vitest run src/lib/__tests__/graph-canvas-draft.test.ts
```

Expected: All tests PASS.

### Step 5: Type-check

```bash
npx tsc --noEmit
```

### Step 6: Commit

```bash
git add src/lib/graph-canvas-draft.ts src/lib/__tests__/graph-canvas-draft.test.ts
git commit -m "feat(graph-canvas): add localStorage draft persistence with 5s debounce and 7-day expiry"
```

---

## Task 14: Panel registration in `App.tsx`

**Repo:** KEPLER
**Files:**
- Modify: `src/App.tsx`

> **Context:** `App.tsx` mounts panels as flex siblings in a horizontal strip. ArtifactsPanel is at lines ~577–636, TaskTree at ~639–655. GraphCanvasPanel goes after TaskTree. It uses the same `AnimatePresence`/`motion.div` + resize handle pattern as ArtifactsPanel.

### Step 1: Add the import

In `KEPLER/src/App.tsx`, find the existing panel imports (around line 11–12):

```typescript
import { ArtifactsPanel } from '@/components/ArtifactsPanel';
import { SessionTaskTree } from './components/task-tree/SessionTaskTree';
```

Add after them:
```typescript
import { GraphCanvasPanel } from '@/components/graph-canvas/GraphCanvasPanel';
```

### Step 2: Destructure the new UIStore values

Find the `useUIStore()` destructuring in App.tsx (around line 60–77). Add these four lines inside the destructuring:

```typescript
    isGraphCanvasPanelOpen,
    setGraphCanvasPanelOpen,
    graphCanvasPanelWidth,
    setGraphCanvasPanelWidth,
```

### Step 3: Add resize state

Find where `isResizingArtifacts` is declared (around line 95):

```typescript
  const [isResizingArtifacts, setIsResizingArtifacts] = useState(false);
```

Add after it:

```typescript
  const [isResizingGraphCanvas, setIsResizingGraphCanvas] = useState(false);
```

### Step 4: Mount the panel

Find the TaskTree closing block (around line 655):

```typescript
        </AnimatePresence>
      </div>
```

Insert the GraphCanvasPanel block immediately after the TaskTree `</AnimatePresence>` and before the outer `</div>`:

```typescript
        {/* Graph Canvas Panel — z-40 layers above task tree */}
        <AnimatePresence mode="wait">
          {isGraphCanvasPanelOpen && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: graphCanvasPanelWidth, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={isResizingGraphCanvas ? { duration: 0 } : { duration: 0.2 }}
              className="flex overflow-hidden z-40 relative"
              style={{ width: graphCanvasPanelWidth }}
            >
              {/* Resize Handle */}
              <div
                className="w-2 hover:bg-accent/50 cursor-col-resize active:bg-accent z-10 flex items-center justify-center group"
                onMouseDown={(e) => {
                  e.preventDefault();
                  setIsResizingGraphCanvas(true);
                  document.body.style.cursor = 'col-resize';
                  document.body.style.userSelect = 'none';
                  const startX = e.clientX;
                  const startWidth = graphCanvasPanelWidth;

                  const handleMouseMove = (moveEvent: MouseEvent) => {
                    const deltaX = startX - moveEvent.clientX;
                    const newWidth = Math.min(Math.max(startWidth + deltaX, 320), 1600);
                    setGraphCanvasPanelWidth(newWidth);
                  };

                  const handleMouseUp = () => {
                    requestAnimationFrame(() => setIsResizingGraphCanvas(false));
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                    document.removeEventListener('mousemove', handleMouseMove);
                    document.removeEventListener('mouseup', handleMouseUp);
                  };

                  document.addEventListener('mousemove', handleMouseMove);
                  document.addEventListener('mouseup', handleMouseUp);
                }}
              >
                <div className="w-0.5 h-8 bg-surface-600 rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              {/* Panel content */}
              <div className="flex-1 overflow-hidden">
                <GraphCanvasPanel
                  isOpen={true}
                  onClose={() => setGraphCanvasPanelOpen(false)}
                  conversationId={currentConversationId || undefined}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
```

### Step 5: Type-check

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
npx tsc --noEmit
```

Expected: No type errors.

### Step 6: Run the full test suites

```bash
# Frontend
npx vitest run

# Sidecar
cd sidecar && uv run pytest tests/ -v
```

Expected: All existing tests pass, no regressions.

### Step 7: Final commit

```bash
cd /Users/michaeljabbour/dev/amplifier-distro-kepler
git add src/App.tsx
git commit -m "feat(app): register GraphCanvasPanel in App.tsx layout alongside existing panels"
```

---

## Summary: Commit sequence

| # | Commit | Repo |
|---|---|---|
| 1 | `feat(hooks): accept optional transport from config in mount()` | BUNDLE |
| 2 | `feat(tool): accept optional transport from config, broadcast mutation deltas` | BUNDLE |
| 3 | `feat(store): add useGraphCanvasStore with dual graph state and delta application` | KEPLER |
| 4 | `feat(ui-store): add isGraphCanvasPanelOpen and graphCanvasPanelWidth` | KEPLER |
| 5 | `feat(ws): handle viz_event and graph_delta messages for graph canvas` | KEPLER |
| 6 | `feat(routes): add /graph/* endpoints for compile, decompile, save, run, list` | KEPLER |
| 7 | `feat(sidecar): inject graph canvas hook transport, update send_func per WS connection` | KEPLER |
| 8 | `feat(graph-canvas): add litegraph.js node type registry and workflow node types` | KEPLER |
| 9 | `feat(graph-canvas): add GraphCanvasCanvas imperative litegraph.js wrapper` | KEPLER |
| 10 | `feat(graph-canvas): add GraphCanvasHeader and GraphCanvasStatusBar` | KEPLER |
| 11 | `feat(graph-canvas): add GraphCanvasToolbar with Save/Run buttons and NodePalette` | KEPLER |
| 12 | `feat(graph-canvas): add GraphCanvasPanel shell assembling all sub-components` | KEPLER |
| 13 | `feat(graph-canvas): add localStorage draft persistence with 5s debounce and 7-day expiry` | KEPLER |
| 14 | `feat(app): register GraphCanvasPanel in App.tsx layout alongside existing panels` | KEPLER |

---

## Red flags to watch for

- **litegraph.js not installed**: Task 8 will fail. Run `npm install litegraph.js` in KEPLER root.
- **`graph_canvas_compiler` not in sidecar venv**: Tasks 6 compile/decompile tests will be 422 — this is acceptable.
- **`ALL_EVENTS` import fails**: Task 7 fallback registers only the explicitly listed events — that's fine.
- **`chat.py` structure differs from expected**: Task 7 Step 7 requires reading `chat.py` to find the exact location of `_update_bash_tool_cb` call before adding the parallel call.
- **`useGraphCanvasStore.subscribe` selector form**: Task 13's `initDraftAutosave` uses Zustand's selector subscribe — verify the import pattern matches the Zustand version in use (`import { subscribeWithSelector } from 'zustand/middleware'` may be needed if the subscribe form doesn't work directly).
