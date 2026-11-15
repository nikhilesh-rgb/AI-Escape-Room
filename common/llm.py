"""Thin wrapper around the Gemini API so both versions share one client.

The wrapper takes plain chat messages and returns text. Keeping it this small
makes it easy to swap the provider or to inject a fake client in tests.
"""
from __future__ import annotations

import os
import time

try:  # optional, only used to read a local .env file
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DEFAULT_MODEL = "gemini-3.8-flash"


class LLMError(RuntimeError):
    """Raised when the LLM cannot be reached or returns nothing usable."""


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise LLMError("No GEMINI_API_KEY found. Copy .env.example to .env and add your key.")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        from google import genai  # imported lazily so tests run without the package

        self._client = genai.Client(api_key=self.api_key)

    def generate(
        self,
        system: str,
        messages: list[dict],
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> str:
        """messages: [{"role": "user" | "assistant", "content": str}, ...]"""
        from google.genai import types

        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
        )
        resp, last = None, None
        for wait in (0, 3, 8, 20, 40):  # retry on temporary overload or rate limits
            time.sleep(wait)
            try:
                resp = self._client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                break
            except Exception as exc:  # network, quota, auth ...
                last = exc
                if not any(code in str(exc) for code in ("429", "500", "503", "504")):
                    break
        if resp is None:
            raise LLMError(f"Gemini request failed: {last}") from last
        text = (resp.text or "").strip()
        if not text:
            raise LLMError("Gemini returned an empty response.")
        return text


def get_client_or_none():
    """Return a GeminiClient, or None when running offline / without a key."""
    if os.getenv("LLM_BACKEND", "").lower() == "offline":
        return None
    try:
        return GeminiClient()
    except LLMError:
        return None
