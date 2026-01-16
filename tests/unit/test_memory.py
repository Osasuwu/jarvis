"""Tests for ConversationMemory."""

import pytest

from jarvis.memory import ConversationMemory


def test_memory_initialization() -> None:
    """Test memory initializes correctly."""
    memory = ConversationMemory(max_length=10)
    assert memory.max_length == 10
    assert memory.is_empty()
    assert memory.size() == 0


def test_add_message() -> None:
    """Test adding messages to memory."""
    memory = ConversationMemory()
    memory.add_message("user", "Hello")
    
    assert memory.size() == 1
    assert not memory.is_empty()
    
    messages = memory.get_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"


def test_add_multiple_messages() -> None:
    """Test adding multiple messages."""
    memory = ConversationMemory()
    
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi there!")
    memory.add_message("user", "How are you?")
    
    assert memory.size() == 3
    messages = memory.get_messages()
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


def test_max_length_truncation() -> None:
    """Test that old messages are removed when max_length reached."""
    memory = ConversationMemory(max_length=3)
    
    memory.add_message("user", "Message 1")
    memory.add_message("assistant", "Message 2")
    memory.add_message("user", "Message 3")
    assert memory.size() == 3
    
    # Adding 4th message should remove the oldest
    memory.add_message("assistant", "Message 4")
    assert memory.size() == 3
    
    messages = memory.get_messages()
    assert messages[0]["content"] == "Message 2"  # Message 1 removed
    assert messages[-1]["content"] == "Message 4"


def test_get_recent() -> None:
    """Test getting recent messages."""
    memory = ConversationMemory()
    
    memory.add_message("user", "1")
    memory.add_message("assistant", "2")
    memory.add_message("user", "3")
    memory.add_message("assistant", "4")
    
    recent = memory.get_recent(2)
    assert len(recent) == 2
    assert recent[0]["content"] == "3"
    assert recent[1]["content"] == "4"


def test_get_recent_more_than_available() -> None:
    """Test getting recent when requesting more than available."""
    memory = ConversationMemory()
    memory.add_message("user", "1")
    memory.add_message("assistant", "2")
    
    recent = memory.get_recent(10)
    assert len(recent) == 2


def test_clear_memory() -> None:
    """Test clearing memory."""
    memory = ConversationMemory()
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi")
    
    assert memory.size() == 2
    memory.clear()
    assert memory.size() == 0
    assert memory.is_empty()


def test_invalid_role() -> None:
    """Test handling of invalid role."""
    memory = ConversationMemory()
    memory.add_message("invalid_role", "Test")
    
    # Should still add the message (role converted to system)
    assert memory.size() == 1


def test_to_dict() -> None:
    """Test exporting memory to dict."""
    memory = ConversationMemory(max_length=5)
    memory.add_message("user", "Hello")
    memory.add_message("assistant", "Hi")
    
    data = memory.to_dict()
    assert data["max_length"] == 5
    assert data["current_size"] == 2
    assert len(data["messages"]) == 2


def test_from_dict() -> None:
    """Test creating memory from dict."""
    data = {
        "max_length": 5,
        "current_size": 2,
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
    }
    
    memory = ConversationMemory.from_dict(data)
    assert memory.max_length == 5
    assert memory.size() == 2
    assert memory.get_messages()[0]["content"] == "Hello"


def test_memory_repr() -> None:
    """Test string representation."""
    memory = ConversationMemory(max_length=10)
    memory.add_message("user", "Test")
    
    repr_str = repr(memory)
    assert "1/10" in repr_str
    assert "ConversationMemory" in repr_str


def test_memory_len() -> None:
    """Test __len__ operator."""
    memory = ConversationMemory()
    assert len(memory) == 0
    
    memory.add_message("user", "Test")
    assert len(memory) == 1
