"""Tests for hook module."""

from unittest.mock import AsyncMock


from hooks_graph_canvas.hook import (
    GraphCanvasHook,
    GraphCanvasTransport,
    JsonlTransport,
    WebSocketTransport,
)


class TestHookReturnsAction:
    async def test_hook_returns_continue_for_known_event(self):
        hook = GraphCanvasHook(config={})
        result = await hook("provider:request", {"request_id": "r1", "model": "m"})
        assert result == {"action": "continue"}

    async def test_hook_returns_continue_for_unknown_event(self):
        hook = GraphCanvasHook(config={})
        result = await hook("some:unknown:event", {"foo": "bar"})
        assert result == {"action": "continue"}


class TestSubsessionSkipping:
    async def test_skip_subsessions_true_skips_events_with_parent_id(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        hook = GraphCanvasHook(config={"skip_subsessions": True}, transport=transport)
        await hook(
            "provider:request",
            {"request_id": "r1", "model": "m", "parent_id": "parent-sess"},
        )
        assert len(output) == 0

    async def test_skip_subsessions_false_processes_events_with_parent_id(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        hook = GraphCanvasHook(config={"skip_subsessions": False}, transport=transport)
        await hook(
            "provider:request",
            {"request_id": "r1", "model": "m", "parent_id": "parent-sess"},
        )
        assert len(output) == 1

    async def test_skip_subsessions_default_is_true(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        hook = GraphCanvasHook(config={}, transport=transport)
        await hook(
            "provider:request",
            {"request_id": "r1", "model": "m", "parent_id": "parent-sess"},
        )
        assert len(output) == 0


class TestDeltaEmission:
    async def test_deltas_emitted_to_jsonl_transport(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        hook = GraphCanvasHook(config={}, transport=transport)
        await hook("provider:request", {"request_id": "r1", "model": "claude-3"})
        assert len(output) == 1
        assert output[0]["action"] == "add_node"
        assert output[0]["node_id"] == "r1"

    async def test_unknown_event_emits_no_delta(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        hook = GraphCanvasHook(config={}, transport=transport)
        await hook("unknown:event", {"x": 1})
        assert len(output) == 0


class TestTransportErrorHandling:
    async def test_transport_error_does_not_crash_hook(self):
        class BrokenTransport(GraphCanvasTransport):
            async def emit(self, delta: dict) -> None:
                raise RuntimeError("transport exploded")

            async def close(self) -> None:
                pass

        hook = GraphCanvasHook(config={}, transport=BrokenTransport())
        # Should NOT raise
        result = await hook("provider:request", {"request_id": "r1", "model": "m"})
        assert result == {"action": "continue"}


class TestThrottling:
    async def test_rapid_content_block_deltas_are_throttled(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        hook = GraphCanvasHook(config={"throttle_ms": 200}, transport=transport)
        # Send several content_block:delta events rapidly
        for i in range(5):
            await hook(
                "content_block:delta",
                {"request_id": "r1", "delta": {"text": f"chunk{i}"}},
            )
        # Only the first should get through within the throttle window
        assert len(output) == 1

    async def test_non_content_block_events_are_not_throttled(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        hook = GraphCanvasHook(config={"throttle_ms": 200}, transport=transport)
        # Non-content-block events should all pass through
        for i in range(3):
            await hook(
                "provider:request",
                {"request_id": f"r{i}", "model": "m"},
            )
        assert len(output) == 3


class TestJsonlTransport:
    async def test_default_output_list(self):
        transport = JsonlTransport()
        await transport.emit({"test": True})
        # Should not raise; internally stores in its own list

    async def test_custom_output_list(self):
        output: list[dict] = []
        transport = JsonlTransport(output=output)
        await transport.emit({"a": 1})
        await transport.emit({"b": 2})
        assert output == [{"a": 1}, {"b": 2}]

    async def test_close_is_noop(self):
        transport = JsonlTransport()
        await transport.close()  # Should not raise


class TestWebSocketTransport:
    async def test_emit_calls_send_func(self):
        send_func = AsyncMock()
        transport = WebSocketTransport(send_func=send_func)
        await transport.emit({"action": "add_node"})
        send_func.assert_called_once()
        # Verify it sent JSON
        import json

        sent = send_func.call_args[0][0]
        parsed = json.loads(sent)
        assert parsed["action"] == "add_node"

    async def test_emit_without_send_func_is_noop(self):
        transport = WebSocketTransport()
        await transport.emit({"action": "add_node"})  # Should not raise

    async def test_transport_error_is_caught(self):
        send_func = AsyncMock(side_effect=ConnectionError("ws closed"))
        transport = WebSocketTransport(send_func=send_func)
        # Should NOT raise
        await transport.emit({"action": "add_node"})

    async def test_close_is_noop(self):
        transport = WebSocketTransport()
        await transport.close()  # Should not raise


class TestMountFunction:
    def test_mount_returns_graph_canvas_hook(self):
        from hooks_graph_canvas import mount

        hook = mount()
        assert isinstance(hook, GraphCanvasHook)

    def test_mount_with_config(self):
        from hooks_graph_canvas import mount

        hook = mount(config={"skip_subsessions": False})
        assert isinstance(hook, GraphCanvasHook)

    def test_mount_uses_jsonl_transport_by_default(self):
        from hooks_graph_canvas import mount

        hook = mount()
        assert isinstance(hook._transport, JsonlTransport)

    def test_mount_accepts_custom_transport_from_config(self):
        from hooks_graph_canvas import mount

        custom_transport = WebSocketTransport()
        hook = mount(config={"transport": custom_transport})
        assert hook._transport is custom_transport

    def test_mount_uses_jsonl_when_transport_not_in_config(self):
        from hooks_graph_canvas import mount

        hook = mount(config={"skip_subsessions": False})
        assert isinstance(hook._transport, JsonlTransport)

    def test_mount_uses_jsonl_when_transport_is_none(self):
        from hooks_graph_canvas import mount

        hook = mount(config={"transport": None})
        assert isinstance(hook._transport, JsonlTransport)

    def test_mount_does_not_mutate_caller_config(self):
        from hooks_graph_canvas import mount

        caller_config = {"transport": WebSocketTransport(), "skip_subsessions": False}
        mount(config=caller_config)
        assert "transport" in caller_config
        assert "skip_subsessions" in caller_config
