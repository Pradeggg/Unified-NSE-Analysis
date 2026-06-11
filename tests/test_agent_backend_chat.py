from __future__ import annotations

from types import SimpleNamespace


def test_openai_backend_chat_accepts_and_forwards_max_tokens():
    from terminal.agent import _OpenAIBackend

    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="ok", tool_calls=[]),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, prompt_tokens_details=None),
                model="gpt-test",
            )

    backend = object.__new__(_OpenAIBackend)
    backend.model = "gpt-test"
    backend.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

    result = backend.chat([{"role": "user", "content": "hello"}], tools=[], max_tokens=77)

    assert result["content"] == "ok"
    assert captured["max_tokens"] == 77


def test_ollama_backend_chat_accepts_max_tokens_as_num_predict():
    from terminal.agent import _OllamaBackend

    captured = {}

    class Requests:
        def post(self, url, json, timeout):
            captured.update({"url": url, "json": json, "timeout": timeout})

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"message": {"content": "ok"}}

            return Response()

    backend = object.__new__(_OllamaBackend)
    backend.model = "llama-test"
    backend.host = "http://ollama.local"
    backend.requests = Requests()

    result = backend.chat([{"role": "user", "content": "hello"}], tools=[], max_tokens=88)

    assert result["content"] == "ok"
    assert captured["json"]["options"]["num_predict"] == 88
