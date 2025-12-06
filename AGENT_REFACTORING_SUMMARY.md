# Agent Architecture Refactoring Summary

## Overview

The agent architecture has been refactored to create a cleaner abstraction layer that separates provider-specific logic from the core agent functionality. This reduces code duplication and makes it easier to add new LLM providers.

## Key Components

### 1. API Adapters (`dimos/agents/api_adapters.py`)

The new API adapter pattern provides:

- **`AbstractAPIAdapter`**: Base class defining the interface all adapters must implement
- **`AgentCapabilities`**: Dataclass defining what features a model/API supports (images, tools, streaming, etc.)
- **`UnifiedMessage`**: Common message format used internally
- **`UnifiedResponse`**: Common response format from all providers

Provider-specific adapters:
- **`OpenAIAdapter`**: Handles OpenAI API specifics including structured outputs
- **`ClaudeAdapter`**: Handles Claude API specifics including thinking blocks and streaming
- **`CerebrasAdapter`**: Handles Cerebras API specifics including schema cleaning for tools

### 2. Refactored Base LLMAgent (`dimos/agents/agent.py`)

The base `LLMAgent` class now includes:

- **Global conversation history** with thread-safe access via `_history_lock`
- **Capability checking** to handle models that don't support certain features (e.g., images)
- **Unified message handling** using the `UnifiedMessage` format
- **API adapter integration** - all provider-specific logic delegated to adapters

Key methods:
- `get_capabilities()`: Returns model capabilities from the adapter
- `_add_to_conversation_history()`: Thread-safe method to add messages
- `reset_conversation_history()`: Clear conversation history
- `_build_prompt()`: Creates messages in unified format
- `_send_query()`: Delegates to API adapter for provider-specific handling

### 3. Simplified Agent Implementations

Each agent implementation is now minimal (~130 lines):

**OpenAIAgent** (`dimos/agents/agent.py`):
```python
class OpenAIAgent(LLMAgent):
    def __init__(self, ...):
        # Create OpenAI adapter
        api_adapter = OpenAIAdapter(model_name=model_name, client=openai_client)
        super().__init__(..., api_adapter=api_adapter)
        # Configure agent-specific settings
```

**ClaudeAgent** (`dimos/agents/claude_agent.py`):
```python
class ClaudeAgent(LLMAgent):
    def __init__(self, ...):
        # Create Claude adapter with thinking support
        api_adapter = ClaudeAdapter(
            model_name=model_name, 
            client=anthropic_client,
            thinking_budget=thinking_budget_tokens or 0
        )
        super().__init__(..., api_adapter=api_adapter)
```

**CerebrasAgent** (`dimos/agents/cerebras_agent.py`):
```python
class CerebrasAgent(LLMAgent):
    def __init__(self, ...):
        # Create Cerebras adapter (text-only)
        api_adapter = CerebrasAdapter(model_name=model_name, client=cerebras_client)
        super().__init__(..., api_adapter=api_adapter)
```

## Key Improvements

### 1. Separation of Concerns
- Provider-specific logic is isolated in adapters
- Agents focus only on configuration and initialization
- Base class handles all common functionality

### 2. Capability-Based Feature Handling
- Models that don't support images (like Cerebras) are handled gracefully
- The system checks capabilities before attempting operations
- No more crashes when calling image methods on text-only models

### 3. Unified Conversation History
- Single implementation in base class with thread safety
- No more duplicate implementations in each agent
- Consistent behavior across all providers

### 4. Tool/Function Calling Abstraction
- Each adapter converts tools to its required format
- Unified response format for tool calls
- Base class handles tool execution and follow-up queries

### 5. Reduced Code Duplication
- Claude and Cerebras agents reduced from 600-700 lines to ~130 lines
- All common logic moved to base class
- Provider differences handled by adapters

## Migration Guide

For existing code using the agents:

1. **No API changes** - The public interface remains the same
2. **New features available**:
   - `reset_conversation_history()` method on all agents
   - Capability checking via `get_capabilities()`
   - Better handling of unsupported features

3. **Adding new providers**:
   - Create a new adapter class extending `AbstractAPIAdapter`
   - Implement the required methods
   - Create a minimal agent class that uses the adapter

## Example Usage

```python
# Create agents as before
claude_agent = ClaudeAgent(
    dev_name="claude",
    model_name="claude-3-5-sonnet-20241022",
    thinking_budget_tokens=2000
)

# Use new features
capabilities = claude_agent.get_capabilities()
if capabilities.supports_images:
    # Process images
    pass

# Reset conversation when needed
claude_agent.reset_conversation_history()

# Everything else works the same
response = claude_agent.run_observable_query("Hello!").run()
```

## Technical Benefits

1. **Maintainability**: Changes to provider APIs only require updating the adapter
2. **Testability**: Adapters can be mocked for testing
3. **Extensibility**: New providers can be added with minimal code
4. **Type Safety**: Unified types provide better IDE support and catch errors earlier
5. **Performance**: Thread-safe conversation history prevents race conditions