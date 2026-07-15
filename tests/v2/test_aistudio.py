"""AI Studio provider session handling, with the browser stack stubbed.

Verifies the contract we rely on from chat_bot_ui_handler (a pip/git dep):
AIStudioUIChat(config).chat_fresh(user_prompt=, system_prompt=, file_path=).
"""
import sys
import types

import pytest

from panelflow.v2.providers import aistudio


@pytest.fixture
def fake_browser(monkeypatch):
    """Stub browser_manager + chat_bot_ui_handler; record what we're asked."""
    built = []
    calls = []
    state = {"response": '{"ok": true}', "raises": False, "cleaned": 0}

    class FakeChat:
        def __init__(self, config=None):
            built.append(config)

        def chat_fresh(self, user_prompt=None, system_prompt=None, file_path=None):
            calls.append({"user_prompt": user_prompt, "system_prompt": system_prompt,
                          "file_path": file_path})
            if state["raises"]:
                raise RuntimeError("browser exploded")
            return state["response"]

        def cleanup(self):
            state["cleaned"] += 1

    handler = types.ModuleType("chat_bot_ui_handler")
    handler.AIStudioUIChat = FakeChat
    sys.modules["chat_bot_ui_handler"] = handler

    browser_manager = types.ModuleType("browser_manager")
    browser_config = types.ModuleType("browser_manager.browser_config")
    browser_config.BrowserConfig = lambda: types.SimpleNamespace(additionl_docker_flag="")
    browser_manager.browser_config = browser_config
    sys.modules["browser_manager"] = browser_manager
    sys.modules["browser_manager.browser_config"] = browser_config

    jebin_lib = types.ModuleType("jebin_lib")
    jebin_lib.utils = types.SimpleNamespace(get_docker_volume_mounts=lambda cfg, path: [])
    sys.modules.setdefault("jebin_lib", jebin_lib)

    monkeypatch.setattr(aistudio, "_CHAT", None)
    yield {"built": built, "calls": calls, "state": state}
    aistudio._CHAT = None


def test_generate_passes_page_and_prompts_through(fake_browser):
    out = aistudio.generate("sys prompt", "user prompt", image_path="/tmp/page.jpg")

    assert out == '{"ok": true}'
    assert fake_browser["calls"] == [{
        "user_prompt": "user prompt", "system_prompt": "sys prompt", "file_path": "/tmp/page.jpg",
    }]


def test_browser_session_is_reused_across_pages(fake_browser):
    """quick_chat would start and stop a container for every page; we keep one."""
    for _ in range(3):
        aistudio.generate("sys", "user", image_path="/tmp/p.jpg")

    assert len(fake_browser["built"]) == 1
    assert len(fake_browser["calls"]) == 3


def test_empty_response_drops_the_session(fake_browser):
    """chat_bot_ui_handler swallows exceptions and returns None; a dead browser
    must not be reused by every retry."""
    fake_browser["state"]["response"] = None

    with pytest.raises(RuntimeError, match="returned nothing"):
        aistudio.generate("sys", "user", image_path="/tmp/p.jpg")
    assert fake_browser["state"]["cleaned"] == 1
    assert aistudio._CHAT is None

    fake_browser["state"]["response"] = '{"ok": true}'
    assert aistudio.generate("sys", "user", image_path="/tmp/p.jpg") == '{"ok": true}'
    assert len(fake_browser["built"]) == 2      # a fresh session was built


def test_a_raising_browser_also_drops_the_session(fake_browser):
    fake_browser["state"]["raises"] = True

    with pytest.raises(RuntimeError, match="exploded"):
        aistudio.generate("sys", "user", image_path="/tmp/p.jpg")
    assert aistudio._CHAT is None


def test_close_is_safe_when_cleanup_fails(fake_browser):
    aistudio.generate("sys", "user", image_path="/tmp/p.jpg")

    def boom():
        raise RuntimeError("docker gone")
    aistudio._CHAT.cleanup = boom

    aistudio.close()          # must not raise
    assert aistudio._CHAT is None


def test_close_is_a_noop_without_a_session(fake_browser):
    aistudio.close()
    assert aistudio._CHAT is None
