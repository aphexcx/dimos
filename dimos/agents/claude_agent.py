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

"""Claude agent implementation for the DIMOS agent framework.

This module provides a ClaudeAgent class that implements the LLMAgent interface
for Anthropic's Claude models.
"""

from __future__ import annotations

import os
from typing import Optional, Union

from pydantic import BaseModel
from reactivex import Observable
from reactivex.scheduler import ThreadPoolScheduler

# Local imports
from dimos.agents.agent import LLMAgent
from dimos.agents.memory.base import AbstractAgentSemanticMemory
from dimos.agents.api_adapters import ClaudeAdapter
from dimos.skills.skills import AbstractSkill, SkillLibrary
from dimos.stream.frame_processor import FrameProcessor
from dimos.utils.logging_config import setup_logger

# Initialize logger for the Claude agent
logger = setup_logger("dimos.agents.claude")


class ClaudeAgent(LLMAgent):
    """Claude agent implementation using the Claude API adapter."""

    def __init__(
        self,
        dev_name: str,
        agent_type: str = "Vision",
        query: str = "What do you see?",
        input_query_stream: Optional[Observable] = None,
        input_video_stream: Optional[Observable] = None,
        input_data_stream: Optional[Observable] = None,
        output_dir: str = os.path.join(os.getcwd(), "assets", "agent"),
        agent_memory: Optional[AbstractAgentSemanticMemory] = None,
        system_query: Optional[str] = None,
        max_input_tokens_per_request: int = 128000,
        max_output_tokens_per_request: int = 16384,
        model_name: str = "claude-3-5-sonnet-20241022",
        rag_query_n: int = 4,
        rag_similarity_threshold: float = 0.45,
        skills: Optional[Union[AbstractSkill, list[AbstractSkill], SkillLibrary]] = None,
        response_model: Optional[BaseModel] = None,
        frame_processor: Optional[FrameProcessor] = None,
        image_detail: str = "low",
        pool_scheduler: Optional[ThreadPoolScheduler] = None,
        process_all_inputs: Optional[bool] = None,
        thinking_budget_tokens: Optional[int] = 2000,
        anthropic_client=None,
    ):
        # Determine appropriate default for process_all_inputs if not provided
        if process_all_inputs is None:
            process_all_inputs = (
                True if input_query_stream is not None and input_video_stream is None else False
            )

        # Create Claude adapter
        api_adapter = ClaudeAdapter(
            model_name=model_name,
            client=anthropic_client,
            thinking_budget=thinking_budget_tokens or 0,
        )

        super().__init__(
            dev_name=dev_name,
            agent_type=agent_type,
            agent_memory=agent_memory,
            pool_scheduler=pool_scheduler,
            process_all_inputs=process_all_inputs,
            system_query=system_query,
            input_query_stream=input_query_stream,
            input_video_stream=input_video_stream,
            input_data_stream=input_data_stream,
            api_adapter=api_adapter,
            max_output_tokens_per_request=max_output_tokens_per_request,
            max_input_tokens_per_request=max_input_tokens_per_request,
        )

        self.query = query
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Configure skills
        self.skills = skills
        if isinstance(self.skills, SkillLibrary):
            self.skill_library = self.skills
        elif isinstance(self.skills, list):
            self.skill_library = SkillLibrary()
            for skill in self.skills:
                self.skill_library.add(skill)
        elif isinstance(self.skills, AbstractSkill):
            self.skill_library = SkillLibrary()
            self.skill_library.add(self.skills)

        self.response_model = response_model
        self.model_name = model_name
        self.rag_query_n = rag_query_n
        self.rag_similarity_threshold = rag_similarity_threshold
        self.image_detail = image_detail
        self.frame_processor = frame_processor or FrameProcessor(delete_on_init=True)

        # Add static context to memory
        self._add_context_to_memory()

        # Ensure only one input stream is provided
        if self.input_video_stream is not None and self.input_query_stream is not None:
            raise ValueError(
                "More than one input stream provided. Please provide only one input stream."
            )

        logger.info("Claude Agent Initialized.")

    def _add_context_to_memory(self):
        """Adds initial context to the agent's memory."""
        context_data = [
            (
                "id0",
                "Optical Flow is a technique used to track the movement of objects in a video sequence.",
            ),
            (
                "id1",
                "Edge Detection is a technique used to identify the boundaries of objects in an image.",
            ),
            ("id2", "Video is a sequence of frames captured at regular intervals."),
            (
                "id3",
                "Colors in Optical Flow are determined by the movement of light, and can be used to track the movement of objects.",
            ),
            (
                "id4",
                "Json is a data interchange format that is easy for humans to read and write, and easy for machines to parse and generate.",
            ),
        ]
        for doc_id, text in context_data:
            self.agent_memory.add_vector(doc_id, text)
