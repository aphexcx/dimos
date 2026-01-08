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

"""Refactored Cerebras agent implementation using the new abstraction layer."""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple, Union

from cerebras.cloud.sdk import Cerebras
from pydantic import BaseModel
from reactivex import Observable, Observer, create, operators as RxOps
from reactivex.disposable import Disposable
from reactivex.scheduler import ThreadPoolScheduler

from dimos.agents.base import BaseLLMAgent, Message, LLMResponse
from dimos.agents.memory.base import AbstractAgentSemanticMemory
from dimos.agents.providers.cerebras_provider import CerebrasProvider
from dimos.agents.tokenizer.base import AbstractTokenizer
from dimos.agents.tokenizer.openai_tokenizer import OpenAITokenizer
from dimos.skills.skills import AbstractSkill, SkillLibrary
from dimos.stream.frame_processor import FrameProcessor
from dimos.utils.threadpool import get_scheduler
from dimos.utils.logging_config import setup_logger

logger = setup_logger("dimos.agents.refactored_cerebras")


class RefactoredCerebrasAgent(BaseLLMAgent):
    """Refactored Cerebras agent using the new abstraction layer."""

    def __init__(
        self,
        dev_name: str,
        agent_type: str = "Text",
        query: str = "What can I help you with?",
        input_query_stream: Optional[Observable] = None,
        input_data_stream: Optional[Observable] = None,
        input_video_stream: Optional[Observable] = None,
        output_dir: str = os.path.join(os.getcwd(), "assets", "agent"),
        agent_memory: Optional[AbstractAgentSemanticMemory] = None,
        system_query: Optional[str] = None,
        max_input_tokens_per_request: int = 128000,
        max_output_tokens_per_request: int = 16384,
        model_name: str = "llama-4-scout-17b-16e-instruct",
        skills: Optional[Union[AbstractSkill, list[AbstractSkill], SkillLibrary]] = None,
        response_model: Optional[BaseModel] = None,
        frame_processor: Optional[FrameProcessor] = None,
        image_detail: str = "low",
        pool_scheduler: Optional[ThreadPoolScheduler] = None,
        process_all_inputs: Optional[bool] = None,
        tokenizer: Optional[AbstractTokenizer] = None,
        cerebras_client: Optional[Cerebras] = None,
    ):
        """
        Initialize the refactored Cerebras agent.

        Args:
            dev_name: The device name of the agent.
            agent_type: The type of the agent (Text-only for Cerebras).
            query: The default query text.
            input_query_stream: Stream for text queries.
            input_data_stream: Stream for data input.
            input_video_stream: Stream for video frames (not supported by Cerebras).
            output_dir: Directory for output files.
            agent_memory: The memory system for the agent.
            system_query: System prompt for RAG context situations.
            max_input_tokens_per_request: Maximum input token count.
            max_output_tokens_per_request: Maximum output token count.
            model_name: The Cerebras model name to use.
            skills: Skills available to the agent.
            response_model: Optional Pydantic model for responses.
            frame_processor: Custom frame processor (not used for Cerebras).
            image_detail: Detail level for image processing (not applicable).
            pool_scheduler: The scheduler to use for thread pool operations.
            process_all_inputs: Whether to process all inputs or skip when busy.
            tokenizer: The tokenizer for the agent.
            cerebras_client: Cerebras client instance.
        """
        # Determine appropriate default for process_all_inputs if not provided
        if process_all_inputs is None:
            if input_query_stream is not None and input_video_stream is None:
                process_all_inputs = True
            else:
                process_all_inputs = False

        super().__init__(
            dev_name=dev_name,
            agent_type=agent_type,
            agent_memory=agent_memory,
            pool_scheduler=pool_scheduler,
            process_all_inputs=process_all_inputs,
            system_query=system_query,
            max_output_tokens_per_request=max_output_tokens_per_request,
            max_input_tokens_per_request=max_input_tokens_per_request,
            input_query_stream=input_query_stream,
            input_data_stream=input_data_stream,
            input_video_stream=input_video_stream,
            skills=skills,
            response_model=response_model,
        )

        # Cerebras-specific configuration
        self.query = query
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.model_name = model_name

        # Initialize provider
        self.llm_provider = CerebrasProvider(
            model_name=model_name,
            client=cerebras_client,
            max_tokens=max_output_tokens_per_request,
        )

        # Initialize tokenizer
        self.tokenizer = tokenizer or OpenAITokenizer(
            model_name="gpt-4"
        )  # Use OpenAI tokenizer as fallback

        # Note: Cerebras doesn't support images, so frame_processor is not used
        self.frame_processor = None

        # Ensure only one input stream is provided
        if self.input_video_stream is not None and self.input_query_stream is not None:
            raise ValueError(
                "More than one input stream provided. Please provide only one input stream."
            )

        logger.info("Refactored Cerebras Agent Initialized.")

    def _add_context_to_memory(self):
        """Add initial context to the agent's memory."""
        context_data = [
            (
                "id0",
                "Optical Flow is a technique used to track the movement of objects in a video sequence.",
            ),
            (
                "id1",
                "Computer Vision is a field of artificial intelligence that trains computers to interpret and understand the visual world.",
            ),
        ]

        for doc_id, content in context_data:
            try:
                # Use the appropriate method for adding to memory
                if hasattr(self.agent_memory, "add_vector"):
                    self.agent_memory.add_vector(doc_id, content)
                elif hasattr(self.agent_memory, "add"):
                    self.agent_memory.add(doc_id, content)
            except Exception as memory_error:
                logger.warning(f"Failed to add context {doc_id}: {memory_error}")

    def _create_query_observable(
        self,
        query_text: str,
        base64_image: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None,
        **kwargs,
    ) -> Observable:
        """Create an observable for processing a query."""

        def _observable_query(observer: Observer):
            try:
                # Update query
                self.query = query_text

                # Get RAG context
                rag_results, system_prompt = self._get_rag_context(query_text)

                # Build messages
                messages = self._build_messages(
                    query_text, base64_image, dimensions, rag_results, system_prompt
                )

                # Get tools if available
                tools = None
                if self.skill_library:
                    tools = self.skill_library.get_tools()

                # Send query to provider
                if self.llm_provider is None:
                    raise RuntimeError("LLM provider not initialized")
                response = self.llm_provider.send_query(messages, tools, **kwargs)

                # Add response to conversation history
                assistant_message = Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=[tc.__dict__ for tc in response.tool_calls]
                    if response.tool_calls
                    else None,
                )
                self.conversation_manager.add_message(assistant_message)

                # Handle tool calls if any
                if response.tool_calls:
                    tool_responses = self._handle_tool_calls(response)
                    if tool_responses:
                        self.conversation_manager.add_messages(tool_responses)

                        # Make follow-up call with tool results
                        follow_up_messages = messages + [assistant_message] + tool_responses
                        follow_up_response = self.llm_provider.send_query(
                            follow_up_messages, tools, **kwargs
                        )

                        # Add final response to conversation history
                        final_message = Message(
                            role="assistant", content=follow_up_response.content
                        )
                        self.conversation_manager.add_message(final_message)

                        observer.on_next(final_message.content)
                else:
                    observer.on_next(response.content)

                observer.on_completed()

            except Exception as e:
                logger.error(f"Error in observable query: {e}")
                observer.on_error(e)

        return create(_observable_query)

    def _build_messages(
        self,
        query_text: str,
        base64_image: Optional[str],
        dimensions: Optional[Tuple[int, int]],
        rag_results: str,
        system_prompt: str,
    ) -> list[Message]:
        """Build messages for the LLM provider."""
        messages = []

        # Add system message if provided
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))

        # Add conversation history
        history = self.conversation_manager.get_recent_messages(10)  # Last 10 messages
        messages.extend(history)

        # Build user message
        user_content = query_text
        if rag_results:
            user_content = f"{rag_results}\n\n{query_text}"

        user_message = Message(role="user", content=user_content)
        messages.append(user_message)

        return messages

    def subscribe_to_query_processing(self, query_observable: Observable) -> Disposable:
        """Subscribe to query processing stream."""

        def _process_query(query) -> Observable:
            try:
                return self.run_observable_query(query)
            except Exception as e:
                logger.error(f"Error processing query: {e}")
                return create(lambda obs: obs.on_error(e))

        def process_if_free(query):
            if self.process_all_inputs or not hasattr(self, "_processing"):
                self._processing = True
                return _process_query(query).pipe(
                    RxOps.finalize(lambda: setattr(self, "_processing", False))
                )
            else:
                return create(lambda obs: obs.on_completed())

        subscription = query_observable.pipe(RxOps.flat_map(process_if_free)).subscribe(
            on_next=lambda response: self.response_subject.on_next(response),
            on_error=lambda e: logger.error(f"Error in query processing: {e}"),
            on_completed=lambda: logger.info("Query processing completed"),
        )

        return subscription

    def get_response_observable(self) -> Observable:
        """Get the response observable."""
        return self.response_subject

    def dispose_all(self):
        """Dispose of all resources."""
        super().dispose_all()
        if hasattr(self, "response_subject"):
            self.response_subject.dispose()
