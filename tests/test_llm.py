"""The model client: local-only endpoint, and clear errors instead of invented output."""

import httpx
import pytest

from vdi import llm


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_refuses_non_local_endpoint(monkeypatch):
    monkeypatch.setattr(llm, "HOST", "https://api.example.com")
    with pytest.raises(llm.ModelError, match="non-local"):
        llm.extract("x")


@pytest.mark.parametrize("resp,msg", [
    (Resp(200, {"message": {"content": "sorry, I cannot"}}), "not valid JSON"),
    (Resp(200, {"message": {"content": "[1, 2]"}}), "not a JSON object"),
    (Resp(404, {}), "not installed"),
    (Resp(500, {}), "HTTP 500"),
])
def test_bad_model_replies_become_errors(monkeypatch, resp, msg):
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: resp)
    with pytest.raises(llm.ModelError, match=msg):
        llm.extract("x")


def test_unreachable_server(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(llm.httpx, "post", boom)
    with pytest.raises(llm.ModelError, match="Cannot reach"):
        llm.extract("x")


def test_both_paths_send_the_same_instructions_and_schema(monkeypatch):
    sent = []
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, timeout: sent.append(json) or Resp(200, {"message": {"content": "{}"}}))
    llm.extract(llm.DIRECT_INPUT, image_png=b"png")
    llm.extract(llm.OCR_INPUT.format(text="TOTAL 1.00"))
    a, b = sent
    assert a["format"] == b["format"] and a["options"] == b["options"] and a["model"] == b["model"]
    assert a["messages"][0]["content"].startswith(llm.INSTRUCTIONS) and b["messages"][0]["content"].startswith(llm.INSTRUCTIONS)
    assert "images" in a["messages"][0] and "images" not in b["messages"][0]
