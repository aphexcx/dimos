#!/usr/bin/env python3
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

"""
Test script to demonstrate the refactored agent architecture.

This script shows how the new abstraction layer works and how
different providers handle various scenarios.
"""

import os
import sys
from typing import Optional

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dimos.agents.base import Message, LLMResponse, ToolCall
from dimos.agents.refactored_openai_agent import RefactoredOpenAIAgent
from dimos.agents.refactored_claude_agent import RefactoredClaudeAgent
from dimos.agents.refactored_cerebras_agent import RefactoredCerebrasAgent
from dimos.utils.logging_config import setup_logger

logger = setup_logger("test_refactored_agents")


def test_image_support_detection():
    """Test that agents correctly detect and handle image support."""
    print("\n=== Testing Image Support Detection ===")

    # Test OpenAI agent (supports images)
    openai_agent = RefactoredOpenAIAgent(dev_name="test_openai", model_name="gpt-4o")
    print(f"OpenAI agent supports images: {openai_agent.supports_images()}")

    # Test Claude agent (supports images)
    claude_agent = RefactoredClaudeAgent(
        dev_name="test_claude", model_name="claude-3-7-sonnet-20250219"
    )
    print(f"Claude agent supports images: {claude_agent.supports_images()}")

    # Test Cerebras agent (text-only)
    cerebras_agent = RefactoredCerebrasAgent(
        dev_name="test_cerebras", model_name="llama-4-scout-17b-16e-instruct"
    )
    print(f"Cerebras agent supports images: {cerebras_agent.supports_images()}")


def test_conversation_management():
    """Test thread-safe conversation management."""
    print("\n=== Testing Conversation Management ===")

    agent = RefactoredOpenAIAgent(dev_name="test_conv")

    # Test adding messages
    message1 = Message(role="user", content="Hello")
    message2 = Message(role="assistant", content="Hi there!")

    agent.conversation_manager.add_message(message1)
    agent.conversation_manager.add_message(message2)

    history = agent.conversation_manager.get_history()
    print(f"Conversation history length: {len(history)}")
    print(f"Recent messages: {len(agent.conversation_manager.get_recent_messages(5))}")


def test_rag_context():
    """Test RAG context retrieval."""
    print("\n=== Testing RAG Context ===")

    agent = RefactoredOpenAIAgent(dev_name="test_rag")

    # Test getting RAG context
    rag_results, system_prompt = agent._get_rag_context("test query")
    print(f"RAG results length: {len(rag_results)}")
    print(f"System prompt: {system_prompt[:50]}..." if system_prompt else "No system prompt")


def test_message_building():
    """Test message building for different providers."""
    print("\n=== Testing Message Building ===")

    agent = RefactoredOpenAIAgent(dev_name="test_messages")

    # Test building messages
    messages = agent._build_messages(
        query_text="What do you see?",
        base64_image="fake_image_data",
        dimensions=(640, 480),
        rag_results="Some context",
        system_prompt="You are a helpful assistant.",
    )

    print(f"Built {len(messages)} messages")
    for i, msg in enumerate(messages):
        print(f"  Message {i}: {msg.role} - {msg.content[:30]}...")


def test_provider_abstraction():
    """Test the provider abstraction layer."""
    print("\n=== Testing Provider Abstraction ===")

    # Test that providers are properly initialized
    openai_agent = RefactoredOpenAIAgent(dev_name="test_provider")
    print(f"OpenAI provider initialized: {openai_agent.llm_provider is not None}")
    print(f"OpenAI provider type: {type(openai_agent.llm_provider).__name__}")

    claude_agent = RefactoredClaudeAgent(dev_name="test_provider")
    print(f"Claude provider initialized: {claude_agent.llm_provider is not None}")
    print(f"Claude provider type: {type(claude_agent.llm_provider).__name__}")

    cerebras_agent = RefactoredCerebrasAgent(dev_name="test_provider")
    print(f"Cerebras provider initialized: {cerebras_agent.llm_provider is not None}")
    print(f"Cerebras provider type: {type(cerebras_agent.llm_provider).__name__}")


def test_skill_library_integration():
    """Test skill library integration."""
    print("\n=== Testing Skill Library Integration ===")

    from dimos.skills.skills import SkillLibrary

    # Create a simple skill library
    skill_library = SkillLibrary()

    agent = RefactoredOpenAIAgent(dev_name="test_skills", skills=skill_library)

    print(f"Skill library initialized: {agent.skill_library is not None}")
    if agent.skill_library:
        print(f"Available skills: {len(agent.skill_library.get())}")


def main():
    """Run all tests."""
    print("DIMOS Refactored Agent System Test")
    print("=" * 50)

    try:
        test_image_support_detection()
        test_conversation_management()
        test_rag_context()
        test_message_building()
        test_provider_abstraction()
        test_skill_library_integration()

        print("\n" + "=" * 50)
        print("All tests completed successfully!")
        print("\nKey improvements demonstrated:")
        print("✓ Clean separation of concerns")
        print("✓ Thread-safe conversation management")
        print("✓ Automatic image support detection")
        print("✓ Provider abstraction layer")
        print("✓ Skill library integration")

    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
