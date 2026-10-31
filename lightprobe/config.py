"""Paths and app-level settings. Everything lives under the app folder, so the whole app (code,
settings, universes) can be copied to another computer as one folder."""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = Path(__file__).resolve().parent / "cards"

# Universes live in ./universes unless LIGHTPROBE_DATA points elsewhere
DATA_DIR = Path(os.environ.get("LIGHTPROBE_DATA") or (APP_ROOT / "universes"))
SETTINGS_FILE = Path(os.environ.get("LIGHTPROBE_SETTINGS") or (APP_ROOT / "settings.json"))

SUPPORTED_MODELS = ["claude-sonnet-5-5", "claude-opus-5-5"]
DEFAULT_MODEL = "claude-sonnet-5-5"
LOCAL_MODELS = ["llama3.1:8b", "qwen3:8b", "qwen3:14b"]
PROVIDERS = {"anthropic": "Anthropic Claude", "ollama": "Local Ollama"}
DEFAULT_PROVIDER = "anthropic"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_CONTEXT = 32768
DEFAULT_OLLAMA_OUTPUT = 8192


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def provider() -> str:
    value = load_settings().get("provider", DEFAULT_PROVIDER)
    if value not in PROVIDERS:
        raise ValueError(f"Unknown LLM provider {value!r}. Choose Anthropic or Ollama in Settings.")
    return value


def ollama_settings() -> dict:
    settings = load_settings()
    return {
        "url": str(settings.get("ollama_url") or DEFAULT_OLLAMA_URL).rstrip("/"),
        "model": str(settings.get("ollama_model") or DEFAULT_OLLAMA_MODEL),
        "context": int(settings.get("ollama_context") or DEFAULT_OLLAMA_CONTEXT),
        "output": int(settings.get("ollama_output") or DEFAULT_OLLAMA_OUTPUT),
    }


def api_key() -> str | None:
    """ANTHROPIC_API_KEY from the environment wins; otherwise the key saved in Settings."""
    return os.environ.get("ANTHROPIC_API_KEY") or load_settings().get("anthropic_api_key") or None


def set_api_key(key: str) -> None:
    settings = load_settings()
    settings["anthropic_api_key"] = key.strip()
    save_settings(settings)


def save_provider_settings(provider_name: str, url: str, model: str, context: int, output: int) -> None:
    if provider_name not in PROVIDERS:
        raise ValueError(f"Unknown LLM provider {provider_name!r}.")
    if not model.strip():
        raise ValueError("Enter an Ollama model name, for example llama3.1:8b.")
    if context < 4096:
        raise ValueError("Ollama context must be at least 4096 tokens.")
    if output < 256:
        raise ValueError("Ollama output limit must be at least 256 tokens.")
    settings = load_settings()
    settings.update({
        "provider": provider_name,
        "ollama_url": url.strip().rstrip("/") or DEFAULT_OLLAMA_URL,
        "ollama_model": model.strip(),
        "ollama_context": int(context),
        "ollama_output": int(output),
    })
    save_settings(settings)
