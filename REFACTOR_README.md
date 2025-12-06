# DIMOS Agent System Refactor

This document describes the comprehensive refactor of the DIMOS agent system to create a cleaner, more maintainable architecture with better separation of concerns.

## Overview

The refactor addresses the following issues in the original implementation:

1. **Code Duplication**: Claude and Cerebras agents were overriding many base methods
2. **Poor Abstraction**: Provider-specific logic was mixed with general agent logic
3. **Image Support Issues**: Text-only models like Cerebras would break when called with images
4. **Conversation History Management**: Thread safety issues with concurrent tool calls
5. **Complex Overrides**: Each provider required extensive method overrides

## New Architecture

### Core Components

#### 1. Base Classes (`dimos/agents/base.py`)

- **`BaseAgent`**: Minimal base class for memory and subscription management
- **`BaseLLMAgent`**: Enhanced base class with conversation management and provider abstraction
- **`ConversationManager`**: Thread-safe conversation history management
- **`LLMProvider`**: Abstract interface for LLM providers

#### 2. Provider Implementations (`dimos/agents/providers/`)

- **`OpenAIProvider`**: OpenAI API integration
- **`ClaudeProvider`**: Anthropic Claude API integration  
- **`CerebrasProvider`**: Cerebras API integration

#### 3. Refactored Agents (`dimos/agents/refactored_*.py`)

- **`RefactoredOpenAIAgent`**: Clean OpenAI agent implementation
- **`RefactoredClaudeAgent`**: Clean Claude agent implementation
- **`RefactoredCerebrasAgent`**: Clean Cerebras agent implementation

## Key Improvements

### 1. Clean Separation of Concerns

```python
# Before: Mixed concerns in each agent
class ClaudeAgent(LLMAgent):
    def _send_query(self, messages):  # Claude-specific API logic
    def _build_prompt(self, ...):     # Claude-specific formatting
    def _handle_tooling(self, ...):   # Claude-specific tool handling

# After: Clean separation
class RefactoredClaudeAgent(BaseLLMAgent):
    def __init__(self, ...):
        self.llm_provider = ClaudeProvider(...)  # Delegate to provider
    
    # Only implement agent-specific logic, delegate to provider
```

### 2. Thread-Safe Conversation Management

```python
class ConversationManager:
    def __init__(self):
        self._history: List[Message] = []
        self._lock = threading.Lock()  # Thread-safe operations
    
    def add_message(self, message: Message) -> None:
        with self._lock:  # Prevents race conditions during tool calls
            self._history.append(message)
```

### 3. Automatic Image Support Detection

```python
def run_observable_query(self, query_text: str, base64_image: Optional[str] = None, ...):
    """Automatically handles image support per provider."""
    if base64_image and not self.supports_images():
        logger.warning(f"Agent {self.agent_type} does not support images. Ignoring image input.")
        base64_image = None
        dimensions = None
    
    return self._create_query_observable(query_text, base64_image, dimensions, **kwargs)
```

### 4. Standardized Provider Interface

```python
class LLMProvider(ABC):
    @abstractmethod
    def send_query(self, messages: List[Message], tools: Optional[List[Dict]] = None) -> LLMResponse:
        """Standardized query interface."""
    
    @abstractmethod
    def supports_images(self) -> bool:
        """Declare image support capability."""
    
    @abstractmethod
    def format_messages_for_provider(self, messages: List[Message], ...) -> Any:
        """Provider-specific message formatting."""
```

## Usage Examples

### OpenAI Agent

```python
from dimos.agents.refactored_openai_agent import RefactoredOpenAIAgent

agent = RefactoredOpenAIAgent(
    dev_name="test_agent",
    model_name="gpt-4o",
    skills=my_skill_library
)

# Automatically handles images
response = agent.run_observable_query(
    "What do you see?", 
    base64_image=image_data
).run()
```

### Claude Agent

```python
from dimos.agents.refactored_claude_agent import RefactoredClaudeAgent

agent = RefactoredClaudeAgent(
    dev_name="claude_agent",
    model_name="claude-3-7-sonnet-20250219",
    thinking_budget_tokens=2000
)

# Claude-specific features like thinking blocks
response = agent.run_observable_query("Analyze this image").run()
```

### Cerebras Agent (Text-Only)

```python
from dimos.agents.refactored_cerebras_agent import RefactoredCerebrasAgent

agent = RefactoredCerebrasAgent(
    dev_name="cerebras_agent",
    model_name="llama-4-scout-17b-16e-instruct"
)

# Automatically ignores image inputs
response = agent.run_observable_query(
    "What do you see?", 
    base64_image=image_data  # Will be ignored with warning
).run()
```

## Migration Guide

### From Old Agents to Refactored Agents

1. **Replace imports**:
   ```python
   # Old
   from dimos.agents.claude_agent import ClaudeAgent
   
   # New
   from dimos.agents.refactored_claude_agent import RefactoredClaudeAgent
   ```

2. **Update constructor calls**:
   ```python
   # Old
   agent = ClaudeAgent(
       dev_name="agent",
       # ... many parameters
   )
   
   # New (same parameters, cleaner interface)
   agent = RefactoredClaudeAgent(
       dev_name="agent",
       # ... same parameters
   )
   ```

3. **No changes needed for method calls**:
   ```python
   # Both old and new work the same
   response = agent.run_observable_query("Hello").run()
   ```

### Benefits of Migration

1. **Reduced Code Size**: Each refactored agent is ~50 lines vs 700+ lines
2. **Better Maintainability**: Provider logic is isolated
3. **Automatic Image Handling**: No more crashes with text-only models
4. **Thread Safety**: Conversation history is properly protected
5. **Easier Testing**: Provider logic can be tested independently

## Provider-Specific Features

### OpenAI Provider
- Supports images through GPT-4o
- Standard OpenAI API format
- Tool calling support

### Claude Provider
- Supports images through vision models
- Claude-specific message format
- Thinking blocks support
- Tool calling support

### Cerebras Provider
- Text-only models
- Custom prompt formatting
- Tool calling through text parsing

## Future Extensibility

Adding new providers is now straightforward:

1. **Create provider class**:
   ```python
   class NewProvider(LLMProvider):
       def send_query(self, messages, tools=None):
           # Implement provider-specific logic
           pass
       
       def supports_images(self) -> bool:
           return True  # or False
   ```

2. **Create agent class**:
   ```python
   class RefactoredNewAgent(BaseLLMAgent):
       def __init__(self, ...):
           self.llm_provider = NewProvider(...)
   ```

3. **Done!** All base functionality is inherited.

## Testing

The refactored architecture enables better testing:

```python
# Test provider independently
def test_openai_provider():
    provider = OpenAIProvider()
    response = provider.send_query(messages)
    assert response.content is not None

# Test agent with mocked provider
def test_agent_with_mock_provider():
    agent = RefactoredOpenAIAgent(...)
    agent.llm_provider = MockProvider()
    # Test agent logic without API calls
```

## Conclusion

The refactored architecture provides:

- **Cleaner Code**: Each component has a single responsibility
- **Better Maintainability**: Changes to one provider don't affect others
- **Improved Reliability**: Automatic handling of unsupported features
- **Thread Safety**: Proper conversation history management
- **Easy Extension**: Adding new providers is straightforward

The new system maintains backward compatibility while providing a much cleaner foundation for future development.