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

"""Base classes and interfaces for the refactored agent system.

This module provides the core abstractions that enable clean separation between
different LLM providers while maintaining a unified interface for agents.
"""

from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union, Protocol
from dataclasses import dataclass

from pydantic import BaseModel
from reactivex import Observable, Subject
from reactivex.scheduler import ThreadPoolScheduler

from dimos.agents.memory.base import AbstractAgentSemanticMemory
from dimos.agents.memory.chroma_impl import OpenAISemanticMemory
from dimos.skills.skills import AbstractSkill, SkillLibrary
from dimos.utils.threadpool import get_scheduler
from dimos.utils.logging_config import setup_logger

logger = setup_logger("dimos.agents.base")


@dataclass
class Message:
    """Represents a message in a conversation."""

    role: str
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolCall:
    """Represents a tool/function call."""

    id: str
    function: Dict[str, Any]
    type: str = "function"


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    tool_calls: List[ToolCall]
    thinking_blocks: Optional[List[str]] = None
    usage: Optional[Dict[str, int]] = None


class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    This interface defines the contract that all LLM providers must implement,
    allowing for clean abstraction and easy addition of new providers.
    """

    @abstractmethod
    def send_query(
        self, messages: List[Message], tools: Optional[List[Dict[str, Any]]] = None, **kwargs
    ) -> LLMResponse:
        """Send a query to the LLM and return a standardized response."""
        pass

    @abstractmethod
    def supports_images(self) -> bool:
        """Return whether this provider supports image inputs."""
        pass

    @abstractmethod
    def format_messages_for_provider(
        self,
        messages: List[Message],
        base64_image: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None,
    ) -> Any:
        """Format messages for the specific provider's API format."""
        pass

    @abstractmethod
    def format_tools_for_provider(self, tools: List[Dict[str, Any]]) -> Any:
        """Format tools for the specific provider's API format."""
        pass


class ConversationManager:
    """Manages conversation history with thread-safe operations."""

    def __init__(self):
        self._history: List[Message] = []
        self._lock = threading.Lock()

    def add_message(self, message: Message) -> None:
        """Add a message to the conversation history."""
        with self._lock:
            self._history.append(message)

    def add_messages(self, messages: List[Message]) -> None:
        """Add multiple messages to the conversation history."""
        with self._lock:
            self._history.extend(messages)

    def get_history(self) -> List[Message]:
        """Get a copy of the conversation history."""
        with self._lock:
            return self._history.copy()

    def clear_history(self) -> None:
        """Clear the conversation history."""
        with self._lock:
            self._history.clear()

    def get_recent_messages(self, count: int) -> List[Message]:
        """Get the most recent messages from the history."""
        with self._lock:
            return self._history[-count:] if self._history else []

    def __len__(self) -> int:
        with self._lock:
            return len(self._history)


class BaseAgent:
    """Base agent that manages memory and subscriptions."""

    def __init__(
        self,
        dev_name: str = "NA",
        agent_type: str = "Base",
        agent_memory: Optional[AbstractAgentSemanticMemory] = None,
        pool_scheduler: Optional[ThreadPoolScheduler] = None,
    ):
        """
        Initializes a new instance of the BaseAgent.

        Args:
            dev_name (str): The device name of the agent.
            agent_type (str): The type of the agent (e.g., 'Base', 'Vision').
            agent_memory (AbstractAgentSemanticMemory): The memory system for the agent.
            pool_scheduler (ThreadPoolScheduler): The scheduler to use for thread pool operations.
                If None, the global scheduler from get_scheduler() will be used.
        """
        self.dev_name = dev_name
        self.agent_type = agent_type
        self.agent_memory = agent_memory or OpenAISemanticMemory()
        self.pool_scheduler = pool_scheduler if pool_scheduler else get_scheduler()


class BaseLLMAgent(BaseAgent):
    """Base LLM agent with improved abstraction and conversation management.

    This class provides the core functionality for LLM-based agents while
    delegating provider-specific operations to LLMProvider implementations.
    """

    def __init__(
        self,
        dev_name: str = "NA",
        agent_type: str = "LLM",
        agent_memory: Optional[AbstractAgentSemanticMemory] = None,
        pool_scheduler: Optional[ThreadPoolScheduler] = None,
        process_all_inputs: bool = False,
        system_query: Optional[str] = None,
        max_output_tokens_per_request: int = 16384,
        max_input_tokens_per_request: int = 128000,
        input_query_stream: Optional[Observable] = None,
        input_data_stream: Optional[Observable] = None,
        input_video_stream: Optional[Observable] = None,
        skills: Optional[Union[AbstractSkill, List[AbstractSkill], SkillLibrary]] = None,
        response_model: Optional[BaseModel] = None,
    ):
        """
        Initializes a new instance of the BaseLLMAgent.

        Args:
            dev_name (str): The device name of the agent.
            agent_type (str): The type of the agent.
            agent_memory (AbstractAgentSemanticMemory): The memory system for the agent.
            pool_scheduler (ThreadPoolScheduler): The scheduler to use for thread pool operations.
            process_all_inputs (bool): Whether to process every input emission.
            system_query (str): System prompt for RAG context situations.
            max_output_tokens_per_request (int): Maximum output token count.
            max_input_tokens_per_request (int): Maximum input token count.
            input_query_stream (Observable): Stream for text queries.
            input_data_stream (Observable): Stream for data input.
            input_video_stream (Observable): Stream for video frames.
            skills: Skills available to the agent.
            response_model (BaseModel): Optional Pydantic model for responses.
        """
        super().__init__(dev_name, agent_type, agent_memory, pool_scheduler)

        # Core configuration
        self.system_query = system_query
        self.max_input_tokens_per_request = max_input_tokens_per_request
        self.max_output_tokens_per_request = max_output_tokens_per_request
        self.max_tokens_per_request = max_input_tokens_per_request + max_output_tokens_per_request
        self.process_all_inputs = process_all_inputs

        # Conversation management
        self.conversation_manager = ConversationManager()

        # Skills configuration
        self.skills = skills
        self.skill_library = self._setup_skill_library(skills)

        # Response model
        self.response_model = response_model

        # Stream configuration
        self.input_video_stream = input_video_stream
        self.input_query_stream = input_query_stream
        self.input_data_stream = input_data_stream

        # Response subject
        self.response_subject = Subject()

        # RAG configuration
        self.rag_query_n = 4
        self.rag_similarity_threshold = 0.45

        # Output directory
        self.output_dir = os.path.join(os.getcwd(), "assets", "agent")
        os.makedirs(self.output_dir, exist_ok=True)

        # Provider-specific attributes (to be set by subclasses)
        self.llm_provider: Optional[LLMProvider] = None

        # Add initial context to memory
        self._add_context_to_memory()

    def _setup_skill_library(self, skills) -> Optional[SkillLibrary]:
        """Setup the skill library from various input formats."""
        if isinstance(skills, SkillLibrary):
            return skills
        elif isinstance(skills, list):
            skill_library = SkillLibrary()
            for skill in skills:
                skill_library.add(skill)
            return skill_library
        elif isinstance(skills, AbstractSkill):
            skill_library = SkillLibrary()
            skill_library.add(skills)
            return skill_library
        return None

    def _add_context_to_memory(self):
        """Add initial context to the agent's memory."""
        # This can be overridden by subclasses to add provider-specific context
        pass

    def supports_images(self) -> bool:
        """Check if the current LLM provider supports images."""
        return self.llm_provider.supports_images() if self.llm_provider else False

    def run_observable_query(
        self,
        query_text: str,
        base64_image: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None,
        **kwargs,
    ) -> Observable:
        """Run a query and return an observable stream of responses.

        This method handles the case where the LLM provider doesn't support images
        by filtering out image-related parameters.
        """
        if base64_image and not self.supports_images():
            logger.warning(
                f"Agent {self.agent_type} does not support images. Ignoring image input."
            )
            base64_image = None
            dimensions = None

        return self._create_query_observable(query_text, base64_image, dimensions, **kwargs)

    def _create_query_observable(
        self,
        query_text: str,
        base64_image: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None,
        **kwargs,
    ) -> Observable:
        """Create an observable for processing a query."""
        # This will be implemented by subclasses to handle the specific query flow
        raise NotImplementedError("Subclasses must implement _create_query_observable")

    def _get_rag_context(self, query: str) -> Tuple[str, str]:
        """Get RAG context from memory."""
        if not query:
            return "", ""

        try:
            results = self.agent_memory.query(
                query,
                n_results=self.rag_query_n,
                similarity_threshold=self.rag_similarity_threshold,
            )

            if results:
                condensed_results = "\n".join([result.content for result in results])
                return condensed_results, self.system_query or ""
            else:
                return "", self.system_query or ""
        except Exception as e:
            logger.error(f"Error getting RAG context: {e}")
            return "", self.system_query or ""

    def _handle_tool_calls(self, response: LLMResponse) -> List[Message]:
        """Handle tool calls in the response and return tool response messages."""
        if not response.tool_calls or not self.skill_library:
            return []

        tool_response_messages = []

        for tool_call in response.tool_calls:
            try:
                # Execute the tool
                function_name = tool_call.function.get("name", "")
                function_args = tool_call.function.get("arguments", "{}")
                result = self.skill_library.call(function_name, **json.loads(function_args))

                # Create tool response message
                tool_response = Message(role="tool", content=str(result), tool_call_id=tool_call.id)
                tool_response_messages.append(tool_response)

            except Exception as e:
                logger.error(
                    f"Error executing tool {tool_call.function.get('name', 'unknown')}: {e}"
                )
                error_response = Message(
                    role="tool",
                    content=f"Error executing tool: {str(e)}",
                    tool_call_id=tool_call.id,
                )
                tool_response_messages.append(error_response)

        return tool_response_messages
