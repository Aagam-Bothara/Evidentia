"""LLM client — unified interface for OpenAI and Anthropic APIs."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from evidentia.core.config import LLMProvider, Settings
from evidentia.core.exceptions import EvidentiaCoreError
from evidentia.core.logging import get_logger

logger = get_logger(__name__)


class LLMResponse:
    """Parsed response from an LLM call."""

    def __init__(self, content: str, usage: dict[str, int] | None = None) -> None:
        self.content = content
        self.usage = usage or {}

    def as_json(self) -> dict[str, Any]:
        """Parse the response content as JSON."""
        # Strip markdown code fences if present
        text = self.content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # Remove opening ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)


class BaseLLM(ABC):
    """Abstract LLM interface."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Send a chat completion request."""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion with tool definitions (function calling)."""

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Yield tokens as they arrive from the LLM.

        Default implementation falls back to non-streaming chat.
        Subclasses override for real streaming.
        """
        response = await self.chat(messages, temperature, max_tokens)
        yield response.content


class OpenAILLM(BaseLLM):
    """OpenAI-compatible LLM client."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: str | None = None,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json":
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        logger.info("llm_call", model=self._model, tokens=usage.get("total_tokens", 0))
        return LLMResponse(content=content, usage=usage)

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": tools,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        message = data["choices"][0]["message"]
        # If the model called tools, return the tool calls as JSON
        content = json.dumps(message["tool_calls"]) if message.get("tool_calls") else message.get("content", "")

        return LLMResponse(content=content, usage=data.get("usage", {}))

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Yield tokens as they arrive from OpenAI-compatible API."""
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with (
            httpx.AsyncClient(timeout=120) as client,
            client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

        logger.info("llm_stream_complete", model=self._model)


class AnthropicLLM(BaseLLM):
    """Anthropic Claude LLM client."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = "https://api.anthropic.com/v1"

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: str | None = None,
    ) -> LLMResponse:
        # Separate system message from user/assistant messages
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)

        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["content"][0]["text"]
        usage = data.get("usage", {})
        logger.info("llm_call", model=self._model, tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
        return LLMResponse(content=content, usage=usage)

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Convert OpenAI-style tool defs to Anthropic format
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", tool)
            anthropic_tools.append(
                {
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                }
            )

        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)

        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
            "tools": anthropic_tools,
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract tool use blocks
        tool_uses = [b for b in data["content"] if b["type"] == "tool_use"]
        if tool_uses:
            content = json.dumps(tool_uses)
        else:
            text_blocks = [b for b in data["content"] if b["type"] == "text"]
            content = text_blocks[0]["text"] if text_blocks else ""

        return LLMResponse(content=content, usage=data.get("usage", {}))

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Yield tokens as they arrive from Anthropic API."""
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)

        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
            "stream": True,
        }
        if system:
            body["system"] = system

        async with (
            httpx.AsyncClient(timeout=120) as client,
            client.stream(
                "POST",
                f"{self._base_url}/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                    if event.get("type") == "content_block_delta":
                        token = event.get("delta", {}).get("text")
                        if token:
                            yield token
                    elif event.get("type") == "message_stop":
                        break
                except (json.JSONDecodeError, KeyError):
                    continue

        logger.info("llm_stream_complete", model=self._model)


def create_llm(settings: Settings) -> BaseLLM:
    """Factory: create the appropriate LLM client from settings."""
    if settings.llm_provider == LLMProvider.OPENAI:
        if not settings.openai_api_key:
            raise EvidentiaCoreError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAILLM(api_key=settings.openai_api_key)
    elif settings.llm_provider == LLMProvider.ANTHROPIC:
        if not settings.anthropic_api_key:
            raise EvidentiaCoreError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return AnthropicLLM(api_key=settings.anthropic_api_key)
    else:
        raise EvidentiaCoreError(f"Unsupported LLM provider: {settings.llm_provider}")
