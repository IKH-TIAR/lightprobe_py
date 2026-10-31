"""Model prompts, one module per pipeline stage. Every call goes through lightprobe.llm."""

from __future__ import annotations

import os

from .. import config


def planning_model(state: dict | None) -> str:
    selected = (os.environ.get("CLAUDE_PLANNING_MODEL") or os.environ.get("OLLAMA_PLANNING_MODEL")
                or ((state or {}).get("models") or {}).get("planning"))
    if config.provider() == "ollama":
        return selected if selected and not selected.startswith("claude-") else config.ollama_settings()["model"]
    return selected if selected and selected.startswith("claude-") else config.DEFAULT_MODEL


def writing_model(state: dict | None) -> str:
    selected = (os.environ.get("CLAUDE_WRITING_MODEL") or os.environ.get("OLLAMA_WRITING_MODEL")
                or os.environ.get("CLAUDE_MODEL") or ((state or {}).get("models") or {}).get("writing"))
    if config.provider() == "ollama":
        return selected if selected and not selected.startswith("claude-") else config.ollama_settings()["model"]
    return selected if selected and selected.startswith("claude-") else config.DEFAULT_MODEL
