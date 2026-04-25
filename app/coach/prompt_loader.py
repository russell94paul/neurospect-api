"""Loads and assembles the Claude system prompt.

The prompt template and strategy library live in the wiki repo (read-only from
this project's perspective). Both are static per deployment, so we load them
once at startup and cache the assembled string in memory.

The template file (system-prompt-template.md) contains the actual prompt
wrapped in a ```fenced``` block under the `## The Prompt` heading. We extract
that block and substitute `{{STRATEGY_LIBRARY_JSON}}` with the serialised
strategies file.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.config import settings

_PROMPT_FENCE_RE = re.compile(r"## The Prompt.*?```\s*\n(.*?)\n```", re.DOTALL)


def _read_prompt_template(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = _PROMPT_FENCE_RE.search(text)
    if not match:
        raise RuntimeError(
            f"Could not locate fenced prompt block under '## The Prompt' in {path}"
        )
    return match.group(1).strip()


def _read_strategies(path: Path) -> str:
    # Parse + re-dump so malformed JSON fails loud at startup instead of at
    # the first Claude call.
    data = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(data, indent=2)


@lru_cache(maxsize=1)
def get_system_prompt() -> str:
    """Return the fully-assembled system prompt. Cached for the process."""
    prompt_dir = Path(settings.ai_coach_prompt_dir).expanduser().resolve()
    template_path = prompt_dir / "system-prompt-template.md"
    strategies_path = prompt_dir / "strategies.json"

    if not template_path.exists():
        raise RuntimeError(f"AI coach template not found at {template_path}")
    if not strategies_path.exists():
        raise RuntimeError(f"AI coach strategies not found at {strategies_path}")

    template = _read_prompt_template(template_path)
    strategies = _read_strategies(strategies_path)

    if "{{STRATEGY_LIBRARY_JSON}}" not in template:
        raise RuntimeError(
            "Prompt template is missing the {{STRATEGY_LIBRARY_JSON}} placeholder"
        )

    return template.replace("{{STRATEGY_LIBRARY_JSON}}", strategies)
