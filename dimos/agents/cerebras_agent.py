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

"""Cerebras agent implementation for the DIMOS agent framework.

This module provides a CerebrasAgent class that implements the LLMAgent interface
for Cerebras inference API.
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
from dimos.agents.api_adapters import CerebrasAdapter
from dimos.skills.skills import AbstractSkill, SkillLibrary
from dimos.stream.frame_processor import FrameProcessor
from dimos.utils.logging_config import setup_logger

# Initialize logger for the Cerebras agent
logger = setup_logger("dimos.agents.cerebras")


class CerebrasAgent(LLMAgent):
    """Cerebras agent implementation using the Cerebras API adapter."""

    def __init__(
        self,
        dev_name: str,
        agent_type: str = "Text",  # Cerebras is text-only
        query: str = "What is your question?",
        input_query_stream: Optional[Observable] = None,
        input_video_stream: Optional[Observable] = None,
        input_data_stream: Optional[Observable] = None,
        output_dir: str = os.path.join(os.getcwd(), "assets", "agent"),
        agent_memory: Optional[AbstractAgentSemanticMemory] = None,
        system_query: Optional[str] = None,
        max_input_tokens_per_request: int = 16000,
        max_output_tokens_per_request: int = 16384,
        model_name: str = "llama3.1-8b",
        skills: Optional[Union[AbstractSkill, list[AbstractSkill], SkillLibrary]] = None,
        response_model: Optional[BaseModel] = None,
        frame_processor: Optional[FrameProcessor] = None,
        image_detail: str = "low",
        pool_scheduler: Optional[ThreadPoolScheduler] = None,
        process_all_inputs: Optional[bool] = None,
        cerebras_client=None,
    ):
        # Determine appropriate default for process_all_inputs if not provided
        if process_all_inputs is None:
            process_all_inputs = (
                True if input_query_stream is not None and input_video_stream is None else False
            )

        # Create Cerebras adapter
        api_adapter = CerebrasAdapter(model_name=model_name, client=cerebras_client)

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
        self.image_detail = image_detail

        # Add static context to memory
        self._add_context_to_memory()

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
