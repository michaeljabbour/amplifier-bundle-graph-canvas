"""Integration tests verifying the graph-canvas bundle works as a cohesive unit."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

# Repo root (two levels up from this test file)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_yaml = YAML()


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from a markdown file (between --- markers)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("No frontmatter found")
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("Frontmatter not closed")
    return _yaml.load(StringIO("\n".join(lines[1:end])))


# =============================================================================
# 1. TestBundleConfigParsing
# =============================================================================


class TestBundleConfigParsing:
    def test_bundle_md_has_valid_frontmatter(self):
        text = (REPO_ROOT / "bundle.md").read_text()
        fm = _parse_frontmatter(text)

        assert fm["bundle"]["name"] == "graph-canvas"
        assert fm["bundle"]["version"] == "0.1.0"
        assert len(fm["includes"]) == 2

    def test_behavior_yaml_is_valid(self):
        text = (REPO_ROOT / "behaviors" / "graph-canvas.yaml").read_text()
        data = _yaml.load(StringIO(text))

        assert "tools" in data
        assert "hooks" in data
        assert "agents" in data
        assert "context" in data

    def test_behavior_references_correct_modules(self):
        text = (REPO_ROOT / "behaviors" / "graph-canvas.yaml").read_text()
        data = _yaml.load(StringIO(text))

        tool_modules = [t["module"] for t in data["tools"]]
        hook_modules = [h["module"] for h in data["hooks"]]

        assert "tool-graph-canvas" in tool_modules
        assert "hooks-graph-canvas" in hook_modules


# =============================================================================
# 2. TestContentFileValidation
# =============================================================================


class TestContentFileValidation:
    def test_awareness_context_exists_and_is_nonempty(self):
        path = REPO_ROOT / "context" / "graph-canvas-awareness.md"
        assert path.exists()
        content = path.read_text()
        assert len(content.strip()) > 0

    def test_agent_has_meta_frontmatter(self):
        text = (REPO_ROOT / "agents" / "graph-canvas-expert.md").read_text()
        fm = _parse_frontmatter(text)

        assert fm["meta"]["name"] == "graph-canvas-expert"
        assert len(fm["meta"]["description"].strip()) > 0

    def test_skill_has_frontmatter(self):
        text = (REPO_ROOT / "skills" / "graph-authoring" / "skill.md").read_text()
        fm = _parse_frontmatter(text)

        assert fm["name"] == "graph-authoring"

    def test_docs_exist(self):
        proto = REPO_ROOT / "docs" / "GRAPH_PROTOCOL.md"
        kepler = REPO_ROOT / "docs" / "kepler-integration.md"

        assert proto.exists()
        assert len(proto.read_text().strip()) > 0

        assert kepler.exists()
        assert len(kepler.read_text().strip()) > 0


# =============================================================================
# 3. TestToolModuleImport
# =============================================================================


class TestToolModuleImport:
    def test_mount_returns_tool_instance(self, tool):
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "parameters")
        assert hasattr(tool, "execute")

    def test_tool_name_is_graph_canvas(self, tool):
        assert tool.name == "graph_canvas"


# =============================================================================
# 4. TestHookModuleImport
# =============================================================================


class TestHookModuleImport:
    def test_mount_returns_hook_instance(self, hook):
        assert callable(hook)
        assert hasattr(hook, "__call__")


# =============================================================================
# 5. TestEndToEnd
# =============================================================================


class TestEndToEnd:
    async def test_full_workflow_add_connect_compile(self, tool):
        # 1. add_node: Analyze
        r1 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "title": "Analyze",
            }
        )
        assert "result" in r1
        node1_id = r1["result"]["node_id"]

        # 2. add_node: Synthesize
        r2 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "title": "Synthesize",
            }
        )
        assert "result" in r2
        node2_id = r2["result"]["node_id"]

        # 3. connect_nodes
        r3 = await tool.execute(
            arguments={
                "action": "connect_nodes",
                "from_id": node1_id,
                "to_id": node2_id,
            }
        )
        assert "result" in r3
        assert "edge_id" in r3["result"]

        # 4. compile_recipe
        r4 = await tool.execute(arguments={"action": "compile_recipe", "name": "test"})
        assert "result" in r4
        yaml_str = r4["result"]["yaml"]

        recipe = _yaml.load(StringIO(yaml_str))
        assert len(recipe["steps"]) == 2

        # 5. load_recipe
        r5 = await tool.execute(arguments={"action": "load_recipe", "yaml": yaml_str})
        assert "result" in r5
        assert r5["result"]["loaded"] is True
        assert r5["result"]["node_count"] == 2

    async def test_hook_processes_events(self, hook):
        # tool:pre event
        pre_result = await hook(
            "tool:pre",
            {
                "tool_use_id": "tu_001",
                "request_id": "req_001",
                "tool_name": "read_file",
            },
        )
        assert pre_result == {"action": "continue"}

        # tool:post event
        post_result = await hook(
            "tool:post",
            {
                "tool_use_id": "tu_001",
                "request_id": "req_001",
                "result": "file contents here",
            },
        )
        assert post_result == {"action": "continue"}

    async def test_compiler_round_trip(self, tool):
        # Build a graph via tool
        r1 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/agent",
                "title": "StepA",
            }
        )
        node1_id = r1["result"]["node_id"]

        r2 = await tool.execute(
            arguments={
                "action": "add_node",
                "type": "workflow/bash",
                "title": "StepB",
            }
        )
        node2_id = r2["result"]["node_id"]

        await tool.execute(
            arguments={
                "action": "connect_nodes",
                "from_id": node1_id,
                "to_id": node2_id,
            }
        )

        # Compile to recipe YAML
        r_compile = await tool.execute(
            arguments={"action": "compile_recipe", "name": "roundtrip"}
        )
        yaml_str = r_compile["result"]["yaml"]

        # Decompile back to graph
        from graph_canvas_compiler import decompile_recipe

        graph_dict = decompile_recipe(yaml_str)

        # Verify structural equivalence
        assert len(graph_dict["nodes"]) == 2
        node_types = {n["type"] for n in graph_dict["nodes"]}
        assert "workflow/agent" in node_types
        assert "workflow/bash" in node_types
