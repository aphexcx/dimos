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

"""Cerebras provider implementation for the refactored agent system."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from cerebras.cloud.sdk import Cerebras

from dimos.agents.base import LLMProvider, Message, LLMResponse, ToolCall
from dimos.utils.logging_config import setup_logger

logger = setup_logger("dimos.agents.providers.cerebras")


class CerebrasProvider(LLMProvider):
    """Cerebras provider implementation."""

    def __init__(
        self,
        model_name: str = "llama-4-scout-17b-16e-instruct",
        client: Optional[Cerebras] = None,
        max_tokens: int = 16384,
        temperature: float = 0.7,
    ):
        """
        Initialize the Cerebras provider.

        Args:
            model_name: The Cerebras model to use.
            client: Cerebras client instance.
            max_tokens: Maximum tokens for response.
            temperature: Temperature for generation.
        """
        self.model_name = model_name
        self.client = client or Cerebras()
        self.max_tokens = max_tokens
        self.temperature = temperature

    def supports_images(self) -> bool:
        """Cerebras models are text-only."""
        return False

    def format_messages_for_provider(
        self,
        messages: List[Message],
        base64_image: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None,
    ) -> str:
        """Format messages for Cerebras API format (text-only)."""
        formatted_prompt = ""

        for message in messages:
            if message.role == "system":
                formatted_prompt += f"<|system|>\n{message.content}\n<|/system|>\n"
            elif message.role == "user":
                formatted_prompt += f"<|user|>\n{message.content}\n<|/user|>\n"
            elif message.role == "assistant":
                formatted_prompt += f"<|assistant|>\n{message.content}\n<|/assistant|>\n"
            elif message.role == "tool":
                formatted_prompt += f"<|tool|>\n{message.content}\n<|/tool|>\n"

        # Add the final assistant prompt
        formatted_prompt += "<|assistant|>\n"

        return formatted_prompt

    def format_tools_for_provider(self, tools: List[Dict[str, Any]]) -> str:
        """Format tools for Cerebras API format (text-only)."""
        if not tools:
            return ""

        tool_descriptions = []
        for tool in tools:
            name = tool["function"]["name"]
            description = tool["function"].get("description", "")
            parameters = tool["function"].get("parameters", {})

            tool_desc = f"Tool: {name}"
            if description:
                tool_desc += f" - {description}"
            if parameters:
                tool_desc += f" (Parameters: {json.dumps(parameters)})"

            tool_descriptions.append(tool_desc)

        return "\n".join(tool_descriptions)

    def send_query(
        self, messages: List[Message], tools: Optional[List[Dict[str, Any]]] = None, **kwargs
    ) -> LLMResponse:
        """Send a query to Cerebras and return a standardized response."""
        try:
            # Format messages for Cerebras
            formatted_prompt = self.format_messages_for_provider(messages)

            # Add tool descriptions if provided
            if tools:
                tool_descriptions = self.format_tools_for_provider(tools)
                if tool_descriptions:
                    formatted_prompt = f"{tool_descriptions}\n\n{formatted_prompt}"

            # Prepare API parameters
            api_params = {
                "model": self.model_name,
                "prompt": formatted_prompt,
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
                "stream": False,  # We'll handle streaming separately if needed
            }

            # Make API call
            response = self.client.complete(**api_params)

            # Extract response content
            content = response.choices[0].text if response.choices else ""

            # Parse tool calls from the response text
            tool_calls = self._parse_tool_calls_from_text(content)

            # Clean up content by removing tool call sections
            content = self._clean_content_from_tool_calls(content)

            return LLMResponse(content=content, tool_calls=tool_calls)

        except Exception as e:
            logger.error(f"Error in Cerebras API call: {e}")
            raise

    def _parse_tool_calls_from_text(self, text: str) -> List[ToolCall]:
        """Parse tool calls from Cerebras text response."""
        tool_calls = []

        # Look for tool call patterns in the text
        # This is a simplified parser - you might need to adjust based on actual Cerebras output format
        tool_pattern = r"<tool_call>(.*?)</tool_call>"
        matches = re.findall(tool_pattern, text, re.DOTALL)

        for i, match in enumerate(matches):
            try:
                # Try to parse as JSON
                tool_data = json.loads(match.strip())
                tool_call = ToolCall(
                    id=f"call_{i}",
                    function={
                        "name": tool_data.get("name", ""),
                        "arguments": json.dumps(tool_data.get("arguments", {})),
                    },
                    type="function",
                )
                tool_calls.append(tool_call)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool call JSON: {match}")
                continue

        return tool_calls

    def _clean_content_from_tool_calls(self, text: str) -> str:
        """Remove tool call sections from the response text."""
        # Remove tool call tags and their content
        cleaned_text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL)
        return cleaned_text.strip()
