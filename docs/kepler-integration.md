# Kepler Integration Guide

This guide explains how to wire the graph-canvas bundle into the Kepler desktop app (amplifier-distro-kepler).

## Bundle Inclusion

Add one line to Kepler's `sidecar/bundles/desktop.yaml`:

```yaml
includes:
  - bundle: git+https://github.com/michaeljabbour/amplifier-bundle-graph-canvas@main
```

This gives Kepler sessions:
- The `graph_canvas` tool (LLM can manipulate graphs)
- The `hooks-graph-canvas` hook (kernel events emitted as visualization deltas)
- The `graph-canvas-expert` agent (context sink for graph-related delegation)
- Awareness context (LLM knows the tool exists)

## Frontend Integration

### React Component: GraphCanvasPanel

Create a new React component that wraps litegraph.js:
- **Compact mode**: Docked panel showing live visualization (read-only)
- **Fullscreen mode**: Full editor with Save/Run controls

### Zustand Store: useGraphCanvasStore

```typescript
interface GraphCanvasStore {
  vizGraph: GraphState | null;       // From hook events
  authoringGraph: GraphState | null; // From user editing
  activeView: 'viz' | 'authoring';
  panelMode: 'compact' | 'fullscreen';
}
```

### WebSocket Messages

Piggyback on the existing chat WebSocket (`ws://127.0.0.1:19876/chat`):

| Message Type | Direction | Purpose |
|---|---|---|
| `viz_event` | Hook -> Frontend | Visualization deltas |
| `graph_delta` | Tool -> Frontend | AI tool mutations |
| `graph_sync` | Frontend -> Sidecar | Authoring save/load |

### FastAPI Routes

Add `sidecar/apps/desktop/routes/graph.py`:

| Route | Method | Purpose |
|---|---|---|
| `/graph/recipes` | GET | List saved recipe files |
| `/graph/compile` | POST | Graph JSON -> recipe YAML |
| `/graph/decompile` | POST | Recipe YAML -> graph JSON |
| `/graph/save` | POST | Persist graph + sidecar layout |
| `/graph/run` | POST | Compile in-memory + execute |

### litegraph.js Dependency

Add to Kepler's `package.json`:
```json
{
  "dependencies": {
    "litegraph.js": "file:../litegraph.js"
  }
}
```

Or publish to npm and reference the version.

## Canonical Artifact Split

```
workflow.yaml              <- Recipe (canonical, works without UI)
workflow.litegraph.json    <- Layout metadata (optional, UI-only)
```
