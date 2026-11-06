"""Controller-side OpenAI-compatible chat completion, with no credential logging."""
import json
import os
from urllib import error, request


def completion(base_url: str, model: str, api_key_env: str, *, timeout: float = 60):
    if not base_url.startswith("https://"):
        raise ValueError("Simulator endpoint must use HTTPS")
    if not model or not os.environ.get(api_key_env):
        raise ValueError("Simulator model and API key are required")
    def complete(messages):
        body = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
        req = request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                              headers={"Authorization": "Bearer " + os.environ[api_key_env],
                                       "Content-Type": "application/json"}, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as response:
                data = json.load(response)
        except error.HTTPError as exc:
            raise RuntimeError(f"Simulator provider returned HTTP {exc.code}") from None
        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Invalid simulator completion response") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Simulator returned empty content")
        return answer
    return complete
