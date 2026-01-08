# Copyright 2025-2026 Dimensional Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""API adapters for different LLM providers.

This module provides abstract base classes and concrete implementations for
adapting different LLM provider APIs to a common interface.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class AgentCapabilities:
    """Defines what capabilities an agent/model supports."""

    supports_images: bool = True
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_system_messages: bool = True
    supports_thinking: bool = False
    max_context_length: int = 128000
    supports_structured_output: bool = False


@dataclass
class UnifiedMessage:
    """Unified message format that can be converted to provider-specific formats."""

    role: str  # 'system', 'user', 'assistant', 'tool'
    content: Optional[str] = None
    images: Optional[List[str]] = None  # Base64 encoded images
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # For tool messages
    thinking_content: Optional[str] = None  # For Claude's thinking


@dataclass
class UnifiedResponse:
    """Unified response format from LLM providers."""

    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    thinking_blocks: Optional[List[str]] = None
    raw_response: Optional[Any] = None  # Original response object

    def __str__(self):
        parts = []
        if self.content:
            parts.append(self.content)
        if self.tool_calls:
            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in self.tool_calls]
            parts.append(f"[Tools called: {', '.join(tool_names)}]")
        return "\n".join(parts) if parts else "[No content]"


class AbstractAPIAdapter(ABC):
    """Abstract base class for LLM API adapters."""

    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.capabilities = self.get_capabilities()

    @abstractmethod
    def get_capabilities(self) -> AgentCapabilities:
        """Return the capabilities of this model/API."""
        pass

    @abstractmethod
    def convert_messages(self, messages: List[UnifiedMessage], **kwargs) -> Any:
        """Convert unified messages to provider-specific format."""
        pass

    @abstractmethod
    def convert_tools(self, tools: List[Dict[str, Any]]) -> Optional[Any]:
        """Convert DIMOS tools to provider-specific format."""
        pass

    @abstractmethod
    def send_request(self, messages: Any, tools: Optional[Any] = None, **kwargs) -> UnifiedResponse:
        """Send request to the API and return unified response."""
        pass

    def validate_request(self, messages: List[UnifiedMessage]) -> List[UnifiedMessage]:
        """Validate and filter messages based on capabilities."""
        validated_messages = []

        for msg in messages:
            # Skip images if not supported
            if msg.images and not self.capabilities.supports_images:
                # Convert to text-only message
                validated_msg = UnifiedMessage(
                    role=msg.role,
                    content=msg.content or "[Image content not supported by this model]",
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
                validated_messages.append(validated_msg)
            else:
                validated_messages.append(msg)

        return validated_messages


# --- OpenAI Adapter ---


class OpenAIAdapter(AbstractAPIAdapter):
    """Adapter for OpenAI API."""

    def __init__(self, model_name: str, client=None, **kwargs):
        super().__init__(model_name, **kwargs)
        if client is None:
            from openai import OpenAI

            self.client = OpenAI()
        else:
            self.client = client

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_images="vision" in self.model_name or "gpt-4" in self.model_name,
            supports_tools=True,
            supports_streaming=True,
            supports_system_messages=True,
            supports_thinking=False,
            max_context_length=128000 if "gpt-4" in self.model_name else 16385,
            supports_structured_output=True,
        )

    def convert_messages(self, messages: List[UnifiedMessage], **kwargs) -> List[Dict[str, Any]]:
        """Convert to OpenAI format."""
        openai_messages = []

        for msg in messages:
            if msg.role == "system":
                openai_messages.append({"role": "system", "content": msg.content})
            elif msg.role == "user":
                if msg.images:
                    # Handle images in OpenAI format
                    content: List[Dict[str, Any]] = [{"type": "text", "text": msg.content or ""}]
                    for img in msg.images:
                        content.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img}",
                                    "detail": kwargs.get("image_detail", "low"),
                                },
                            }
                        )
                    openai_messages.append({"role": "user", "content": content})
                else:
                    openai_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                message = {"role": "assistant", "content": msg.content}
                if msg.tool_calls:
                    message["tool_calls"] = msg.tool_calls
                openai_messages.append(message)
            elif msg.role == "tool":
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                        "name": msg.name,
                    }
                )

        return openai_messages

    def convert_tools(self, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """OpenAI tools are already in the correct format."""
        return tools if tools else None

    def send_request(self, messages: Any, tools: Optional[Any] = None, **kwargs) -> UnifiedResponse:
        """Send request to OpenAI API."""
        api_params = {
            "model": self.model_name,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0),
            "max_tokens": kwargs.get("max_tokens", 16384),
        }

        response_model = kwargs.get("response_model")

        # Use parse API if response_model is provided
        if response_model is not None:
            # Import NOT_GIVEN locally to avoid circular imports
            from openai import NOT_GIVEN

            api_params["response_format"] = response_model
            response = self.client.beta.chat.completions.parse(
                **api_params, tools=tools if tools else NOT_GIVEN
            )
        else:
            if tools:
                api_params["tools"] = tools
                api_params["tool_choice"] = kwargs.get("tool_choice", "auto")
            response = self.client.chat.completions.create(**api_params)

        message = response.choices[0].message

        # Convert tool calls to standard format
        tool_calls = None
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ]

        # Get parsed content if available
        content = message.content
        if hasattr(message, "parsed") and message.parsed:
            content = str(message.parsed)

        return UnifiedResponse(content=content, tool_calls=tool_calls, raw_response=message)


# --- Claude Adapter ---


class ClaudeAdapter(AbstractAPIAdapter):
    """Adapter for Claude API."""

    def __init__(
        self,
        model_name: str,
        client=None,
        thinking_budget: int = 2000,
        memory_file_path: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model_name, **kwargs)
        if client is None:
            import anthropic

            self.client = anthropic.Anthropic()
        else:
            self.client = client
        self.thinking_budget = thinking_budget
        self.memory_file_path = memory_file_path

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_images=True,
            supports_tools=True,
            supports_streaming=True,
            supports_system_messages=True,
            supports_thinking=True,
            max_context_length=200000,
            supports_structured_output=False,
        )

    def convert_messages(
        self, messages: List[UnifiedMessage], **kwargs
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Convert to Claude format. Returns (system_message, messages)."""
        system_message = None
        claude_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            elif msg.role == "user":
                if msg.images:
                    # Handle images in Claude format
                    content = []
                    if msg.content:
                        content.append({"type": "text", "text": msg.content})
                    for img in msg.images:
                        content.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": img,
                                },
                            }
                        )
                    claude_messages.append({"role": "user", "content": content})
                else:
                    claude_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                # Handle assistant messages with thinking blocks
                content = []
                if msg.thinking_content:
                    content.append({"type": "thinking", "thinking": msg.thinking_content})
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["function"]["name"],
                                "input": json.loads(tc["function"]["arguments"]),
                            }
                        )
                claude_messages.append({"role": "assistant", "content": content})
            elif msg.role == "tool":
                claude_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )

        return system_message, claude_messages

    def convert_tools(self, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Convert DIMOS tools to Claude format."""
        if not tools:
            return None

        claude_tools = []
        for tool in tools:
            if tool.get("type") != "function":
                continue

            function = tool.get("function", {})
            claude_tool = {
                "name": function.get("name"),
                "description": function.get("description", ""),
                "input_schema": {
                    "type": "object",
                    "properties": function.get("parameters", {}).get("properties", {}),
                    "required": function.get("parameters", {}).get("required", []),
                },
            }
            claude_tools.append(claude_tool)

        return claude_tools

    def send_request(self, messages: Any, tools: Optional[Any] = None, **kwargs) -> UnifiedResponse:
        """Send request to Claude API with streaming."""
        system_message, claude_messages = messages

        api_params = {
            "model": self.model_name,
            "messages": claude_messages,
            "max_tokens": kwargs.get("max_tokens", 16384),
            "temperature": 0,
        }

        if system_message:
            api_params["system"] = system_message

        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}

        if self.thinking_budget > 0:
            api_params["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
            api_params["temperature"] = 1  # Required for thinking

        # Stream the response
        content = ""
        tool_calls = []
        thinking_blocks = []

        with self.client.messages.stream(**api_params) as stream:
            current_block = {"type": None, "content": ""}

            for event in stream:
                if event.type == "content_block_start":
                    current_block = {"type": event.content_block.type, "content": ""}

                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "thinking"):
                        current_block["content"] = event.delta.thinking
                    elif hasattr(event.delta, "text"):
                        content += event.delta.text

                elif event.type == "content_block_stop":
                    if current_block["type"] == "thinking":
                        thinking_blocks.append(current_block["content"])
                    elif current_block["type"] == "tool_use" and hasattr(event, "content_block"):
                        tool_block = event.content_block
                        tool_calls.append(
                            {
                                "id": tool_block.id,
                                "type": "function",
                                "function": {
                                    "name": tool_block.name,
                                    "arguments": json.dumps(tool_block.input),
                                },
                            }
                        )

        return UnifiedResponse(
            content=content, tool_calls=tool_calls, thinking_blocks=thinking_blocks
        )


# --- Cerebras Adapter ---


class CerebrasAdapter(AbstractAPIAdapter):
    """Adapter for Cerebras API."""

    def __init__(self, model_name: str, client=None, **kwargs):
        super().__init__(model_name, **kwargs)
        if client is None:
            from cerebras.cloud.sdk import Cerebras

            self.client = Cerebras()
        else:
            self.client = client

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_images=False,  # Cerebras is text-only
            supports_tools=True,
            supports_streaming=False,
            supports_system_messages=True,
            supports_thinking=False,
            max_context_length=16000,
            supports_structured_output=True,
        )

    def convert_messages(self, messages: List[UnifiedMessage], **kwargs) -> List[Dict[str, Any]]:
        """Convert to Cerebras format (similar to OpenAI)."""
        cerebras_messages = []

        for msg in messages:
            if msg.role == "system":
                cerebras_messages.append({"role": "system", "content": msg.content})
            elif msg.role == "user":
                # Cerebras doesn't support images, just use text
                cerebras_messages.append({"role": "user", "content": msg.content or ""})
            elif msg.role == "assistant":
                message: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    message["tool_calls"] = msg.tool_calls
                cerebras_messages.append(message)
            elif msg.role == "tool":
                cerebras_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                        "name": msg.name,
                    }
                )

        return cerebras_messages

    def convert_tools(self, tools: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Convert and clean tools for Cerebras."""
        if not tools:
            return None

        # Clean schema for Cerebras
        cleaned_tools = []
        for tool in tools:
            if "function" in tool and "parameters" in tool["function"]:
                cleaned_tool = tool.copy()
                cleaned_tool["function"]["parameters"] = self._clean_schema(
                    tool["function"]["parameters"]
                )
                cleaned_tools.append(cleaned_tool)

        return cleaned_tools

    def _clean_schema(self, schema: dict) -> dict:
        """Remove unsupported fields from schema."""
        if not isinstance(schema, dict):
            return schema

        cleaned = {}
        unsupported = {
            "minItems",
            "maxItems",
            "uniqueItems",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minimum",
            "maximum",
        }

        for key, value in schema.items():
            if key in unsupported:
                continue
            elif isinstance(value, dict):
                cleaned[key] = self._clean_schema(value)
            elif isinstance(value, list):
                cleaned[key] = [
                    self._clean_schema(item) if isinstance(item, dict) else item for item in value
                ]
            else:
                cleaned[key] = value

        return cleaned

    def send_request(self, messages: Any, tools: Optional[Any] = None, **kwargs) -> UnifiedResponse:
        """Send request to Cerebras API."""
        api_params = {"model": self.model_name, "messages": messages}

        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"

        if kwargs.get("response_model"):
            api_params["response_format"] = {
                "type": "json_object",
                "schema": kwargs["response_model"],
            }

        response = self.client.chat.completions.create(**api_params)
        message = response.choices[0].message

        # Convert tool calls if present
        tool_calls = None
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ]

        return UnifiedResponse(content=message.content, tool_calls=tool_calls, raw_response=message)
