"""Memory management for conversation history."""

import logging
from collections import deque
from typing import Any

from jarvis.config import get_config

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Manages conversation history with automatic truncation.

    For MVP: Simple in-memory storage with size limit.
    Future: Persistent storage, vector embeddings, summarization.
    """

    def __init__(self, max_length: int | None = None):
        """
        Initialize conversation memory.

        Args:
            max_length: Maximum number of messages to keep (defaults to config)
        """
        config = get_config()
        self.max_length = max_length or config.memory.max_conversation_length
        self._messages: deque[dict[str, str]] = deque(maxlen=self.max_length)
        logger.info(f"ConversationMemory initialized (max_length={self.max_length})")

    def add_message(self, role: str, content: str) -> None:
        """
        Add a message to memory.

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
        """Clear all messages from memory."""
        message_count = len(self._messages)
        self._messages.clear()
        logger.info(f"Memory cleared ({message_count} messages removed)")

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
        Create memory from dict format.

        Args:
            data: Dict with memory state

        Returns:
            ConversationMemory instance
        """
        memory = cls(max_length=data["max_length"])
        for msg in data["messages"]:
            memory.add_message(msg["role"], msg["content"])
        return memory

    def __len__(self) -> int:
        """Get number of messages."""
        return len(self._messages)

    def __repr__(self) -> str:
        """String representation."""
        return f"ConversationMemory({len(self._messages)}/{self.max_length} messages)"
