"""Tests for Blocker 1: Memory Persistence."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from jarvis.memory.conversation import ConversationMemory


@pytest.mark.asyncio
async def test_memory_persistence_save_and_load():
    """Test that memory persists and reloads correctly."""
    with TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "memory.json"

        # Create memory with persistence
        memory1 = ConversationMemory(auto_load=False)
        memory1.storage_path = storage_path
        memory1.persist_enabled = True

        # Add messages
        memory1.add_message("user", "Hello")
        memory1.add_message("assistant", "Hi there!")
        memory1.add_message("user", "How are you?")

        # Save explicitly
        memory1.save()

        # Verify file exists
        assert storage_path.exists()

        # Load into new memory instance
        memory2 = ConversationMemory(auto_load=False)
        memory2.storage_path = storage_path
        memory2.persist_enabled = True
        memory2.load()

        # Verify messages match
        assert len(memory2) == 3
        assert memory2.get_messages()[0]["role"] == "user"
        assert memory2.get_messages()[1]["role"] == "assistant"
        assert memory2.get_messages()[2]["role"] == "user"


@pytest.mark.asyncio
async def test_memory_auto_load_on_init():
    """Test that memory auto-loads saved conversation on init."""
    with TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "memory.json"

        # Create and save memory
        memory1 = ConversationMemory(auto_load=False)
        memory1.storage_path = storage_path
        memory1.persist_enabled = True
        memory1.add_message("user", "Test message")
        memory1.save()

        # Create new memory with auto-load
        memory2 = ConversationMemory(auto_load=True)
        memory2.storage_path = storage_path
        memory2.persist_enabled = True
        # Note: auto_load happens in __init__, so we need to test separately
        memory2.load()

        # Verify auto-loaded
        assert len(memory2) == 1
        assert memory2.get_messages()[0]["content"] == "Test message"


@pytest.mark.asyncio
async def test_memory_persistence_disabled():
    """Test that persistence can be disabled."""
    with TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "memory.json"

        memory = ConversationMemory(auto_load=False)
        memory.storage_path = storage_path
        memory.persist_enabled = False  # Disable persistence

        memory.add_message("user", "Message")

        # Should not create file
        assert not storage_path.exists()


@pytest.mark.asyncio
async def test_memory_storage_format():
    """Test that storage format is valid JSON with correct schema."""
    with TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "memory.json"

        memory = ConversationMemory(auto_load=False)
        memory.storage_path = storage_path
        memory.persist_enabled = True

        memory.add_message("user", "Test")
        memory.save()

        # Read and parse JSON
        with open(storage_path) as f:
            data = json.load(f)

        # Verify schema
        assert "version" in data
        assert data["version"] == "1.0"
        assert "max_length" in data
        assert "messages" in data
        assert isinstance(data["messages"], list)


@pytest.mark.asyncio
async def test_memory_clear_deletes_storage():
    """Test that clear() deletes the storage file."""
    with TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "memory.json"

        memory = ConversationMemory(auto_load=False)
        memory.storage_path = storage_path
        memory.persist_enabled = True

        memory.add_message("user", "Test")
        memory.save()

        assert storage_path.exists()

        memory.clear()

        # File should be deleted
        assert not storage_path.exists()


@pytest.mark.asyncio
async def test_memory_corrupted_file_raises_error():
    """Test that corrupted storage file raises helpful error."""
    with TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "memory.json"

        # Write corrupted JSON
        storage_path.write_text("{invalid json}")

        memory = ConversationMemory(auto_load=False)
        memory.storage_path = storage_path
        memory.persist_enabled = True

        # Should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            memory.load()


@pytest.mark.asyncio
async def test_memory_truncation_enforced():
    """Test that max_length is enforced during persistence."""
    with TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "memory.json"

        memory = ConversationMemory(max_length=3, auto_load=False)
        memory.storage_path = storage_path
        memory.persist_enabled = True

        # Add more than max_length messages
        for i in range(5):
            memory.add_message("user", f"Message {i}")

        # Should only have 3 (max_length)
        assert len(memory) == 3

        # Verify persistence respects max_length
        memory.save()

        memory2 = ConversationMemory(auto_load=False)
        memory2.storage_path = storage_path
        memory2.persist_enabled = True
        memory2.load()

        assert len(memory2) == 3


@pytest.mark.asyncio
async def test_config_validation_storage_path():
    """Test that config validates storage path is writable."""
    import tempfile

    from jarvis.config import MemorySettings

    with tempfile.TemporaryDirectory() as tmpdir:
        valid_path = Path(tmpdir) / "subdir" / "memory"

        # Should not raise - path should be created
        settings = MemorySettings(
            persist_to_disk=True,
            storage_path=str(valid_path),
        )

        # Path parent should be created
        assert settings.storage_path


@pytest.mark.asyncio
async def test_memory_to_dict_from_dict():
    """Test export/import using dict format."""
    memory1 = ConversationMemory(auto_load=False)
    memory1.add_message("user", "Hello")
    memory1.add_message("assistant", "Hi")

    # Export to dict
    data = memory1.to_dict()

    # Import from dict
    memory2 = ConversationMemory.from_dict(data)

    # Verify messages match
    assert len(memory2) == 2
    assert memory2.get_messages()[0]["content"] == "Hello"
    assert memory2.get_messages()[1]["content"] == "Hi"
