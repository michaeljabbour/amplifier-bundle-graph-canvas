"""Tests for event_mapper module."""

from hooks_graph_canvas.event_mapper import map_event


class TestProviderRequest:
    def test_provider_request_returns_add_node_delta(self):
        data = {
            "request_id": "req-123",
            "model": "claude-3.5-sonnet",
            "timestamp": "2026-03-01T12:00:00Z",
        }
        delta = map_event("provider:request", data)

        assert delta is not None
        assert delta["action"] == "add_node"
        assert delta["node_id"] == "req-123"
        assert delta["data"]["type"] == "llm_turn"
        assert delta["data"]["status"] == "thinking"
        assert delta["data"]["model"] == "claude-3.5-sonnet"
        assert delta["detail_level"] == "high"
        assert delta["event"] == "provider:request"
        assert delta["timestamp"] == "2026-03-01T12:00:00Z"


class TestProviderResponse:
    def test_provider_response_returns_update_node_delta(self):
        data = {
            "request_id": "req-123",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "timestamp": "2026-03-01T12:00:01Z",
        }
        delta = map_event("provider:response", data)

        assert delta is not None
        assert delta["action"] == "update_node"
        assert delta["node_id"] == "req-123"
        assert delta["data"]["status"] == "complete"
        assert delta["data"]["usage"] == {"input_tokens": 100, "output_tokens": 50}
        assert delta["detail_level"] == "high"


class TestContentBlockDelta:
    def test_content_block_delta_returns_drill_down_detail_level(self):
        data = {
            "request_id": "req-123",
            "delta": {"text": "Hello"},
            "timestamp": "2026-03-01T12:00:00.500Z",
        }
        delta = map_event("content_block:delta", data)

        assert delta is not None
        assert delta["action"] == "update_node"
        assert delta["node_id"] == "req-123"
        assert delta["detail_level"] == "drill_down"


class TestToolPre:
    def test_tool_pre_returns_add_node_delta(self):
        data = {
            "request_id": "req-123",
            "tool_use_id": "tool-456",
            "tool_name": "read_file",
            "timestamp": "2026-03-01T12:00:02Z",
        }
        delta = map_event("tool:pre", data)

        assert delta is not None
        assert delta["action"] == "add_node"
        assert delta["node_id"] == "tool-456"
        assert delta["data"]["type"] == "read_file"
        assert delta["data"]["status"] == "executing"
        assert delta["detail_level"] == "high"
        # Should also include edge info for connecting to LLM node
        assert delta["edge"] is not None
        assert delta["edge"]["from_node"] == "req-123"
        assert delta["edge"]["to_node"] == "tool-456"


class TestToolPost:
    def test_tool_post_returns_update_node_delta(self):
        data = {
            "tool_use_id": "tool-456",
            "result": "file contents here...",
            "timestamp": "2026-03-01T12:00:03Z",
        }
        delta = map_event("tool:post", data)

        assert delta is not None
        assert delta["action"] == "update_node"
        assert delta["node_id"] == "tool-456"
        assert delta["data"]["status"] == "complete"
        assert delta["data"]["result_preview"] is not None
        assert delta["detail_level"] == "high"


class TestToolError:
    def test_tool_error_returns_update_node_with_error_status(self):
        data = {
            "tool_use_id": "tool-456",
            "error": "Permission denied",
            "timestamp": "2026-03-01T12:00:03Z",
        }
        delta = map_event("tool:error", data)

        assert delta is not None
        assert delta["action"] == "update_node"
        assert delta["node_id"] == "tool-456"
        assert delta["data"]["status"] == "error"
        assert delta["data"]["error"] == "Permission denied"
        assert delta["detail_level"] == "high"


class TestSessionSpawn:
    def test_session_spawn_returns_add_node_with_collapsed_subgraph(self):
        data = {
            "session_id": "sess-789",
            "timestamp": "2026-03-01T12:00:04Z",
        }
        delta = map_event("session:spawn", data)

        assert delta is not None
        assert delta["action"] == "add_node"
        assert delta["node_id"] == "sess-789"
        assert delta["data"]["type"] == "agent_spawn"
        assert delta["data"]["collapsed"] is True
        assert delta["detail_level"] == "high"


class TestSessionComplete:
    def test_session_complete_returns_update_node(self):
        data = {
            "session_id": "sess-789",
            "timestamp": "2026-03-01T12:00:05Z",
        }
        delta = map_event("session:complete", data)

        assert delta is not None
        assert delta["action"] == "update_node"
        assert delta["node_id"] == "sess-789"
        assert delta["data"]["status"] == "complete"
        assert delta["detail_level"] == "high"


class TestRecipeStepStart:
    def test_recipe_step_start_returns_add_node(self):
        data = {
            "step_id": "step-001",
            "step_name": "compile",
            "timestamp": "2026-03-01T12:00:06Z",
        }
        delta = map_event("recipe:step:start", data)

        assert delta is not None
        assert delta["action"] == "add_node"
        assert delta["node_id"] == "step-001"
        assert delta["data"]["type"] == "recipe_step"
        assert delta["data"]["step_name"] == "compile"
        assert delta["detail_level"] == "high"


class TestRecipeStepComplete:
    def test_recipe_step_complete_returns_update_node(self):
        data = {
            "step_id": "step-001",
            "timestamp": "2026-03-01T12:00:07Z",
        }
        delta = map_event("recipe:step:complete", data)

        assert delta is not None
        assert delta["action"] == "update_node"
        assert delta["node_id"] == "step-001"
        assert delta["data"]["status"] == "complete"
        assert delta["detail_level"] == "high"


class TestUnknownEvent:
    def test_unknown_event_returns_none(self):
        result = map_event("some:unknown:event", {"foo": "bar"})
        assert result is None

    def test_empty_event_returns_none(self):
        result = map_event("", {})
        assert result is None


class TestTimestampGeneration:
    def test_timestamp_generated_when_missing(self):
        data = {"request_id": "req-no-ts", "model": "claude-3"}
        delta = map_event("provider:request", data)
        assert delta is not None
        assert "timestamp" in delta
        assert isinstance(delta["timestamp"], str)
