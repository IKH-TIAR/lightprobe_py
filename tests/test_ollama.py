import json

from lightprobe import config, llm


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_ollama_text_call_uses_local_endpoint(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response({
            "model": "llama3.1:8b",
            "message": {"role": "assistant", "content": "local response"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 12,
            "eval_count": 4,
        })

    monkeypatch.setattr(config, "load_settings", lambda: {
        "provider": "ollama",
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "llama3.1:8b",
        "ollama_context": 16384,
        "ollama_output": 4096,
    })
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    result = llm.generate_text(llm.CallOptions(model="llama3.1:8b", system="system"), "prompt")

    assert result == "local response"
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["payload"]["model"] == "llama3.1:8b"
    assert seen["payload"]["options"] == {"num_ctx": 16384, "num_predict": 4096}


def test_ollama_json_call_retries_with_clean_json(monkeypatch):
    responses = iter([
        {"message": {"content": "not json"}, "done": True, "done_reason": "stop"},
        {"message": {"content": '{"ok": true}'}, "done": True, "done_reason": "stop"},
    ])
    seen = []

    def fake_urlopen(request, timeout):
        seen.append(json.loads(request.data.decode("utf-8")))
        return _Response(next(responses))

    monkeypatch.setattr(config, "load_settings", lambda: {"provider": "ollama"})
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    result = llm.generate_json(
        llm.CallOptions(model="llama3.1:8b", system="system", schema={"type": "object"}),
        "prompt",
    )

    assert result == {"ok": True}
    assert seen[0]["format"] == {"type": "object"}
