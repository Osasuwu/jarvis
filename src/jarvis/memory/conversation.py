"""Memory management for conversation history with persistent storage."""

import json
import logging
from collections import deque
from datetime import UTC
from pathlib import Path
from typing import Any

from jarvis.config import get_config

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Manages conversation history with automatic truncation and persistent storage.

    Storage:
    - In-memory: Deque for fast access with automatic truncation
    - Persistent: JSON file for durability across sessions
    - Load: Automatically loads saved conversation on initialization (optional)

    Storage schema (JSON):
    {
        "version": "1.0",
        "max_length": 50,
        "created_at": "2026-01-17T...",
        "updated_at": "2026-01-17T...",
        "messages": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]
    }
    """

    def __init__(self, max_length: int | None = None, auto_load: bool = True):
        """
        Initialize conversation memory.

        Args:
            max_length: Maximum number of messages to keep (defaults to config)
            auto_load: Automatically load saved conversation on init (default: True)

        Raises:
            OSError: If storage path is not writable (when persistence enabled)
        """
        config = get_config()
        self.max_length = max_length or config.memory.max_conversation_length
        self._messages: deque[dict[str, str]] = deque(maxlen=self.max_length)

        # Persistence configuration
        self.persist_enabled = config.memory.persist_to_disk
        self.storage_path = Path(config.memory.storage_path)

        logger.info(
            f"ConversationMemory initialized (max_length={self.max_length}, "
            f"persistence={self.persist_enabled})"
        )

        # Validate storage path is writable if persistence enabled
        if self.persist_enabled:
            self._validate_storage_path()

            # Attempt to load saved conversation
            if auto_load:
                try:
                    self.load()
                    logger.info(f"Loaded {len(self._messages)} messages from persistent storage")
                except FileNotFoundError:
                    logger.debug("No saved conversation found; starting fresh")
                except Exception as e:
                    logger.warning(f"Failed to load saved conversation: {e}")

    def _validate_storage_path(self) -> None:
        """
        Validate that storage path is writable.

        Raises:
            OSError: If path is not writable
        """
        try:
            # Ensure parent directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if directory is writable
            if self.storage_path.parent.exists():
                # Try to create a test file
                test_file = self.storage_path.parent / ".write_test"
                test_file.touch()
                test_file.unlink()
            else:
                raise OSError(f"Cannot create storage directory: {self.storage_path.parent}")

        except (PermissionError, OSError) as e:
            error_msg = (
                f"Storage path '{self.storage_path.parent}' is not writable: {e}\n"
                "Configuration error: persist_to_disk=True but storage path not writable"
            )
            logger.error(error_msg)
            raise OSError(error_msg) from e

    def add_message(self, role: str, content: str) -> None:
        """
        Add a message to memory and optionally persist.

        Args:
            role: Message role ('user', 'assistant', 'system', 'tool')
            content: Message content
        """
        if role not in ["user", "assistant", "system", "tool"]:
            logger.warning(f"Unknown role '{role}', using 'system' instead")
            role = "system"

        message = {"role": role, "content": content}
        self._messages.append(message)

        logger.debug(f"Added {role} message ({len(content)} chars)")

        # Warn if approaching limit
        if len(self._messages) >= self.max_length * 0.9:
            logger.warning(f"Memory nearing limit: {len(self._messages)}/{self.max_length}")

        # Persist after each message if enabled
        if self.persist_enabled:
            try:
                self.save()
            except Exception as e:
                logger.error(f"Failed to persist message: {e}")

    def get_messages(self) -> list[dict[str, str]]:
        """
        Get all messages in chronological order.

        Returns:
            List of message dicts
        """
        return list(self._messages)

    def get_recent(self, count: int) -> list[dict[str, str]]:
        """
        Get N most recent messages.

        Args:
            count: Number of recent messages

        Returns:
            List of recent messages
        """
        messages = list(self._messages)
        return messages[-count:] if count < len(messages) else messages

    def clear(self) -> None:
        """
        Clear all messages from memory and delete persistent storage.
        """
        message_count = len(self._messages)
        self._messages.clear()
        logger.info(f"Memory cleared ({message_count} messages removed)")

        # Delete persisted file if exists
        if self.persist_enabled and self.storage_path.exists():
            try:
                self.storage_path.unlink()
                logger.debug(f"Deleted persistent storage file: {self.storage_path}")
            except OSError as e:
                logger.warning(f"Failed to delete persistent storage: {e}")

    def save(self) -> None:
        """
        Save conversation to persistent storage (JSON format).

        The storage file is human-readable and includes metadata.

        Raises:
            OSError: If write to storage path fails
        """
        if not self.persist_enabled:
            return

        try:
            from datetime import datetime

            data = {
                "version": "1.0",
                "max_length": self.max_length,
                "created_at": datetime.now(UTC).isoformat(),
                "messages": list(self._messages),
            }

            # Ensure parent directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Write with pretty formatting for readability
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved {len(self._messages)} messages to {self.storage_path}")

        except OSError as e:
            error_msg = f"Failed to save conversation to {self.storage_path}: {e}"
            logger.error(error_msg)
            raise OSError(error_msg) from e

    def load(self) -> None:
        """
        Load conversation from persistent storage (JSON format).

        Clears existing messages and loads from file. If file doesn't exist,
        no error is raised (safe for initialization).

        Raises:
            FileNotFoundError: If storage file doesn't exist
            json.JSONDecodeError: If storage file is corrupted
            ValueError: If storage format version is incompatible
        """
        if not self.persist_enabled:
            return

        if not self.storage_path.exists():
            logger.debug(f"Persistent storage file not found: {self.storage_path}")
            raise FileNotFoundError(f"Storage file not found: {self.storage_path}")

        try:
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)

            # Validate format version
            version = data.get("version", "1.0")
            if version != "1.0":
                raise ValueError(f"Unsupported storage format version: {version}")

            # Clear existing messages
            self._messages.clear()

            # Load messages
            for msg in data.get("messages", []):
                if "role" in msg and "content" in msg:
                    self._messages.append(
                        {
                            "role": msg["role"],
                            "content": msg["content"],
                        }
                    )

            logger.info(f"Loaded {len(self._messages)} messages from {self.storage_path}")

        except json.JSONDecodeError as e:
            error_msg = f"Corrupted storage file {self.storage_path}: {e}"
            logger.error(error_msg)
            raise json.JSONDecodeError(error_msg, "", 0) from e
        except OSError as e:
            error_msg = f"Failed to read storage file {self.storage_path}: {e}"
            logger.error(error_msg)
            raise OSError(error_msg) from e

    def size(self) -> int:
        """Get current number of messages."""
        return len(self._messages)

    def is_empty(self) -> bool:
        """Check if memory is empty."""
        return len(self._messages) == 0

    def to_dict(self) -> dict[str, Any]:
        """
        Export memory to dict format.

        Returns:
            Dict with memory state
        """
        return {
            "max_length": self.max_length,
            "current_size": len(self._messages),
            "messages": list(self._messages),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationMemory":
        """
        Create memory from dict format (no auto-load from disk).

        Args:
            data: Dict with memory state

        Returns:
            ConversationMemory instance
        """
        memory = cls(max_length=data["max_length"], auto_load=False)
        for msg in data["messages"]:
            # Add messages directly to avoid persistence during construction
            message = {"role": msg["role"], "content": msg["content"]}
            memory._messages.append(message)
        return memory

    def __len__(self) -> int:
        """Get number of messages."""
        return len(self._messages)

    def __repr__(self) -> str:
        """String representation."""
        return f"ConversationMemory({len(self._messages)}/{self.max_length} messages)"
