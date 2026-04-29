import json
import logging
import os
import random
import time
from typing import Protocol

import httpx

from backend_arena.src.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMTimeoutError,
    RateLimitError,
)
from backend_arena.src.schemas.types import ChatMessage

log = logging.getLogger(__name__)

_BASE_DELAY = 2.0
_MULTIPLIER = 2.0
_MAX_WAIT = 10.0
_MAX_RETRIES = 3
_READ_TIMEOUT = 30.0


class LLMAdapter(Protocol):
    def __call__(self, system_prompt: str, chat_history: list[ChatMessage]) -> str: ...


def _with_backoff(fn):
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return fn()
        except RateLimitError:
            if attempt == _MAX_RETRIES:
                raise
            cap = min(_BASE_DELAY * (_MULTIPLIER ** attempt), _MAX_WAIT)
            sleep_s = random.uniform(0, cap)
            log.warning("Rate limited — retry %d/%d in %.2fs", attempt + 1, _MAX_RETRIES, sleep_s)
            time.sleep(sleep_s)


class MockAdapter:
    def __call__(self, system_prompt: str, chat_history: list[ChatMessage]) -> str:
        return json.dumps({
            "internal_monologue": "Scanning opponent's argument for logical gaps. Found three.",
            "spoken_dialogue": "Is that really your best shot? My logic is airtight — yours is a house of cards.",
            "sentiment_score": 20,
            "aggression_level": 65,
        })


class OpenAIAdapter:
    def __init__(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=_READ_TIMEOUT)
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def __call__(self, system_prompt: str, chat_history: list[ChatMessage]) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in chat_history]
        return _with_backoff(lambda: self._call(messages))

    def _call(self, messages: list[dict]) -> str:
        import openai
        try:
            r = self._client.chat.completions.create(model=self._model, messages=messages)
            return r.choices[0].message.content
        except openai.AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except openai.RateLimitError as e:
            raise RateLimitError(str(e)) from e
        except openai.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except openai.APIConnectionError as e:
            raise LLMConnectionError(str(e)) from e


class ClaudeAdapter:
    def __init__(self) -> None:
        import anthropic
        self._client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    def __call__(self, system_prompt: str, chat_history: list[ChatMessage]) -> str:
        messages = [
            {"role": m.role, "content": m.content}
            for m in chat_history
            if m.role != "system"
        ]
        return _with_backoff(lambda: self._call(system_prompt, messages))

    def _call(self, system_prompt: str, messages: list[dict]) -> str:
        import anthropic
        try:
            r = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
            )
            return r.content[0].text
        except anthropic.AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(str(e)) from e
        except anthropic.APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except anthropic.APIConnectionError as e:
            raise LLMConnectionError(str(e)) from e


class GroqAdapter:
    def __init__(self) -> None:
        from groq import Groq
        self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self._model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    def __call__(self, system_prompt: str, chat_history: list[ChatMessage]) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in chat_history]
        return _with_backoff(lambda: self._call(messages))

    def _call(self, messages: list[dict]) -> str:
        import groq
        try:
            r = self._client.chat.completions.create(model=self._model, messages=messages)
            return r.choices[0].message.content
        except groq.AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except groq.RateLimitError as e:
            raise RateLimitError(str(e)) from e
        except httpx.ReadTimeout as e:
            raise LLMTimeoutError(str(e)) from e
        except httpx.ConnectError as e:
            raise LLMConnectionError(str(e)) from e


class OllamaAdapter:
    def __init__(self) -> None:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._client = httpx.Client(base_url=base_url, timeout=_READ_TIMEOUT)
        self._model = os.getenv("OLLAMA_MODEL", "llama3")

    def __call__(self, system_prompt: str, chat_history: list[ChatMessage]) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in chat_history]
        return _with_backoff(lambda: self._call(messages))

    def _call(self, messages: list[dict]) -> str:
        try:
            r = self._client.post(
                "/api/chat",
                json={"model": self._model, "messages": messages, "stream": False},
            )
            if r.status_code in (401, 403):
                raise LLMAuthError(f"Ollama auth error: HTTP {r.status_code}")
            if r.status_code == 429:
                raise RateLimitError("Ollama rate limited")
            r.raise_for_status()
            return r.json()["message"]["content"]
        except httpx.ReadTimeout as e:
            raise LLMTimeoutError(str(e)) from e
        except httpx.ConnectError as e:
            raise LLMConnectionError(str(e)) from e


class HuggingFaceAdapter:
    def __init__(self) -> None:
        self._api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        self._model = os.getenv("HUGGINGFACE_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
        self._url = f"https://api-inference.huggingface.co/models/{self._model}/v1/chat/completions"
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=_READ_TIMEOUT,
        )

    def __call__(self, system_prompt: str, chat_history: list[ChatMessage]) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in chat_history]
        return _with_backoff(lambda: self._call(messages))

    def _call(self, messages: list[dict]) -> str:
        try:
            r = self._client.post(
                self._url,
                json={"model": self._model, "messages": messages, "max_tokens": 2048},
            )
            if r.status_code in (401, 403):
                raise LLMAuthError(f"HuggingFace auth error: HTTP {r.status_code}")
            if r.status_code == 429:
                raise RateLimitError("HuggingFace rate limited")
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except httpx.ReadTimeout as e:
            raise LLMTimeoutError(str(e)) from e
        except httpx.ConnectError as e:
            raise LLMConnectionError(str(e)) from e


_adapter_cache: dict[str, LLMAdapter] = {}


def route(selected_llm: str) -> LLMAdapter:
    if selected_llm not in _adapter_cache:
        if selected_llm == "mock":
            _adapter_cache["mock"] = MockAdapter()
        elif selected_llm == "openai":
            _adapter_cache["openai"] = OpenAIAdapter()
        elif selected_llm == "claude":
            _adapter_cache["claude"] = ClaudeAdapter()
        elif selected_llm == "groq":
            _adapter_cache["groq"] = GroqAdapter()
        elif selected_llm == "ollama":
            _adapter_cache["ollama"] = OllamaAdapter()
        elif selected_llm == "huggingface":
            _adapter_cache["huggingface"] = HuggingFaceAdapter()
        else:
            raise ValueError(f"Unknown LLM: {selected_llm!r}")
    return _adapter_cache[selected_llm]


