"""Shared model call layer. Every model call in the app goes through here, so providers can be
selected without changing the pipeline stages.

- All calls stream (large outputs would otherwise hit HTTP timeouts).
- Stable context is sent as a cached system block (prompt caching).
- The server-side refusal fallback is on, so a declined request is re-run instead of failing.
- Truncated JSON is never "repaired": it raises TruncatedOutputError so the caller splits the work.
- Long prose that hits the output limit is continued in the same conversation, never shortened.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import anthropic

from . import config, storage

log = logging.getLogger("lightprobe.llm")

DEFAULT_MAX_TOKENS = 64000
# Stop reasons that mean the output was cut off before it was complete
TRUNCATED = ("max_tokens", "model_context_window_exceeded")
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Universe the current job works on (usage is recorded per universe)
current_universe: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_universe", default=None)

# USD per million tokens: input, output, cache read. Cache writes bill at 1.25x input.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
}


class TruncatedOutputError(Exception):
    def __init__(self, partial: str):
        super().__init__("Model output hit max_tokens and was truncated")
        self.partial = partial


class RefusalError(Exception):
    pass


class MissingAPIKeyError(Exception):
    pass


class OllamaConnectionError(Exception):
    pass


@dataclass
class LocalMessage:
    text: str
    stop_reason: str
    usage: Any = None


@dataclass
class CallOptions:
    model: str
    system: str
    cached_context: str = ""          # stable context, sent after the system prompt with a cache breakpoint
    max_tokens: int = DEFAULT_MAX_TOKENS
    effort: str | None = None         # low | medium | high | xhigh | max
    schema: dict | None = None        # JSON schema for structured output
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Structured-output schema helpers (every object closed; all properties required)
# ---------------------------------------------------------------------------

S = {"type": "string"}
I = {"type": "integer"}
N = {"type": "number"}
B = {"type": "boolean"}


def arr(items: dict) -> dict:
    return {"type": "array", "items": items}


def obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def enum(*values: str) -> dict:
    return {"type": "string", "enum": list(values)}


# ---------------------------------------------------------------------------
# Client and usage tracking
# ---------------------------------------------------------------------------

_client_lock = threading.Lock()
_client: anthropic.Anthropic | None = None
_client_key: str | None = None


def client() -> anthropic.Anthropic:
    global _client, _client_key
    key = config.api_key()
    if not key:
        raise MissingAPIKeyError("No Anthropic API key. Add it in Settings (top right) before running a step.")
    with _client_lock:
        if _client is None or key != _client_key:
            _client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=900.0)
            _client_key = key
        return _client


_usage_lock = threading.Lock()


def record_usage(model: str, usage: Any, requested_model: str | None = None) -> None:
    if usage is None:
        return
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cread = getattr(usage, "cache_read_input_tokens", 0) or 0
    cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
    note = f" | cache hit {cread}" if cread else (f" | cache write {cwrite}" if cwrite else "")
    log.info("[tokens] %s in=%s out=%s%s", model, inp, out, note)
    name = current_universe.get()
    if not name:
        return
    if config.provider() == "ollama":
        cost = 0.0
    else:
        p_in, p_out, p_cache = PRICES.get(model) or PRICES.get(requested_model or "") or PRICES[config.DEFAULT_MODEL]
        cost = (inp * p_in + out * p_out + cread * p_cache + cwrite * p_in * 1.25) / 1_000_000
    path = storage.universe_dir(name) / "usage.json"
    with _usage_lock:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"calls": 0, "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "estimatedUSD": 0.0}
        data["calls"] += 1
        data["input"] += inp
        data["output"] += out
        data["cacheRead"] += cread
        data["cacheWrite"] += cwrite
        data["estimatedUSD"] = round(data["estimatedUSD"] + cost, 4)
        storage.atomic_write(path, json.dumps(data, indent=2))


def read_usage(name: str) -> dict:
    path = storage.universe_dir(name) / "usage.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------

def _system_blocks(opts: CallOptions) -> list[dict]:
    blocks: list[dict] = [{"type": "text", "text": opts.system}]
    if opts.cached_context.strip():
        blocks.append({"type": "text", "text": opts.cached_context, "cache_control": {"type": "ephemeral"}})
    return blocks


def _call(opts: CallOptions, messages: list[dict]):
    if config.provider() == "ollama":
        return _call_ollama(opts, messages)
    output_config: dict = {}
    if opts.effort:
        output_config["effort"] = opts.effort
    if opts.schema:
        output_config["format"] = {"type": "json_schema", "schema": opts.schema}
    kwargs: dict = {
        "model": opts.model,
        "max_tokens": opts.max_tokens,
        "system": _system_blocks(opts),
        "messages": messages,
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
        **opts.extra,
    }
    if output_config:
        kwargs["output_config"] = output_config
    log.info("[call] %s", opts.model)
    with client().beta.messages.stream(**kwargs) as stream:
        message = stream.get_final_message()
    record_usage(getattr(message, "model", None) or opts.model, message.usage, opts.model)
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        explanation = getattr(details, "explanation", None) if details else None
        raise RefusalError(f"Claude declined this request{f' ({category})' if category else ''}{f': {explanation}' if explanation else ''}")
    return message


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
            for item in content
        )
    return str(content)


def _call_ollama(opts: CallOptions, messages: list[dict]) -> LocalMessage:
    settings = config.ollama_settings()
    model = opts.model if opts.model and not opts.model.startswith("claude-") else settings["model"]
    ollama_messages = [{"role": "system", "content": opts.system}]
    if opts.cached_context.strip():
        ollama_messages.append({"role": "system", "content": opts.cached_context})
    ollama_messages.extend({"role": m["role"], "content": _message_text(m.get("content", ""))} for m in messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
        "options": {
            "num_ctx": settings["context"],
            "num_predict": min(opts.max_tokens, settings["output"]),
        },
    }
    if opts.schema:
        payload["format"] = opts.schema
    request = urllib.request.Request(
        f"{settings['url']}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    log.info("[call] Ollama %s (ctx=%s)", payload["model"], settings["context"])
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace").strip()
        raise OllamaConnectionError(f"Ollama rejected the request ({err.code}): {detail or err.reason}") from err
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        raise OllamaConnectionError(
            f"Could not reach Ollama at {settings['url']}. Start Ollama and make sure {payload['model']!r} is installed."
        ) from err
    if not isinstance(result, dict) or not isinstance(result.get("message"), dict):
        raise OllamaConnectionError("Ollama returned an unexpected response without a message.")
    reason = result.get("done_reason") or ("end_turn" if result.get("done", True) else "max_tokens")
    if reason in ("length", "limit"):
        reason = "max_tokens"
    usage = type("Usage", (), {
        "input_tokens": result.get("prompt_eval_count", 0),
        "output_tokens": result.get("eval_count", 0),
    })()
    message = LocalMessage(_message_text(result["message"].get("content", "")), reason, usage)
    record_usage(payload["model"], usage, payload["model"])
    return message


def _text_of(message) -> str:
    if isinstance(message, LocalMessage):
        return message.text
    return "".join(b.text for b in message.content if getattr(b, "type", "") == "text")


def _assistant_content(message) -> list[dict]:
    if isinstance(message, LocalMessage):
        return [{"role": "assistant", "content": message.text}]
    # by_alias: some blocks have wire names that are Python keywords (a fallback block's "from" is from_)
    return [b.model_dump(by_alias=True, exclude_none=True) for b in message.content]


def extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        return fenced.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return text.strip()
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start:end + 1]


def generate_json(opts: CallOptions, prompt: str) -> Any:
    """Structured call. Raises TruncatedOutputError on max_tokens (the caller splits the work)."""
    messages: list[dict] = [{"role": "user", "content": prompt}]
    for attempt in (1, 2):
        message = _call(opts, messages)
        text = _text_of(message)
        if message.stop_reason in TRUNCATED:
            raise TruncatedOutputError(text)
        try:
            return json.loads(extract_json(text))
        except json.JSONDecodeError as err:
            if attempt == 2:
                raise ValueError(f"Model returned invalid JSON: {err}") from err
            messages.append({"role": "assistant", "content": _assistant_content(message)})
            messages.append({"role": "user", "content": "That response was not valid JSON. Reply again with ONLY the complete, valid JSON object - no prose, no code fences."})
    raise AssertionError("unreachable")


def generate_text(opts: CallOptions, prompt: str, max_continuations: int = 3) -> str:
    """Long-form text. Output that hits max_tokens is continued in the same conversation
    (append-only) rather than retried shorter, so long chapters are never condensed to fit."""
    messages: list[dict] = [{"role": "user", "content": prompt}]
    output = ""
    for i in range(max_continuations + 1):
        message = _call(opts, messages)
        output += _text_of(message)
        if message.stop_reason not in TRUNCATED:
            return output
        if message.stop_reason != "max_tokens" or i == max_continuations:
            # Out of continuations, or the context window itself is full (continuing would only make it fuller)
            raise TruncatedOutputError(output)
        log.warning("Output hit max_tokens - requesting continuation %s/%s", i + 1, max_continuations)
        messages.append({"role": "assistant", "content": _assistant_content(message)})
        messages.append({"role": "user", "content": "Your output was cut off by the length limit. Continue EXACTLY where you stopped, mid-sentence if necessary. Do not repeat anything already written and do not add commentary."})
    return output


def parse_sections(text: str, names: list[str]) -> dict[str, str]:
    """Delimited sections (<<<NAME>>>) keep long prose out of JSON string escaping."""
    out: dict[str, str] = {}
    for i, name in enumerate(names):
        marker = f"<<<{name}>>>"
        start = text.find(marker)
        if start < 0:
            out[name] = ""
            continue
        frm = start + len(marker)
        end = len(text)
        for other in names[i + 1:] + ["END"]:
            idx = text.find(f"<<<{other}>>>", frm)
            if 0 <= idx < end:
                end = idx
        out[name] = text[frm:end].strip()
    return out


def tail(text: str, chars: int) -> str:
    if not text:
        return ""
    return "...(earlier text omitted)\n" + text[-chars:] if len(text) > chars else text
