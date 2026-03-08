"""Centralized LLM client abstraction.

All LLM provider interactions are routed through this module.
To add a new provider (Anthropic, Ollama, Azure, etc.), implement the
LLMClient protocol and register it in create_llm_client().
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import openai
from openai import OpenAI


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM providers.

    Any LLM backend must implement this interface. The rest of the
    application interacts with LLMs exclusively through this protocol.
    """

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 500,
    ) -> str | None:
        """Send a chat completion request and return the response text.

        Returns None if the call fails (the caller handles fallback).
        """
        ...


class OpenAIClient:
    """OpenAI GPT implementation of LLMClient."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._client = OpenAI(api_key=api_key)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 500,
    ) -> str | None:
        """Call OpenAI Chat Completions API."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            return None
        except openai.OpenAIError as e:
            print(f"Warning: LLM API call failed ({e}).")
            return None


def create_llm_client(
    provider: str = "openai",
    api_key: str | None = None,
    model: str = "gpt-4o",
) -> LLMClient | None:
    """Factory function to create an LLM client.

    Returns None if credentials are missing (caller should use fallback).

    To add a new provider:
    1. Create a class implementing the LLMClient protocol.
    2. Add an elif branch here.
    """
    if not api_key:
        return None

    if provider == "openai":
        return OpenAIClient(api_key=api_key, model=model)
    else:
        print(f"Warning: Unknown LLM provider '{provider}'. No LLM will be used.")
        return None
