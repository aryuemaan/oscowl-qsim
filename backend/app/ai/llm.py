"""Thin client over Google's Gen AI SDK for Gemini and Gemma, with an offline fallback.

* Gemini (``gemini-3.8-flash``, ``gemini-4-argon``) through the Gemini API key from
  Google AI Studio, or through Vertex AI when ``GOOGLE_GENAI_USE_VERTEXAI=true``.
* Gemma (``gemma-4-26b-a4b-it``) through the same Gemini API, or a local model
  served by Ollama.
* No key? Everything still works: callers get ``None`` and use their rule-based path.

All calls ask for JSON, are cached in memory (demo-friendly, saves cost) and
never raise: errors are returned in ``meta['error']``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from functools import lru_cache

import httpx

from ..config import Settings, get_settings

log = logging.getLogger("qsim.ai")


def parse_json_lenient(text: str | None) -> dict | None:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        val = json.loads(t)
        return val if isinstance(val, dict) else {"items": val}
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            try:
                return json.loads(t[i : j + 1])
            except json.JSONDecodeError:
                return None
    return None


class AIClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self._client = None
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self.last_error: str | None = None
        has_cred = bool(settings.gemini_api_key) or settings.google_genai_use_vertexai
        if settings.qsim_ai_mode == "offline" or not has_cred:
            self.mode = "offline"
        else:
            self.mode = "gemini"
        prov = settings.gemma_provider
        if prov == "ollama":
            self.gemma_provider = "ollama"
        elif prov in ("auto", "gemini_api") and self.mode == "gemini":
            self.gemma_provider = "gemini_api"
        else:
            self.gemma_provider = "off"

    # ---------------------------------------------------------------- status
    @property
    def online(self) -> bool:
        return self.mode == "gemini"

    def status(self) -> dict:
        return {
            "mode": self.mode,
            "via": "vertex_ai" if self.s.google_genai_use_vertexai else ("gemini_api" if self.online else None),
            "flash_model": self.s.gemini_flash_model,
            "reasoning_model": self.s.gemini_reasoning_model,
            "gemma_provider": self.gemma_provider,
            "gemma_model": self.s.ollama_gemma_model if self.gemma_provider == "ollama" else self.s.gemma_model,
            "last_error": self.last_error,
        }

    # ---------------------------------------------------------------- calls
    def _sdk(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            http = types.HttpOptions(timeout=int(self.s.ai_timeout_s * 1000))
            if self.s.google_genai_use_vertexai:
                self._client = genai.Client(vertexai=True, project=self.s.google_cloud_project or None,
                                            location=self.s.google_cloud_location, http_options=http)
            else:
                self._client = genai.Client(api_key=self.s.gemini_api_key, http_options=http)
        return self._client

    def _cached(self, key: str) -> dict | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _store(self, key: str, value: dict) -> None:
        self._cache[key] = value
        while len(self._cache) > 256:
            self._cache.popitem(last=False)

    def generate_json(self, *, model: str, system: str, prompt: str, thinking: str | None = "low",
                      max_tokens: int = 4096, gemma: bool = False) -> tuple[dict | None, dict]:
        """Call a Gemini/Gemma model and parse a JSON object from the answer."""
        provider = "gemma" if gemma else "gemini"
        meta = {"provider": provider, "model": model, "latency_ms": 0.0, "cached": False, "error": None}
        if not self.online and not (gemma and self.gemma_provider == "ollama"):
            meta["provider"], meta["error"] = "offline", "AI is offline (no GEMINI_API_KEY)"
            return None, meta
        key = hashlib.sha256(f"{model}|{system}|{prompt}".encode()).hexdigest()
        hit = self._cached(key)
        if hit is not None:
            meta["cached"] = True
            return hit, meta
        t0 = time.perf_counter()
        try:
            if gemma and self.gemma_provider == "ollama":
                meta["provider"], meta["model"] = "ollama", self.s.ollama_gemma_model
                data = self._ollama(system, prompt)
            else:
                data = self._gemini(model, system, prompt, thinking, max_tokens, gemma)
        except Exception as exc:  # network, quota, bad model id, ...
            self.last_error = f"{type(exc).__name__}: {exc}"[:400]
            meta["error"] = self.last_error
            log.warning("AI call failed (%s): %s", model, self.last_error)
            data = None
        meta["latency_ms"] = (time.perf_counter() - t0) * 1000
        if data is not None:
            self._store(key, data)
            self.last_error = None
        elif meta["error"] is None:
            meta["error"] = "Model answer was not valid JSON"
        return data, meta

    def _gemini(self, model: str, system: str, prompt: str, thinking: str | None, max_tokens: int, gemma: bool) -> dict | None:
        from google.genai import types

        client = self._sdk()
        if gemma:  # Gemma on the Gemini API: no system instruction / JSON mode, so inline both
            resp = client.models.generate_content(
                model=model, contents=f"{system}\n\n{prompt}\n\nRespond with a single JSON object only.",
                config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=max_tokens))
            return parse_json_lenient(resp.text)
        base = dict(system_instruction=system, temperature=0.2, max_output_tokens=max_tokens,
                    response_mime_type="application/json")
        try:
            cfg = types.GenerateContentConfig(**base, thinking_config=types.ThinkingConfig(thinking_level=thinking)) if thinking else types.GenerateContentConfig(**base)
            resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
        except Exception:
            if not thinking:
                raise
            resp = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(**base))
        return parse_json_lenient(resp.text)

    def _ollama(self, system: str, prompt: str) -> dict | None:
        r = httpx.post(
            f"{self.s.ollama_url.rstrip('/')}/api/chat",
            json={"model": self.s.ollama_gemma_model, "stream": False, "format": "json",
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
            timeout=self.s.ai_timeout_s,
        )
        r.raise_for_status()
        return parse_json_lenient(r.json().get("message", {}).get("content"))


@lru_cache
def get_ai_client() -> AIClient:
    return AIClient(get_settings())
