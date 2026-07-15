"""Provider plumbing: the response-shape quirks each one has in the wild."""
import json

import pytest

from panelflow.v2 import llm
from panelflow.v2.providers import ttt


# ---------------------------------------------------------------- TTT envelope

def test_unwrap_reads_the_opencode_envelope():
    result = json.dumps({"response": '{"merges": []}'})
    assert ttt._unwrap(result) == '{"merges": []}'


def test_unwrap_reads_the_qwen_envelope():
    """qwen returns "text", opencode returns "response" — same service."""
    result = json.dumps({"text": '{"merges": []}', "model": "qwen3.5:4b"})
    assert ttt._unwrap(result) == '{"merges": []}'


def test_unwrap_rejects_an_empty_result():
    with pytest.raises(RuntimeError, match="empty result"):
        ttt._unwrap(None)


def test_unwrap_rejects_an_envelope_with_no_body():
    with pytest.raises(RuntimeError, match="no text"):
        ttt._unwrap(json.dumps({"model": "qwen3.5:4b"}))


# ---------------------------------------------------------------- fence stripping

def test_strip_fence_unwraps_json_fences():
    """opencode answers in chat form and fences its JSON."""
    assert llm._strip_fence('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fence_unwraps_bare_fences():
    assert llm._strip_fence('```\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fence_leaves_plain_json_alone():
    assert llm._strip_fence('{"a": 1}') == '{"a": 1}'


def test_strip_fence_handles_empty_input():
    assert llm._strip_fence(None) == ""


# ---------------------------------------------------------------- routing

def test_text_calls_go_to_the_text_provider(monkeypatch):
    calls = []

    class FakeText:
        @staticmethod
        def generate(**kwargs):
            calls.append("text")
            return '{"ok": true}'

    monkeypatch.setattr(llm.providers, "text", lambda: FakeText)
    assert llm.ask_json("sys", "user") == {"ok": True}
    assert calls == ["text"]


def test_vision_calls_go_to_the_vision_provider(monkeypatch):
    calls = []

    class FakeVision:
        @staticmethod
        def generate(**kwargs):
            calls.append(kwargs["image_path"])
            return '{"ok": true}'

    monkeypatch.setattr(llm.providers, "vision", lambda: FakeVision)
    assert llm.ask_json("sys", "user", image_path="/tmp/page.jpg") == {"ok": True}
    assert calls == ["/tmp/page.jpg"]


def test_ask_json_retries_then_raises(monkeypatch):
    attempts = []

    class Flaky:
        @staticmethod
        def generate(**kwargs):
            attempts.append(1)
            raise RuntimeError("browser died")

    monkeypatch.setattr(llm.providers, "text", lambda: Flaky)
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        llm.ask_json("sys", "user")
    assert len(attempts) == llm.RETRIES


def test_ask_json_recovers_on_a_later_attempt(monkeypatch):
    state = {"n": 0}

    class Flaky:
        @staticmethod
        def generate(**kwargs):
            state["n"] += 1
            if state["n"] < 2:
                raise RuntimeError("transient")
            return '```json\n{"ok": true}\n```'

    monkeypatch.setattr(llm.providers, "text", lambda: Flaky)
    assert llm.ask_json("sys", "user") == {"ok": True}


def test_ask_json_rejects_a_non_object_response(monkeypatch):
    class Listy:
        @staticmethod
        def generate(**kwargs):
            return '["not", "an", "object"]'

    monkeypatch.setattr(llm.providers, "text", lambda: Listy)
    with pytest.raises(RuntimeError, match="failed after"):
        llm.ask_json("sys", "user")
