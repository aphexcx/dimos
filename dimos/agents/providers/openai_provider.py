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

"""OpenAI provider implementation for the refactored agent system."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI, NOT_GIVEN
from pydantic import BaseModel

from dimos.agents.base import LLMProvider, Message, LLMResponse, ToolCall
from dimos.agents.tokenizer.base import AbstractTokenizer
from dimos.agents.tokenizer.openai_tokenizer import OpenAITokenizer
from dimos.utils.logging_config import setup_logger

logger = setup_logger("dimos.agents.providers.openai")


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        client: Optional[OpenAI] = None,
        tokenizer: Optional[AbstractTokenizer] = None,
        max_tokens: int = 16384,
        temperature: float = 0.7,
    ):
        """
        Initialize the OpenAI provider.

        Args:
            model_name: The OpenAI model to use.
            client: OpenAI client instance.
            tokenizer: Tokenizer for token counting.
            max_tokens: Maximum tokens for response.
            temperature: Temperature for generation.
        """
        self.model_name = model_name
        self.client = client or OpenAI()
        self.tokenizer = tokenizer or OpenAITokenizer(model_name=model_name)
        self.max_tokens = max_tokens
        self.temperature = temperature

    def supports_images(self) -> bool:
        """OpenAI supports images through GPT-4o and other vision models."""
        return "gpt-4o" in self.model_name or "gpt-4-vision" in self.model_name

    def format_messages_for_provider(
        self,
        messages: List[Message],
        base64_image: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Format messages for OpenAI API format."""
        formatted_messages = []

        for message in messages:
            formatted_message = {"role": message.role, "content": message.content}

            # Handle image content
            if base64_image and message.role == "user":
                if self.supports_images():
                    formatted_message["content"] = [
                        {"type": "text", "text": message.content},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "low",
                            },
                        },
                    ]
                # Note: If not supporting images, keep the original text content

            # Handle tool calls
            if message.tool_calls:
                formatted_message["tool_calls"] = [
                    {
                        "id": tc.get("id", ""),
                        "type": tc.get("type", "function"),
                        "function": tc.get("function", {}),
                    }
                    for tc in message.tool_calls
                ]

            # Handle tool call ID
            if message.tool_call_id:
                formatted_message["tool_call_id"] = message.tool_call_id

            formatted_messages.append(formatted_message)

        return formatted_messages

    def format_tools_for_provider(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools for OpenAI API format."""
        return tools

    def send_query(
        self, messages: List[Message], tools: Optional[List[Dict[str, Any]]] = None, **kwargs
    ) -> LLMResponse:
        """Send a query to OpenAI and return a standardized response."""
        try:
            # Format messages for OpenAI
            formatted_messages = self.format_messages_for_provider(messages)

            # Prepare API parameters
            api_params = {
                "model": self.model_name,
                "messages": formatted_messages,
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
            }

            # Add tools if provided
            if tools:
                api_params["tools"] = self.format_tools_for_provider(tools)
                api_params["tool_choice"] = kwargs.get("tool_choice", "auto")

            # Make API call
            response = self.client.chat.completions.create(**api_params)

            # Extract response content
            choice = response.choices[0]
            content = choice.message.content or ""

            # Extract tool calls
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_call = ToolCall(
                        id=tc.id,
                        function={"name": tc.function.name, "arguments": tc.function.arguments},
                        type=tc.type,
                    )
                    tool_calls.append(tool_call)

            # Extract usage information
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return LLMResponse(content=content, tool_calls=tool_calls, usage=usage)

        except Exception as e:
            logger.error(f"Error in OpenAI API call: {e}")
            raise
