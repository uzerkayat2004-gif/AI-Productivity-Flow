"""Regression guards for the review fixes: context capture busy-flag release
on timeout (a hung UIA worker must not poison later captures)."""

from __future__ import annotations

import time

from voice_flow import context_capture as cc


def test_timeout_releases_busy_flag() -> None:
    cc._reset_for_tests()
    try:
        def slow_adapter(hwnd):
            time.sleep(0.5)
            return cc.CursorContext(before="stale", trustworthy=True)

        first = cc.capture_cursor_context(12345, timeout_seconds=0.05, adapter=slow_adapter)
        assert first == cc.CursorContext()

        # Even though the slow worker is still running, the module must be
        # unblocked for the next capture.
        second = cc.capture_cursor_context(
            12345,
            timeout_seconds=0.2,
            adapter=lambda h: cc.CursorContext(before="fresh", trustworthy=True),
        )
        assert second.before == "fresh"

        # And once everything settles, captures still work.
        time.sleep(0.6)
        third = cc.capture_cursor_context(
            12345,
            timeout_seconds=0.2,
            adapter=lambda h: cc.CursorContext(before="final", trustworthy=True),
        )
        assert third.before == "final"
    finally:
        cc._reset_for_tests()


def test_no_hwnd_returns_empty_without_touching_busy() -> None:
    cc._reset_for_tests()
    try:
        assert cc.capture_cursor_context(None, timeout_seconds=0.01) == cc.CursorContext()
        assert cc.capture_cursor_context(0, timeout_seconds=0.01) == cc.CursorContext()
        assert cc.capture_cursor_context(
            1,
            timeout_seconds=0.2,
            adapter=lambda h: cc.CursorContext(before="ok", trustworthy=True),
        ).before == "ok"
    finally:
        cc._reset_for_tests()