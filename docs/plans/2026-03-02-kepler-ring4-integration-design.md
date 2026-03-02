# Kepler Ring 4 Integration Design

## Goal

Design the Kepler desktop app integration (Ring 4) for the graph-canvas bundle — React `GraphCanvasPanel` component, FastAPI routes, WebSocket wiring, and litegraph.js embedding. Full scope: visualization (hook-driven), AI tool feedback (tool mutations on canvas), and visual authoring (user drags nodes, saves as recipes).

## Context

**Bundle repo**: `amplifier-bundle-graph-canvas` at github.com/michaeljabbour/amplifier-bundle-graph-canvas
**Kepler repo**: `amplifier-distro-kepler` — Tauri 2.0 app with React frontend and Python FastAPI sidecar

### Current State
- All three Python modules (tool-graph-canvas, hooks-graph-canvas, graph-canvas-compiler) are fully implemented and tested
- 19 node types registered, 11 tool actions working, 10 kernel events mapped
- `WebSocketTransport` class exists in the hook module but needs `send_func` injected
- Zero Ring 4 code exists — no React components, no FastAPI routes, no WebSocket wiring

### Key Decisions Made
- **Ring 4 code lives in the Kepler repo** (`amplifier-distro-kepler`), not the bundle repo. Clean ring boundary.
- **Full scope**: Visualization + AI tool feedback + Authoring (all three use cases)
- **Approach A (thin integration)**: Single component tree, single Zustand store, sub-components extracted as complexity demands. No preemptive layering.
- **Persistence**: Hybrid (Option C) — filesystem for saved recipes (YAML + `.litegraph.json` sidecar), localStorage for in-progress drafts. No SQLite. Follows the existing todo-store pattern.
- **Hook transport**: Config-driven injection at `mount()` time — pass pre-constructed `WebSocketTransport` instance via config dict. One-line change to `mount()`.

## Architecture Overview

```
Kepler Ring 4 (amplifier-distro-kepler)
├── src/components/graph-canvas/     # React components
│   ├── GraphCanvasPanel.tsx         # Shell: mode switching, panel chrome
│   ├── GraphCanvasHeader.tsx        # Tab bar (Viz | Authoring), expand/collapse
│   ├── GraphCanvasToolbar.tsx       # Authoring-only: node palette, Save, Run
│   ├── GraphCanvasCanvas.tsx        # litegraph.js imperative wrapper
│   ├── GraphCanvasStatusBar.tsx     # Node count, dirty indicator
│   ├── node-palette/
│   │   └── NodePalette.tsx          # Draggable node type browser
│   └── types.ts                     # TypeScript interfaces
├── src/lib/stores/
│   └── graph-canvas-store.ts        # useGraphCanvasStore (Zustand)
└── sidecar/apps/desktop/routes/
    └── graph_canvas.py              # FastAPI route module

Bundle Repo (amplifier-bundle-graph-canvas) — changes needed:
└── modules/hooks-graph-canvas/
    └── hooks_graph_canvas/__init__.py   # mount() reads transport from config
```

## Section 1: Component Architecture

The React side lives in the Kepler repo under `src/components/graph-canvas/`:

```
src/components/graph-canvas/
├── GraphCanvasPanel.tsx        # Shell: mode switching, panel chrome, isOpen guard
├── GraphCanvasHeader.tsx       # Tab bar (Viz | Authoring), expand/collapse button
├── GraphCanvasToolbar.tsx      # Authoring-only: node palette, Save, Run, search
├── GraphCanvasCanvas.tsx       # The litegraph.js wrapper (imperative core)
├── GraphCanvasStatusBar.tsx    # Node count, connection status, dirty indicator
├── node-palette/
│   └── NodePalette.tsx         # Draggable node type browser (categories from schema)
└── types.ts                    # TypeScript interfaces for graph state
```

**GraphCanvasPanel** (the shell) follows the existing Kepler panel pattern:

```typescript
interface GraphCanvasPanelProps {
  isOpen: boolean;
  onClose: () => void;
  conversationId?: string;
}

export function GraphCanvasPanel({ isOpen, onClose, conversationId }: GraphCanvasPanelProps) {
  if (!isOpen) return null;

  const { activeView, panelMode } = useGraphCanvasStore();
  const isFullscreen = panelMode === 'fullscreen';

  return (
    <div className={isFullscreen ? 'fixed inset-0 z-50 bg-surface-900' : 'h-full flex flex-col bg-surface-900 border-l border-surface-800/50'}>
      <GraphCanvasHeader onClose={onClose} />
      {activeView === 'authoring' && <GraphCanvasToolbar />}
      <GraphCanvasCanvas conversationId={conversationId} />
      <GraphCanvasStatusBar />
    </div>
  );
}
```

**Key conventions** (matching existing Kepler panels):
- `isOpen` guard with null-render when closed (don't mount DOM)
- `framer-motion` for list item animations
- Lucide icons throughout
- Tailwind `surface-*` color tokens (`surface-900`, `surface-800`, `surface-700`)
- `accent` color token for interactive highlights
- Hover-reveal buttons: `opacity-0 group-hover:opacity-100`

**GraphCanvasCanvas** is the imperative core — owns the litegraph.js lifecycle:
- `useRef<HTMLCanvasElement>` for the DOM canvas
- `useRef<LGraph>` for the graph model instance
- `useRef<LGraphCanvas>` for the canvas controller
- `useEffect` on mount: creates `LGraph` + `LGraphCanvas`, registers node types, wires callbacks
- `useEffect` on unmount: stops graph, removes canvas
- `useEffect` watching `activeView`: loads `vizGraph` or `authoringGraph` from store into the `LGraph` instance
- In viz mode: litegraph is read-only (`allow_interaction: false`, `allow_searchbox: false`)
- In authoring mode: full interactivity, litegraph callbacks fire → store updates

**Mode transitions:**

| From | To | What happens |
|---|---|---|
| Compact + Viz | Fullscreen + Viz | Panel expands, same read-only graph, more detail visible |
| Compact + Viz | Fullscreen + Authoring | Panel expands, switches to authoring graph, toolbar appears |
| Fullscreen + Authoring | Compact + Viz | Toolbar hides, switches to viz graph, panel contracts |
| Any | Close | Panel unmounts, litegraph instances destroyed, store state preserved |

**Fullscreen implementation**: CSS class on the panel container that Kepler's layout respects. `useUIStore` already manages panel widths — fullscreen sets the panel to consume the full viewport, collapsing the chat area.

## Section 2: State Management & Persistence

### Zustand Store: useGraphCanvasStore

Located at `src/lib/stores/graph-canvas-store.ts`:

```typescript
interface GraphNode {
  id: string;
  type: string;           // e.g. "workflow/agent", "workflow/bash"
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

interface GraphEdge {
  id: string;
  from_node: string;
  from_slot: number;
  to_node: string;
  to_slot: number;
  type: 'data' | 'dependency';  // solid vs dashed
}

interface GraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface GraphDelta {
  action: 'add_node' | 'remove_node' | 'add_edge' | 'remove_edge'
        | 'update_node' | 'clear' | 'set_status';
  data: Record<string, unknown>;
}

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
```

**Delta application**: Both `applyVizDelta` and `applyAuthoringDelta` handle the same `GraphDelta` format (matching the Python `protocol.py` `Delta` dataclass). Merges incrementally — never replaces the full graph. Keeps the litegraph canvas stable.

**UIStore additions** (in existing `src/lib/stores/ui-store.ts`):
```typescript
isGraphCanvasPanelOpen: boolean;
setGraphCanvasPanelOpen: (open: boolean) => void;
graphCanvasPanelWidth: number;
setGraphCanvasPanelWidth: (width: number | ((prev: number) => number)) => void;
```

### WebSocket Message Handling

Two new cases in the existing message handler switch statement:
```typescript
case 'viz_event':
  useGraphCanvasStore.getState().applyVizDelta(msg.data);
  break;
case 'graph_delta':
  useGraphCanvasStore.getState().applyAuthoringDelta(msg.data);
  break;
```

No new WebSocket connection. No new message handler. Two `case` branches.

### localStorage Draft Persistence

Following the todo-store pattern:

```typescript
const DRAFT_KEY = 'graph-canvas:draft';

// Debounced snapshot on authoring changes (5s idle)
useGraphCanvasStore.subscribe(
  (state) => state.authoringGraph,
  debounce((authoringGraph) => {
    if (!authoringGraph) return;
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      graph: authoringGraph,
      sourceRecipePath: useGraphCanvasStore.getState().sourceRecipePath,
      recipeHash: useGraphCanvasStore.getState().recipeHash,
      lastModified: Date.now(),
    }));
  }, 5000)
);
```

On app startup, check for drafts and surface "Restore unsaved changes?" prompt. Stale drafts expire after 7 days. Best-effort — bundle works perfectly without drafts. No migration, no versioning of draft format.

## Section 3: Sidecar Integration

### FastAPI Routes: graph_canvas.py

Located at `sidecar/apps/desktop/routes/graph_canvas.py`. Follows the `create_*_router(desktop)` factory:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

class CompileRequest(BaseModel):
    graph: dict

class DecompileRequest(BaseModel):
    recipe_yaml: str
    layout_data: dict | None = None

class SaveRequest(BaseModel):
    graph: dict
    path: str

class RunRequest(BaseModel):
    graph: dict
    name: str | None = None

def create_graph_canvas_router(desktop) -> APIRouter:
    router = APIRouter(prefix="/graph", tags=["graph"])

    @router.get("/recipes")
    async def list_recipes():
        """List saved recipe files in the workspace."""
        ...

    @router.post("/compile")
    async def compile_graph(request: CompileRequest):
        """Graph JSON -> recipe YAML string."""
        from graph_canvas_compiler import compile_graph
        try:
            yaml_str = compile_graph(request.graph)
            return {"yaml": yaml_str}
        except CompileError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @router.post("/decompile")
    async def decompile_recipe(request: DecompileRequest):
        """Recipe YAML -> graph JSON."""
        from graph_canvas_compiler import decompile_recipe
        try:
            graph = decompile_recipe(request.recipe_yaml, request.layout_data)
            return {"graph": graph}
        except CompileError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @router.post("/save")
    async def save_graph(request: SaveRequest):
        """Compile graph and persist recipe YAML + layout sidecar."""
        from graph_canvas_compiler import compile_graph
        yaml_str = compile_graph(request.graph)
        recipe_path = f"{request.path}.yaml"
        layout_path = f"{request.path}.litegraph.json"
        # Write recipe YAML + layout sidecar (positions + recipe_hash)
        return {"recipe_path": recipe_path, "layout_path": layout_path}

    @router.post("/run")
    async def run_graph(request: RunRequest):
        """Compile in-memory and execute via recipes tool."""
        from graph_canvas_compiler import compile_graph
        yaml_str = compile_graph(request.graph)
        # Invoke existing recipes tool to execute
        # Hook viz deltas stream execution back to frontend
        return {"status": "started", "recipe_name": request.name}

    return router
```

**Registration** in `sidecar/apps/desktop/__init__.py` `create_router()`:
```python
from .routes.graph_canvas import create_graph_canvas_router
router.include_router(create_graph_canvas_router(desktop))
```

### Hook Transport Wiring

**Bundle-side change** (`hooks_graph_canvas/__init__.py`):
```python
def mount(config: dict | None = None):
    from .hook import GraphCanvasHook, JsonlTransport
    config = config or {}
    transport = config.get("transport") or JsonlTransport()
    return GraphCanvasHook(config=config, transport=transport)
```

**Kepler-side wiring** (in session setup):
```python
from hooks_graph_canvas.hook import WebSocketTransport

ws_transport = WebSocketTransport(
    send_func=lambda delta: ws_send({
        "type": "viz_event",
        "data": delta,
        "conversationId": conversation_id
    })
)

hook_config = {
    "skip_subsessions": True,
    "throttle_ms": 100,
    "transport": ws_transport,
}
```

**Tool broadcast** follows the same pattern — tool module's `mount()` also accepts optional `transport` in config. Kepler wraps tool deltas with `"type": "graph_delta"` to distinguish from hook-driven `"viz_event"`.

### WebSocket Message Flow

```
Hook event (kernel)  --> hook.emit(delta) --> ws_send(viz_event)     --> frontend applyVizDelta
Tool mutation (LLM)  --> tool.broadcast()  --> ws_send(graph_delta)  --> frontend applyAuthoringDelta
Authoring save (user) --> POST /graph/save --> compile + write files --> response to frontend
Authoring run (user)  --> POST /graph/run  --> compile + execute     --> hook viz deltas show execution
```

## Section 4: litegraph.js Embedding

### Node Type Registration

On `GraphCanvasCanvas` mount, register all node types before creating any graph:

```typescript
import { LiteGraph, LGraph, LGraphCanvas } from 'litegraph.js';

function registerNodeTypes() {
  registerWorkflowNode('workflow/agent',     { color: '#4A9EFF' });
  registerWorkflowNode('workflow/bash',      { color: '#FF9F43' });
  registerWorkflowNode('workflow/subrecipe', { color: '#A855F7' });
  registerWorkflowNode('workflow/stage',     { color: '#22C55E', width: 300 }); // 1.5x
  registerWorkflowNode('workflow/context',   { color: '#64748B' });
  // Math, logic, string, events, basic nodes registered from schema categories
}

function registerWorkflowNode(typeName: string, opts: NodeOpts) {
  function WorkflowNode() { /* slots from schema */ }
  WorkflowNode.title = typeName.split('/')[1];
  WorkflowNode.prototype.color = opts.color;

  // Modifier badges (condition, foreach, while, retry)
  WorkflowNode.prototype.onDrawForeground = function(ctx: CanvasRenderingContext2D) {
    drawModifierBadges(ctx, this.properties.modifiers);
  };

  // Status indicator for viz mode (running/complete/error ring)
  WorkflowNode.prototype.onDrawBackground = function(ctx: CanvasRenderingContext2D) {
    if (this.properties.status) {
      drawStatusRing(ctx, this.properties.status);
    }
  };

  LiteGraph.registerNodeType(typeName, WorkflowNode);
}
```

Schema (inputs, outputs, defaults, categories) shipped as a static JSON file from the compiler's `schema.py`. No round-trip endpoint needed.

### Canvas2D Lifecycle in React

`GraphCanvasCanvas.tsx`:

```typescript
export function GraphCanvasCanvas({ conversationId }: { conversationId?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const graphRef = useRef<LGraph | null>(null);
  const lgCanvasRef = useRef<LGraphCanvas | null>(null);
  const { activeView, vizGraph, authoringGraph } = useGraphCanvasStore();

  // Mount: create litegraph instances
  useEffect(() => {
    if (!canvasRef.current) return;
    registerNodeTypes();
    const graph = new LGraph();
    const lgCanvas = new LGraphCanvas(canvasRef.current, graph);
    const resizeObserver = new ResizeObserver(([entry]) => {
      lgCanvas.resize(entry.contentRect.width, entry.contentRect.height);
    });
    resizeObserver.observe(canvasRef.current.parentElement!);
    graphRef.current = graph;
    lgCanvasRef.current = lgCanvas;
    graph.start();
    return () => { graph.stop(); resizeObserver.disconnect(); };
  }, []);

  // Sync: load active graph when view or data changes
  useEffect(() => {
    const graph = graphRef.current;
    const lgCanvas = lgCanvasRef.current;
    if (!graph || !lgCanvas) return;
    const source = activeView === 'viz' ? vizGraph : authoringGraph;
    if (source) syncGraphState(graph, source);  // Incremental merge, not full reload
    lgCanvas.allow_interaction = activeView === 'authoring';
    lgCanvas.allow_searchbox = activeView === 'authoring';
    lgCanvas.allow_dragnodes = activeView === 'authoring';
  }, [activeView, vizGraph, authoringGraph]);

  // Authoring callbacks: litegraph -> store
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || activeView !== 'authoring') return;
    graph.onNodeAdded = (node) => useGraphCanvasStore.getState().addNode(lgNodeToStoreNode(node));
    graph.onNodeRemoved = (node) => useGraphCanvasStore.getState().removeNode(node.id.toString());
    graph.onConnectionChange = () => { /* re-sync edges */ };
    graph.onNodePropertyChanged = (node, name, value) => {
      useGraphCanvasStore.getState().updateNode(node.id.toString(), {
        properties: { ...node.properties, [name]: value }
      });
    };
    return () => { graph.onNodeAdded = null; graph.onNodeRemoved = null; graph.onConnectionChange = null; };
  }, [activeView]);

  return (
    <div className="flex-1 min-h-0 relative">
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
    </div>
  );
}
```

**Critical: `syncGraphState` does incremental merge**, not full reload. On each delta: compare incoming nodes/edges against litegraph's current state, add/remove/update only what changed, preserve user's viewport position and zoom. Prevents canvas flashing during high-frequency viz updates.

### Subgraph Progressive Disclosure

litegraph.js has native `Subgraph` support:
- **High-level nodes** (LLM turn, tool call) always visible at top level
- **Sub-agent spawns** create a `Subgraph` node — collapsed by default, summary label
- **Drill-down details** nest inside subgraph — rendered when user double-clicks to expand
- Hook tags deltas with `detail_level: "high"` or `detail_level: "drill"`. High-level deltas update the top graph. Drill-down deltas target a specific subgraph by `parent_node_id`

```typescript
function applyDelta(graph: LGraph, delta: GraphDelta) {
  if (delta.data.detail_level === 'drill' && delta.data.parent_node_id) {
    const parentNode = graph.getNodeById(delta.data.parent_node_id);
    if (parentNode?.subgraph) {
      applyDeltaToGraph(parentNode.subgraph, delta);
    }
    return;
  }
  applyDeltaToGraph(graph, delta);
}
```

### Edge Rendering

Two visual styles:
- **Data-flow edges** (solid lines, default color) — represent `{{variable}}` references
- **Dependency edges** (dashed lines, muted color) — represent `depends_on` relationships

Override `LGraphCanvas.prototype.drawConnection` to check `edge.type` and switch stroke style.

## Bundle-Side Changes Required

The bundle repo needs one change before Kepler integration works:

1. **`hooks_graph_canvas/__init__.py`**: Change `mount()` to read optional `transport` from config instead of hardcoding `JsonlTransport`. One line of logic. Backward-compatible — no transport in config defaults to `JsonlTransport`.

2. **`tool_graph_canvas/__init__.py`**: Same pattern — read optional `transport` from config for broadcast. Currently the `broadcast_transport: websocket` config key in the behavior YAML is declared but never read.

## Open Questions Resolved

| Question | Decision | Rationale |
|---|---|---|
| Where does Ring 4 code live? | Kepler repo | Clean ring boundary |
| Phase 1 scope? | Full: viz + tool + authoring | All three use cases |
| Authoring persistence? | Hybrid: filesystem + localStorage | Follows todo-store pattern, no SQLite |
| Hook transport injection? | Config-driven at mount() | Clean boundary, no temporal coupling |
| Integration approach? | Thin (Approach A) — fully featured | Ruthless simplicity, extract sub-components when needed |

## Remaining Open Questions (from parent design doc)

1. **TypeScript compiler package** — Should `graph-canvas-compiler` also ship as npm? Deferred to Phase 2. Client-side compile/decompile is nice-to-have, not blocking.
2. **litegraph.js dependency source** — Local fork (`file:../litegraph.js`) vs npm. Decision needed at implementation time based on fork readiness.
3. **SessionTaskTree relationship** — Visualization hook could eventually replace the task tree. Keep both for now, evaluate after dogfooding.
