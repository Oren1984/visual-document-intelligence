"""Minimal client for a local Ollama server. Both extraction paths use the same model, prompt and decoding settings;
only the input differs (image vs OCR text). Nothing is sent anywhere except the local Ollama endpoint."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .schema import DESCRIPTIONS, FIELDS, json_schema

MODEL = os.environ.get("VDI_MODEL", "qwen3-vl:4b-instruct")
HOST = os.environ.get("VDI_OLLAMA_URL", "http://127.0.0.1:11434")
TIMEOUT_S = float(os.environ.get("VDI_TIMEOUT_S", "600"))
OPTIONS = {"temperature": 0, "seed": 7, "num_ctx": 8192}

_FIELD_LINES = "\n".join(f"- {f}: {DESCRIPTIONS[f]}" for f in FIELDS)
INSTRUCTIONS = f"""You extract fields from one retail receipt.
Return a JSON object with exactly these keys:
{_FIELD_LINES}
Rules: copy text values as printed. Use null for any field that is not printed on the receipt;
do not calculate or guess missing values. Amounts are plain numbers without currency symbols."""

DIRECT_INPUT = "The receipt is the attached image."
OCR_INPUT = ("The receipt is given below as text from an OCR engine. Lines were rebuilt from the OCR boxes and "
             "may contain recognition errors.\n----- OCR TEXT -----\n{text}\n----- END -----")


class ModelError(RuntimeError):
    """The local model could not be reached or returned unusable output. Message is safe to show."""


@dataclass(frozen=True)
class ModelReply:
    fields: dict
    raw: str
    seconds: float
    eval_tokens: int | None


def _check_local(url: str) -> None:
    host = urlparse(url).hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ModelError(f"Refusing non-local model endpoint {host!r}: document images must stay on this machine.")


def extract(prompt_input: str, image_png: bytes | None = None, model: str = MODEL) -> ModelReply:
    _check_local(HOST)
    msg = {"role": "user", "content": f"{INSTRUCTIONS}\n\n{prompt_input}"}
    if image_png is not None:
        msg["images"] = [base64.b64encode(image_png).decode()]
    body = {"model": model, "messages": [msg], "stream": False, "format": json_schema(),
            "options": OPTIONS, "keep_alive": "30m"}
    try:
        r = httpx.post(f"{HOST}/api/chat", json=body, timeout=TIMEOUT_S)
    except httpx.TimeoutException:
        raise ModelError(f"The local model did not answer within {TIMEOUT_S:.0f} s.") from None
    except httpx.HTTPError:
        raise ModelError("Cannot reach the local Ollama server. Start Ollama and try again.") from None
    if r.status_code == 404:
        raise ModelError(f"Model {model!r} is not installed. Run: ollama pull {model}")
    if r.status_code != 200:
        raise ModelError(f"The local model returned HTTP {r.status_code}.")
    data = r.json()
    raw = data.get("message", {}).get("content", "")
    try:
        fields = json.loads(raw)
    except json.JSONDecodeError:
        raise ModelError("The model's output was not valid JSON.") from None
    if not isinstance(fields, dict):
        raise ModelError("The model's output was not a JSON object.")
    seconds = (data.get("total_duration") or 0) / 1e9
    return ModelReply({f: fields.get(f) for f in FIELDS}, raw, seconds, data.get("eval_count"))


def model_info(model: str = MODEL) -> dict:
    """Model name, digest and Ollama version, for run records. Empty values if the server is unreachable."""
    _check_local(HOST)
    info = {"model": model, "digest": None, "ollama": None, "endpoint": HOST, "processor": None}
    try:
        info["ollama"] = httpx.get(f"{HOST}/api/version", timeout=5).json().get("version")
        for m in httpx.get(f"{HOST}/api/tags", timeout=5).json().get("models", []):
            if m.get("name") == model:
                info["digest"] = m.get("digest")
        for m in httpx.get(f"{HOST}/api/ps", timeout=5).json().get("models", []):
            if m.get("name") == model:  # only known while the model is loaded
                info["processor"] = "GPU" if m.get("size_vram") else "CPU"
    except (httpx.HTTPError, ValueError):
        pass
    return info
