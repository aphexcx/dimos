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

"""Claude provider implementation for the refactored agent system."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from dimos.agents.base import LLMProvider, Message, LLMResponse, ToolCall
from dimos.utils.logging_config import setup_logger

logger = setup_logger("dimos.agents.providers.claude")


class ClaudeProvider(LLMProvider):
    """Claude provider implementation."""

    def __init__(
        self,
        model_name: str = "claude-3-7-sonnet-20250219",
        client: Optional[anthropic.Anthropic] = None,
        max_tokens: int = 16384,
        temperature: float = 0.7,
        thinking_budget_tokens: Optional[int] = 2000,
    ):
        """
        Initialize the Claude provider.

        Args:
            model_name: The Claude model to use.
            client: Anthropic client instance.
            max_tokens: Maximum tokens for response.
            temperature: Temperature for generation.
            thinking_budget_tokens: Tokens allocated for Claude's thinking.
        """
        self.model_name = model_name
        self.client = client or anthropic.Anthropic()
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking_budget_tokens = thinking_budget_tokens

    def supports_images(self) -> bool:
        """Claude supports images through vision models."""
        return (
            "haiku" in self.model_name or "sonnet" in self.model_name or "opus" in self.model_name
        )

    def format_messages_for_provider(
        self,
        messages: List[Message],
        base64_image: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Format messages for Claude API format."""
        formatted_messages = []

        for message in messages:
            if message.role == "system":
                # Claude doesn't support system messages in the same way
                # We'll prepend system content to the first user message
                continue

            formatted_message = {"role": message.role}

            # Handle content
            if message.role == "user":
                content_parts = []

                # Add text content
                if message.content:
                    content_parts.append({"type": "text", "text": message.content})

                # Add image content
                if base64_image and self.supports_images():
                    content_parts.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        }
                    )

                formatted_message["content"] = content_parts
            else:
                # For assistant and tool messages, content is just text
                formatted_message["content"] = message.content

            # Handle tool call ID for tool messages
            if message.tool_call_id:
                formatted_message["tool_call_id"] = message.tool_call_id

            formatted_messages.append(formatted_message)

        return formatted_messages

    def format_tools_for_provider(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools for Claude API format."""
        claude_tools = []

        for tool in tools:
            claude_tool = {
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "input_schema": tool["function"]["parameters"],
            }
            claude_tools.append(claude_tool)

        return claude_tools

    def send_query(
        self, messages: List[Message], tools: Optional[List[Dict[str, Any]]] = None, **kwargs
    ) -> LLMResponse:
        """Send a query to Claude and return a standardized response."""
        try:
            # Format messages for Claude
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

            # Add thinking budget if specified
            if self.thinking_budget_tokens and self.thinking_budget_tokens > 0:
                api_params["thinking_budget_tokens"] = self.thinking_budget_tokens

            # Make API call
            response = self.client.messages.create(**api_params)

            # Extract response content
            content = ""
            if response.content:
                # Claude can return multiple content blocks
                text_blocks = [block.text for block in response.content if block.type == "text"]
                content = "\n".join(text_blocks)

            # Extract tool calls
            tool_calls = []
            if response.content:
                for block in response.content:
                    if block.type == "tool_use":
                        tool_call = ToolCall(
                            id=block.id,
                            function={"name": block.name, "arguments": json.dumps(block.input)},
                            type="function",
                        )
                        tool_calls.append(tool_call)

            # Extract thinking blocks
            thinking_blocks = []
            if response.content:
                thinking_blocks = [
                    block.text for block in response.content if block.type == "thinking"
                ]

            # Extract usage information
            usage = None
            if response.usage:
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }

            return LLMResponse(
                content=content, tool_calls=tool_calls, thinking_blocks=thinking_blocks, usage=usage
            )

        except Exception as e:
            logger.error(f"Error in Claude API call: {e}")
            raise
