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


# ---------------------------------------------------------------- prose-wrapped JSON

def _provider(monkeypatch, response):
    class Fake:
        @staticmethod
        def generate(**kwargs):
            return response
    monkeypatch.setattr(llm.providers, "text", lambda: Fake)


def test_json_is_recovered_from_a_chatty_reply(monkeypatch):
    """Google AI Mode answers conversationally and offers follow-ups."""
    _provider(monkeypatch, 'Here is the analysis you asked for:\n'
                           '{"scene_summary": "a cover", "page_type": "cover"}\n'
                           'Would you like me to analyze the interior pages?')
    assert llm.ask_json("sys", "user") == {"scene_summary": "a cover", "page_type": "cover"}


def test_json_is_recovered_from_a_fenced_chatty_reply(monkeypatch):
    _provider(monkeypatch, 'Sure! Here you go:\n```json\n{"a": 1}\n```\nAnything else?')
    assert llm.ask_json("sys", "user") == {"a": 1}


def test_prose_with_no_json_goes_to_the_reshaper(monkeypatch):
    """Prose is no longer a dead end — it is handed to TTT to transcribe. Here
    the reshaper is unavailable (see the no_live_llm fixture), so it fails."""
    _provider(monkeypatch, "This image is a comic book cover rather than an "
                           "interior story page. Intensity: 1 (Calm / Title Card)")
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        llm.ask_json("sys", "user")


def test_nested_objects_survive_extraction(monkeypatch):
    _provider(monkeypatch, 'Result: {"panels": [{"id": 1, "characters": [{"ref": "x"}]}]} done')
    assert llm.ask_json("sys", "user") == {"panels": [{"id": 1, "characters": [{"ref": "x"}]}]}


# ---------------------------------------------------------------- prose -> JSON reshape

REAL_GOOGLE_AI_ANSWER = '''The image provided is a comic book cover or title card rather than a narrative comic page with standard sequential panels.
Panels
Panel 1
role: establishing
intensity: 1
skippable: false
focal_point: [0.5, 0.5]
dialogue:
kind: caption
text: "ALL AGES"
speaker: ""
Characters
No characters from a roster appear in this title image.
If you'd like, let me know if you want to analyze more pages from this comic.'''


def test_prose_answer_is_reshaped_via_ttt(monkeypatch):
    """Google AI Mode follows the schema but renders it as text, never JSON."""
    seen = {}

    class Vision:
        @staticmethod
        def generate(**kwargs):
            return REAL_GOOGLE_AI_ANSWER

    def fake_ttt_generate(system_prompt, user_prompt, **kwargs):
        seen["system"] = system_prompt
        seen["user"] = user_prompt
        return '{"page_type": "cover", "panels": [{"id": 1, "role": "establishing"}]}'

    monkeypatch.setattr(llm.providers, "vision", lambda: Vision)
    monkeypatch.setattr("panelflow.v2.providers.ttt.generate", fake_ttt_generate)

    out = llm.ask_json("analyst instructions here", "user", image_path="/tmp/p.jpg")

    assert out == {"page_type": "cover", "panels": [{"id": 1, "role": "establishing"}]}
    # the reshaper is told to transcribe, and gets the shape via the original prompt
    assert "transcriber" in seen["system"]
    assert "analyst instructions here" in seen["user"]
    assert "ALL AGES" in seen["user"]


def test_json_answers_skip_the_reshape(monkeypatch):
    """A provider that can emit JSON (AI Studio, Gemini) costs no extra call."""
    calls = []

    class Vision:
        @staticmethod
        def generate(**kwargs):
            return '{"page_type": "story"}'

    monkeypatch.setattr(llm.providers, "vision", lambda: Vision)
    monkeypatch.setattr("panelflow.v2.providers.ttt.generate",
                        lambda **kw: calls.append(1) or "{}")

    assert llm.ask_json("sys", "user", image_path="/tmp/p.jpg") == {"page_type": "story"}
    assert calls == []


def test_a_reshape_that_also_fails_is_retried(monkeypatch):
    attempts = []

    class Vision:
        @staticmethod
        def generate(**kwargs):
            attempts.append(1)
            return "just prose, no data at all"

    monkeypatch.setattr(llm.providers, "vision", lambda: Vision)
    monkeypatch.setattr("panelflow.v2.providers.ttt.generate",
                        lambda **kw: "still not json")

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        llm.ask_json("sys", "user", image_path="/tmp/p.jpg")
    assert len(attempts) == llm.RETRIES


# ---------------------------------------------------------------- prompt contract

def test_analyze_asks_for_label_value_and_reshaper_owns_the_json_shape():
    """Google AI Mode renders structured answers as text and will not emit JSON,
    so 1.3 asks for label: value and the reshaper holds the JSON shape."""
    from panelflow.v2 import prompts

    analyze = prompts.load("analyze_page")
    assert "label: value" in analyze
    assert "PANEL 1" in analyze and "NEW_CHARACTERS" in analyze

    # 1.2's OCR owns text regions; 1.3 is never asked for a pixel coordinate
    assert "text_regions" not in analyze

    reshape = prompts.load("reshape_to_json")
    for field in ("scene_summary", "new_characters", "panels", "focal_point"):
        assert field in reshape, f"reshaper must define {field}"
    assert "transcriber" in reshape
