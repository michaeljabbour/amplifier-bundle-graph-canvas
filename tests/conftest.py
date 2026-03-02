import pytest
from tool_graph_canvas import mount as mount_tool
from hooks_graph_canvas import mount as mount_hook


@pytest.fixture
def tool():
    return mount_tool()


@pytest.fixture
def hook():
    return mount_hook()
