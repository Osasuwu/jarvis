"""Main Orchestrator implementing ReAct (Reasoning + Acting) loop."""

import logging
import time
from typing import Any

from jarvis.config import get_config
from jarvis.core.executor import Executor
from jarvis.core.planner import Planner
from jarvis.core.resilience import retry_async
from jarvis.gap_analyzer import GapDetector, GapResearcher, ToolProposer
from jarvis.llm import LLMProvider
from jarvis.memory.conversation import ConversationMemory
from jarvis.observability import clear_log_context, set_log_context, update_log_context
from jarvis.safety.auditor import AuditLogger
from jarvis.safety.confirmation import ConfirmationPrompt
from jarvis.safety.whitelist import WhitelistManager
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Main orchestrator that implements ReAct loop for agent reasoning.

    The ReAct pattern:
    1. Think - Analyze the task and current state
    2. Act - Choose and execute tools (with safety checks)
    3. Observe - Process results
    4. Repeat - Until task is complete

    Safety enforcement:
    - All tool executions go through Executor with safety layer
    - HIGH risk tools require user confirmation
    - All operations audited and logged
    - Whitelist enforcement for parameters
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        memory: ConversationMemory | None = None,
        max_iterations: int | None = None,
        executor: Executor | None = None,
        confirmation: ConfirmationPrompt | None = None,
        whitelist: WhitelistManager | None = None,
        auditor: AuditLogger | None = None,
    ):
        """
        Initialize orchestrator.

        Args:
            llm_provider: LLM provider for reasoning
            tool_registry: Registry of available tools
            memory: Conversation memory (optional)
            max_iterations: Max ReAct iterations (defaults to config)
            executor: Custom executor (optional; created if not provided)
            confirmation: Confirmation system (optional)
            whitelist: Whitelist manager (optional)
            auditor: Audit logger (optional)
        """
        self.llm = llm_provider
        self.tool_registry = tool_registry
        self.memory = memory if memory is not None else ConversationMemory()
        self.planner = Planner(llm_provider, tool_registry)
        self.gap_detector = GapDetector()
        self.gap_researcher = GapResearcher()
        self.tool_proposer = ToolProposer()

        config = get_config()
        self.max_iterations = max_iterations or config.agent.max_iterations

        # Initialize executor with safety layer
        if executor is None:
            # Create executor with safety components
            # Risk levels for confirmation are configured via ToolSettings
            require_confirmation_for = config.tools.require_confirmation_for_risk_levels
            self.executor = Executor(
                tool_registry,
                confirmation=confirmation,
                whitelist=whitelist,
                auditor=auditor,
                require_confirmation_for=require_confirmation_for,
            )
        else:
            self.executor = executor

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
        # Set logging context for tracking
        set_log_context(operation="react_loop")
        start_time = time.time()

        logger.info(
            f"Starting ReAct loop for query: {user_input[:100]}...",
            extra={"component": "orchestrator", "action": "start"},
        )

        try:
            # Add user message to memory
            self.memory.add_message("user", user_input)

            iteration = 0
            final_response = ""

            # FIXME: Tool availability logic issue
            # This flag was originally designed to hide tools from LLM after the first tool call,
            # but this causes problems:
            # - LLM cannot see available tools in later iterations
            # - If a follow-up tool call is needed, LLM has no way to know what tools exist
            # - Results in "tool not found" errors or LLM confusion
            #
            # Recommended fix: Always provide tools to LLM, OR implement proper tool availability
            # negotiation based on conversation state. For now, keeping the flag but documenting
            # the issue. This will be addressed in a future update.
            #
            # Related: Task 4 in stabilization_plan.md
            tool_called_once = False

            while iteration < self.max_iterations:
                iteration += 1
                update_log_context(operation=f"react_iteration_{iteration}")
                logger.debug(f"ReAct iteration {iteration}/{self.max_iterations}")

                # 1. THINK: Get current context and plan next action
                messages = self.memory.get_messages()

                # Tool availability: Currently tools are hidden after first use (see FIXME above)
                # This behavior is under review and may change in future releases
                llm_tools = self.tool_registry.get_llm_schemas() if not tool_called_once else None

                # Execute LLM call with retry logic
                try:
                    response = await retry_async(
                        lambda msgs=messages, tools=llm_tools: self.llm.complete(
                            messages=msgs,
                            tools=tools if tools else None,
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
                                lambda tc=tool_call: self.executor.execute_tool(
                                    tool_name=tc.name,
                                    arguments=tc.arguments,
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

                        final_response = "Не удалось полностью выполнить запрос из-за ограничений инструментов.\n\n" "Причины:\n" + "\n".join(
                            [f"• {fr['tool']}: {fr['error'] or 'unknown error'}" for fr in failed]
                        ) + "\n\nПредложения по решению:\n" + "\n".join(
                            suggestions
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
                "ReAct loop completed",
                extra={
                    "component": "orchestrator",
                    "action": "complete",
                    "status": "success" if final_response else "timeout",
                    "duration_ms": duration_ms,
                },
            )

            return final_response
        finally:
            # Clear request context
            clear_log_context()

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
