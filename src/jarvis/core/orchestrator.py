"""Main Orchestrator implementing ReAct (Reasoning + Acting) loop."""

import logging
import time
from typing import Any

from jarvis.config import get_config
from jarvis.core.exceptions import LLMError, ToolExecutionError, RetryableError
from jarvis.core.executor import Executor
from jarvis.core.planner import Planner
from jarvis.core.resilience import retry_async, RetryPolicy
from jarvis.llm import LLMProvider
from jarvis.gap_analyzer import GapDetector, GapResearcher, ToolProposer
from jarvis.memory.conversation import ConversationMemory
from jarvis.observability import set_request_id, clear_request_id
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
        self.gap_detector = GapDetector()
        self.gap_researcher = GapResearcher()
        self.tool_proposer = ToolProposer()

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
        # Set request ID for tracking
        request_id = set_request_id()
        start_time = time.time()
        
        logger.info(
            f"Starting ReAct loop for query: {user_input[:100]}...",
            extra={"component": "orchestrator", "action": "start", "request_id": request_id},
        )

        try:
            # Add user message to memory
            self.memory.add_message("user", user_input)

            iteration = 0
            final_response = ""
            tool_called_once = False

            while iteration < self.max_iterations:
                iteration += 1
                logger.debug(f"ReAct iteration {iteration}/{self.max_iterations}")

                # 1. THINK: Get current context and plan next action
                messages = self.memory.get_messages()

                # Only provide tools on first iteration, or after successful completion
                llm_tools = self.tool_registry.get_llm_schemas() if not tool_called_once else None

                # Execute LLM call with retry logic
                try:
                    response = await retry_async(
                        lambda: self.llm.complete(
                            messages=messages,
                            tools=llm_tools if llm_tools else None,
                        ),
                        max_attempts=2,
                        timeout=60.0,
                        operation_name="llm_complete",
                    )
                except Exception as e:
                    logger.error(f"LLM call failed after retries: {e}")
                    final_response = (
                        "I encountered an error communicating with the language model. "
                        "Please try again in a moment."
                    )
                    self.memory.add_message("assistant", final_response)
                    break

                # 2. DECIDE: Check if we should act or respond
                if response.tool_calls:
                    # ACT: Execute tool calls
                    logger.debug(f"LLM response content: {response.content}")
                    logger.debug(f"LLM requested {len(response.tool_calls)} tool calls")

                    tool_called_once = True

                    # Add assistant message with tool calls intent
                    self.memory.add_message("assistant", response.content or "Executing tools...")

                    tool_results = []
                    for tool_call in response.tool_calls:
                        try:
                            result = await retry_async(
                                lambda: self.executor.execute_tool(
                                    tool_name=tool_call.name,
                                    arguments=tool_call.arguments,
                                ),
                                max_attempts=2,
                                timeout=30.0,
                                operation_name=f"tool_{tool_call.name}",
                            )
                            tool_results.append(
                                {
                                    "tool": tool_call.name,
                                    "success": result.success,
                                    "output": result.output,
                                    "error": result.error,
                                }
                            )
                        except Exception as e:
                            logger.error(f"Tool {tool_call.name} failed after retries: {e}")
                            tool_results.append(
                                {
                                    "tool": tool_call.name,
                                    "success": False,
                                    "output": None,
                                    "error": f"Execution failed: {str(e)}",
                                }
                            )

                    # Add tool results to memory
                    results_text = "\n".join(
                        [
                            f"- {r['tool']}: {'✓ ' if r['success'] else '✗ '}{r['output'] or r['error']}"
                            for r in tool_results
                        ]
                    )
                    self.memory.add_message("system", f"Tool results:\n{results_text}")

                    # If any tool failed, detect capability gaps and propose solutions
                    failed = [r for r in tool_results if not r["success"]]
                    if failed:
                        suggestions: list[str] = []
                        for fr in failed:
                            gap = self.gap_detector.detect_from_error(
                                capability_name=fr["tool"],
                                description=f"Tool '{fr['tool']}' failed during execution",
                                context=user_input,
                                tool_name=fr["tool"],
                                error=str(fr["error"]),
                                severity="HIGH",
                            )
                            research = await self.gap_researcher.research_gap(gap)
                            proposal = self.tool_proposer.propose_tool(gap, research)
                            suggestions.append(
                                f"- {proposal.tool_name}: {proposal.description}. "
                                f"Hint: {proposal.implementation_hint}"
                            )

                        final_response = (
                            "Не удалось полностью выполнить запрос из-за ограничений инструментов.\n\n"
                            "Причины:\n" +
                            "\n".join(
                                [
                                    f"• {fr['tool']}: {fr['error'] or 'unknown error'}"
                                    for fr in failed
                                ]
                            ) +
                            "\n\nПредложения по решению:\n" + "\n".join(suggestions)
                        )
                        self.memory.add_message("assistant", final_response)
                        break

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

            # Log completion
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"ReAct loop completed",
                extra={
                    "component": "orchestrator",
                    "action": "complete",
                    "status": "success" if final_response else "timeout",
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )
            
            return final_response
        finally:
            # Clear request context
            clear_request_id()

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
