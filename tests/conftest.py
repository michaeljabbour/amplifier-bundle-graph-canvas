import pytest
from amplifier_module_tool_graph_canvas.tool import GraphCanvasTool
from amplifier_module_hooks_graph_canvas.hook import GraphCanvasHook


@pytest.fixture
def tool():
    return GraphCanvasTool(config={})


@pytest.fixture
def hook():
    return GraphCanvasHook(config={})
