"""prompt_loader extracts the fenced system prompt and injects strategies."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from app.coach import prompt_loader


def _write_fixtures(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "system-prompt-template.md").write_text(
        textwrap.dedent(
            """\
            ---
            title: fake
            ---

            # heading

            ## The Prompt

            Blah.

            ```
            You are the coach.

            Strategies:

            {{STRATEGY_LIBRARY_JSON}}

            End.
            ```

            ## Trailing section
            """
        ),
        encoding="utf-8",
    )
    (tmp / "strategies.json").write_text(
        json.dumps({"version": "test", "strategies": [{"id": "x"}]}),
        encoding="utf-8",
    )
    return tmp


def test_prompt_assembly(tmp_path, monkeypatch):
    fixtures = _write_fixtures(tmp_path / "ai-coach")
    monkeypatch.setattr(
        prompt_loader.settings, "ai_coach_prompt_dir", str(fixtures), raising=False
    )
    prompt_loader.get_system_prompt.cache_clear()

    prompt = prompt_loader.get_system_prompt()
    assert "You are the coach." in prompt
    assert "{{STRATEGY_LIBRARY_JSON}}" not in prompt
    assert '"id": "x"' in prompt
    assert "Trailing section" not in prompt


def test_missing_placeholder_raises(tmp_path, monkeypatch):
    fixtures = tmp_path / "ai-coach"
    fixtures.mkdir(parents=True)
    (fixtures / "system-prompt-template.md").write_text(
        "## The Prompt\n\n```\nno placeholder here\n```\n", encoding="utf-8"
    )
    (fixtures / "strategies.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        prompt_loader.settings, "ai_coach_prompt_dir", str(fixtures), raising=False
    )
    prompt_loader.get_system_prompt.cache_clear()
    with pytest.raises(RuntimeError):
        prompt_loader.get_system_prompt()


def test_missing_files_raise(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(
        prompt_loader.settings, "ai_coach_prompt_dir", str(empty), raising=False
    )
    prompt_loader.get_system_prompt.cache_clear()
    with pytest.raises(RuntimeError):
        prompt_loader.get_system_prompt()
