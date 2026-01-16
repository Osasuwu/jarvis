"""Main Orchestrator implementing ReAct (Reasoning + Acting) loop."""

import logging
from typing import Any

from jarvis.config import get_config
from jarvis.core.executor import Executor
from jarvis.core.planner import Planner
from jarvis.llm import LLMProvider
from jarvis.memory.conversation import ConversationMemory
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Main orchestrator that implements ReAct loop for agent reasoning.

    The ReAct pattern:
    1. Think - Analyze the task and current state
    2. Act - Choose and execute tools
    3. Observe - Process results
    4. Repeat - Until task is complete
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        memory: ConversationMemory | None = None,
        max_iterations: int | None = None,
    ):
        """
        Initialize orchestrator.

        Args:
            llm_provider: LLM provider for reasoning
            tool_registry: Registry of available tools
            memory: Conversation memory (optional)
            max_iterations: Max ReAct iterations (defaults to config)
        """
        self.llm = llm_provider
        self.tool_registry = tool_registry
        self.memory = memory or ConversationMemory()
        self.planner = Planner(llm_provider, tool_registry)
        self.executor = Executor(tool_registry)

        config = get_config()
        self.max_iterations = max_iterations or config.agent.max_iterations

        logger.info(
            f"Orchestrator initialized with {len(tool_registry)} tools, "
            f"max_iterations={self.max_iterations}"
        )

    async def run(self, user_input: str) -> str:
        """
        Run the ReAct loop for a user query.

        Args:
            user_input: User's query or task

        Returns:
            Final response to the user
        """
        logger.info(f"Starting ReAct loop for query: {user_input[:100]}...")

        # Add user message to memory
        self.memory.add_message("user", user_input)

        iteration = 0
        final_response = ""

        while iteration < self.max_iterations:
            iteration += 1
            logger.debug(f"ReAct iteration {iteration}/{self.max_iterations}")

            # 1. THINK: Get current context and plan next action
            messages = self.memory.get_messages()
            llm_tools = self.tool_registry.get_llm_schemas()

            response = await self.llm.complete(
                messages=messages,
                tools=llm_tools if llm_tools else None,
            )

            # 2. DECIDE: Check if we should act or respond
            if response.tool_calls:
                # ACT: Execute tool calls
                logger.debug(f"LLM requested {len(response.tool_calls)} tool calls")

                tool_results = []
                for tool_call in response.tool_calls:
                    result = await self.executor.execute_tool(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                    tool_results.append(
                        {
                            "tool": tool_call.name,
                            "success": result.success,
                            "output": result.output,
                            "error": result.error,
                        }
                    )

                # Add tool execution to memory
                self.memory.add_message(
                    "assistant",
                    f"Used tools: {[tc.name for tc in response.tool_calls]}",
                )
                self.memory.add_message(
                    "system",
                    f"Tool results: {tool_results}",
                )

                # 3. OBSERVE: Continue loop with tool results
                continue

            else:
                # RESPOND: LLM provided final answer
                final_response = response.content
                self.memory.add_message("assistant", final_response)
                logger.info(f"Task completed in {iteration} iterations")
                break

        if not final_response:
            final_response = (
                "I couldn't complete the task within the maximum iterations. "
                "Please try breaking down your request into smaller parts."
            )
            logger.warning(f"Max iterations ({self.max_iterations}) reached")

        return final_response

    def reset(self) -> None:
        """Reset the orchestrator state and memory."""
        self.memory.clear()
        logger.info("Orchestrator reset")

    def get_stats(self) -> dict[str, Any]:
        """
        Get orchestrator statistics.

        Returns:
            Dict with statistics
        """
        return {
            "max_iterations": self.max_iterations,
            "tools_available": len(self.tool_registry),
            "memory_size": len(self.memory.get_messages()),
            "llm_provider": self.llm.provider_name,
            "llm_model": self.llm.model_name,
        }
