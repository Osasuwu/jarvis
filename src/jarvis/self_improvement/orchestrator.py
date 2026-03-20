"""Self-Improvement Orchestrator - coordinates the improvement cycle.

This module implements the agent reasoning model from the spec,
orchestrating detection, proposal, approval, and execution phases.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.safety.confirmation import ImprovementApprovalPrompt
from jarvis.self_improvement.copilot_interface import CopilotInterface, InterfaceConfig
from jarvis.self_improvement.detector import DetectorConfig, ImprovementDetector
from jarvis.self_improvement.models import (
    CopilotPrompt,
    DecisionType,
    ExecutionReport,
    ExecutionStatus,
    ImprovementOpportunity,
    RiskLevel,
    ValidationResult,
    ValidationStatus,
)
from jarvis.self_improvement.proposer import PromptProposer
from jarvis.self_improvement.researcher import ImprovementResearcher
from jarvis.self_improvement.tracker import ApprovalTracker, RateLimitConfig

# Protected paths that must never be analyzed per spec
PROTECTED_PATHS = frozenset(
    {
        "self_improvement/",
        "safety/",
        "core/orchestrator.py",
    }
)

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the self-improvement orchestrator."""

    workspace_path: Path
    storage_path: Path | None = None
    max_opportunities_per_cycle: int = 10
    max_prompts_per_batch: int = 5
    risk_ceiling: RiskLevel = RiskLevel.MEDIUM  # Require override for higher
    enable_validation: bool = True

    def __post_init__(self) -> None:
        if self.storage_path is None:
            self.storage_path = self.workspace_path / ".jarvis" / "self_improvement"


class CycleResult:
    """Result of an improvement cycle."""

    def __init__(self) -> None:
        self.opportunities_detected: int = 0
        self.opportunities_vetted: int = 0
        self.prompts_generated: int = 0
        self.prompts_approved: int = 0
        self.prompts_rejected: int = 0
        self.prompts_deferred: int = 0
        self.executions_successful: int = 0
        self.executions_failed: int = 0
        self.stopped_reason: str | None = None
        self.escalations: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunities_detected": self.opportunities_detected,
            "opportunities_vetted": self.opportunities_vetted,
            "prompts_generated": self.prompts_generated,
            "prompts_approved": self.prompts_approved,
            "prompts_rejected": self.prompts_rejected,
            "prompts_deferred": self.prompts_deferred,
            "executions_successful": self.executions_successful,
            "executions_failed": self.executions_failed,
            "stopped_reason": self.stopped_reason,
            "escalations": self.escalations,
        }


class SelfImprovementOrchestrator:
    """Orchestrates the self-improvement cycle.

    Implements the Agent Reasoning Model from spec section 3.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        approval_callback: callable | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            config: Orchestrator configuration
            approval_callback: Async callback for approval requests.
                Signature: async def callback(request: ApprovalRequest) -> tuple[DecisionType, str | None]
                Returns (decision, edited_prompt_or_feedback)
        """
        self.config = config
        self.approval_callback = approval_callback

        # Initialize components
        self.detector = ImprovementDetector(
            DetectorConfig(
                workspace_path=config.workspace_path,
                excluded_paths=set(PROTECTED_PATHS),
            )
        )
        self.proposer = PromptProposer(config.workspace_path)
        self.researcher = ImprovementResearcher()
        self.tracker = ApprovalTracker(
            storage_path=config.storage_path or Path(".jarvis/self_improvement"),
            rate_limit_config=RateLimitConfig(),
        )
        self.interface = CopilotInterface(
            InterfaceConfig(
                queue_path=config.workspace_path / ".copilot_queue",
            )
        )

    async def run_cycle(self) -> CycleResult:
        """Run a complete improvement cycle.

        Implements the full agent reasoning model from spec section 3:
        Phase 0: Entry Guard
        Phase 1: Detection Plan Selection
        Phase 2: Opportunity Vetting
        Phase 3: Proposal Synthesis
        Phase 4: Approval Packaging
        Phase 5: Execution Gate
        Phase 6: Post-Execution Verification
        Phase 7: Learning Update

        Returns:
            CycleResult with statistics and outcomes
        """
        result = CycleResult()

        # Phase 0: Entry Guard
        guard_result = await self._phase0_entry_guard()
        if guard_result:
            result.stopped_reason = guard_result
            return result

        # Phase 1: Detection Plan Selection
        skip_detectors = self.tracker.get_skipped_detectors()

        if not self.detector.analyzers:
            result.stopped_reason = "No eligible detectors"
            return result

        # Phase 2: Opportunity Vetting
        opportunities = await self.detector.detect(skip_detectors=skip_detectors)
        result.opportunities_detected = len(opportunities)

        if not opportunities:
            result.stopped_reason = "No opportunities found"
            return result

        # Score and prioritize
        scored = self._score_opportunities(opportunities)

        # Filter by per-file and per-category rate limits (M2 fix)
        filtered = []
        for opp in scored:
            limits = self.tracker.check_rate_limits(
                file_path=opp.file_path,
                category=opp.category,
            )
            if limits.get("per_file_weekly"):
                logger.debug(f"Skipping {opp.id}: per-file rate limit exceeded for {opp.file_path}")
                continue
            filtered.append(opp)

        vetted = filtered[: self.config.max_opportunities_per_cycle]
        result.opportunities_vetted = len(vetted)

        # Phase 3: Proposal Synthesis
        prompts: list[CopilotPrompt] = []
        for opportunity in vetted:
            prompt = await self._synthesize_proposal(opportunity)
            if prompt:
                prompts.append(prompt)

        result.prompts_generated = len(prompts)

        if not prompts:
            result.stopped_reason = "No valid prompts generated"
            return result

        # Phase 4: Approval Packaging
        batches = self.proposer.batch_prompts(prompts, self.config.max_prompts_per_batch)

        # Process each batch
        category_counts: dict[str, int] = {}  # Track per-category in this cycle

        for batch in batches:
            # Phase 5: Execution Gate
            for prompt in batch:
                # Track enqueue time per Q7 decision
                prompt_created_at = datetime.now()

                opportunity = self._find_opportunity(prompt.opportunity_id, vetted)
                if not opportunity:
                    continue

                # Per-category rate limit: max 5 per cycle (M2 fix)
                category_key = opportunity.category.value
                category_counts[category_key] = category_counts.get(category_key, 0)
                if category_counts[category_key] >= 5:
                    logger.debug(
                        f"Skipping {opportunity.id}: per-category limit (5) exceeded for {category_key}"
                    )
                    continue
                category_counts[category_key] += 1

                # Check risk ceiling
                if self._exceeds_risk_ceiling(prompt):
                    result.escalations.append(
                        f"Prompt {prompt.id} exceeds risk ceiling, requires override"
                    )
                    continue

                # Request approval
                decision, feedback = await self._request_approval(prompt, opportunity)
                approval_time = datetime.now()

                # Calculate approval latency
                approval_latency_seconds = (approval_time - prompt_created_at).total_seconds()

                if decision == DecisionType.APPROVE:
                    result.prompts_approved += 1

                    # Enqueue for execution with timing metadata
                    self.interface.enqueue_prompt(prompt)

                    # Store timing for future report generation
                    prompt._approval_metadata = {  # noqa: SLF001
                        "created_at": prompt_created_at,
                        "approved_at": approval_time,
                        "latency_seconds": approval_latency_seconds,
                    }

                    # Record decision with context
                    self.tracker.record_decision(
                        prompt,
                        decision,
                        category=opportunity.category.value,
                        detector_name=opportunity.detector,
                    )

                elif decision == DecisionType.REJECT:
                    result.prompts_rejected += 1
                    self.tracker.record_decision(
                        prompt,
                        decision,
                        user_feedback=feedback,
                        category=opportunity.category.value,
                        detector_name=opportunity.detector,
                    )

                elif decision == DecisionType.DEFER:
                    result.prompts_deferred += 1
                    self.tracker.record_decision(
                        prompt,
                        decision,
                        category=opportunity.category.value,
                        detector_name=opportunity.detector,
                    )

                elif decision == DecisionType.EDIT:
                    # Re-scope with edited prompt
                    # See design_questions.md Q3: Edit loop implementation needs clarification
                    self.tracker.record_decision(
                        prompt,
                        decision,
                        edited_prompt=feedback,
                        category=opportunity.category.value,
                        detector_name=opportunity.detector,
                    )

        # Phase 6 & 7 happen when user marks prompts as complete
        # (handled by separate methods)

        return result

    async def _phase0_entry_guard(self) -> str | None:
        """Phase 0: Entry Guard.

        Per spec:
        - Validate trigger type and confirm scope excludes protected paths
        - Check rate limits and cooldowns
        - If violation, halt and request human decision

        Returns:
            Error message if guard fails, None if OK to proceed
        """
        # Check rate limits
        limits = self.tracker.check_rate_limits()
        if limits.get("global_weekly"):
            return "Global weekly rate limit exceeded (max 20 improvements per week)"

        # Check workspace for git conflicts
        # Per spec: DO NOT process workspace if unresolved Git conflicts exist
        if await self._has_git_conflicts():
            return "Unresolved Git conflicts exist in workspace"

        return None

    async def _has_git_conflicts(self) -> bool:
        """Check if workspace has unresolved git conflicts.

        Per spec Phase 0: "If conflicts exist, stop and escalate"
        Conservative approach: treat git unavailability as requiring escalation.

        Returns:
            True if conflicts detected OR git unavailable (escalation required)
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.config.workspace_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Check for conflict markers (UU = both modified)
            for line in result.stdout.splitlines():
                if line.startswith("UU ") or line.startswith("AA "):
                    return True
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Per C5 fix: Escalate when git unavailable (conservative safety)
            logger.warning("Git unavailable or timed out - escalating for safety")
            return True

    def _score_opportunities(
        self, opportunities: list[ImprovementOpportunity]
    ) -> list[ImprovementOpportunity]:
        """Score and sort opportunities by priority."""
        scored: list[tuple[float, ImprovementOpportunity]] = []

        for opp in opportunities:
            approval_rate = self.tracker.get_approval_rate(opp.category)
            score = self.detector.score_opportunity(opp, approval_rate)
            scored.append((score, opp))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [opp for _, opp in scored]

    async def _synthesize_proposal(
        self, opportunity: ImprovementOpportunity
    ) -> CopilotPrompt | None:
        """Phase 3: Proposal Synthesis.

        Per spec:
        - Assemble action spec: objective, minimal scope, expected changes
        - Reject opportunities that are not atomic
        - If context exceeds size thresholds, split or defer
        """
        # Validate atomicity
        if not opportunity.atomic:
            return None

        # Research best practices (M4 integration)
        research = await self.researcher.research(opportunity)

        # Generate prompt with research findings
        prompt = self.proposer.propose(
            opportunity,
            related_files=list(research.external_references),
            best_practices=research.best_practices[:5] if research.best_practices else None,
        )

        return prompt

    def _find_opportunity(
        self, opportunity_id: str, opportunities: list[ImprovementOpportunity]
    ) -> ImprovementOpportunity | None:
        """Find an opportunity by ID."""
        for opp in opportunities:
            if opp.id == opportunity_id:
                return opp
        return None

    def _exceeds_risk_ceiling(self, prompt: CopilotPrompt) -> bool:
        """Check if prompt exceeds configured risk ceiling."""
        risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

        ceiling_index = risk_order.index(self.config.risk_ceiling)
        prompt_index = risk_order.index(prompt.risk_level)

        return prompt_index > ceiling_index

    async def _request_approval(
        self,
        prompt: CopilotPrompt,
        opportunity: ImprovementOpportunity,
    ) -> tuple[DecisionType, str | None]:
        """Request approval from human with edit loop support.

        Per Q3 design decision: Single edit loop with diff display and re-approval.

        Returns:
            Tuple of (decision, metadata):
            - (APPROVE, None): Approved as-is or after single edit
            - (REJECT, reason): Rejected with optional reason
            - (DEFER, None): Deferred for later
        """
        # Use new ImprovementApprovalPrompt from safety module (Q2 decision)
        approval_system = ImprovementApprovalPrompt()

        # Build rationale from historical context
        historical = self.tracker.get_historical_context(opportunity.category)
        rationale = f"Based on {len(historical)} similar decisions in category '{opportunity.category.value}'"

        # First approval attempt
        decision, metadata = await approval_system.request_improvement_approval(
            opportunity=opportunity,
            proposed_prompt=prompt,
            rationale=rationale,
        )

        # Handle category disable (encoded as REJECT with special metadata prefix)
        if metadata and metadata.startswith("category_disabled:"):
            reason = metadata.replace("category_disabled:", "")
            self.tracker.record_decision(
                opportunity_id=opportunity.id,
                decision=DecisionType.REJECT,
                detector_name=opportunity.detector_name,
                category=opportunity.category,
                reason=f"Category disabled by user: {reason}",
            )
            return DecisionType.REJECT, reason

        if decision == DecisionType.EDIT:
            # Single edit loop per Q3 decision
            if not metadata:
                return DecisionType.REJECT, "No edits provided"

            # Show diff
            original_lines = prompt.prompt_text.splitlines(keepends=True)
            edited_lines = metadata.splitlines(keepends=True)
            diff = list(
                difflib.unified_diff(
                    original_lines,
                    edited_lines,
                    fromfile="Original Prompt",
                    tofile="Edited Prompt",
                    lineterm="",
                )
            )

            print("\n" + "=" * 60)
            print("PROMPT DIFF:")
            print("=" * 60)
            print("\n".join(diff))
            print("=" * 60)

            # Re-approval required per Q3
            re_approval = await asyncio.to_thread(
                input,
                "\nRe-approve edited prompt? ([y]es/[n]o): ",
            )

            if re_approval.strip().lower() in ("y", "yes"):
                # Update prompt with edited text
                prompt.prompt_text = metadata
                # Mark as user-edited for learning
                prompt.validation_plan.append("# USER_EDITED: true")
                return DecisionType.APPROVE, "Approved after edit"

            # Rejected after edit
            return DecisionType.REJECT, "Rejected after edit"

        # Return the decision as-is (APPROVE or REJECT)
        return decision, metadata

    async def verify_execution(
        self,
        prompt: CopilotPrompt,
        files_modified: list[str],
    ) -> ExecutionReport:
        """Phase 6: Post-Execution Verification.

        Per spec:
        - Verify expected files changed and validations pass
        - If validations fail or changes diverge, flag as "failed execution"
        """
        expected_files = {c.file for c in prompt.expected_changes}
        modified_set = set(files_modified)

        # Check scope match
        scope_match = expected_files.issubset(modified_set)

        # Run validations
        validations: dict[str, ValidationResult] = {}

        if self.config.enable_validation:
            for validation_cmd in prompt.validation_plan:
                result = await self._run_validation(validation_cmd)
                # Use first word of command as key
                key = validation_cmd.split()[0]
                validations[key] = result

        # Determine overall status
        all_pass = all(v.status == ValidationStatus.PASS for v in validations.values())

        if scope_match and all_pass:
            status = ExecutionStatus.SUCCESS
            error_details = None
        elif not scope_match:
            status = ExecutionStatus.PARTIAL
            error_details = f"Scope mismatch: expected {expected_files}, got {modified_set}"
        else:
            status = ExecutionStatus.FAILED
            failed_validations = [
                k for k, v in validations.items() if v.status == ValidationStatus.FAIL
            ]
            error_details = f"Validations failed: {failed_validations}"

        # Extract timing metadata if available (Q7 implementation)
        timing_metadata = getattr(prompt, "_approval_metadata", None)
        duration_seconds = timing_metadata["latency_seconds"] if timing_metadata else 0.0
        created_at = timing_metadata["created_at"] if timing_metadata else datetime.now()
        approved_at = timing_metadata["approved_at"] if timing_metadata else None

        report = ExecutionReport(
            prompt_id=prompt.id,
            status=status,
            files_modified=files_modified,
            files_expected=list(expected_files),
            scope_match=scope_match,
            validations=validations,
            duration_seconds=duration_seconds,
            error_details=error_details,
            copilot_response_length=0,
            user_notes="",
            created_at=created_at,
            approved_at=approved_at,
        )

        # Phase 7: Learning Update
        self.tracker.record_execution(report)

        return report

    async def _run_validation(self, command: str) -> ValidationResult:
        """Run a validation command."""
        try:
            result = subprocess.run(
                command.split(),
                cwd=self.config.workspace_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            status = ValidationStatus.PASS if result.returncode == 0 else ValidationStatus.FAIL
            output = result.stdout + result.stderr

            return ValidationResult(
                status=status,
                output=output[:500],
            )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                status=ValidationStatus.FAIL,
                output="Validation timed out",
            )
        except FileNotFoundError:
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                output=f"Command not found: {command.split()[0]}",
            )

    def get_pending_prompts(self) -> list[str]:
        """Get list of pending prompt IDs awaiting user action."""
        return self.interface.get_pending_prompts()

    def complete_prompt(
        self,
        prompt_id: str,
        files_modified: list[str],
        user_notes: str = "",
    ) -> ExecutionReport | None:
        """Mark a prompt as complete and record the execution.

        Args:
            prompt_id: ID of the completed prompt
            files_modified: List of files that were modified
            user_notes: Optional notes

        Returns:
            Execution report or None if prompt not found
        """
        # Find the prompt in stored prompts
        for prompt in self.proposer.prompts:
            if prompt.id == prompt_id:
                return self.interface.mark_complete(prompt, files_modified, user_notes)
        return None

    def fail_prompt(
        self,
        prompt_id: str,
        error_details: str,
        user_notes: str = "",
    ) -> ExecutionReport | None:
        """Mark a prompt as failed.

        Args:
            prompt_id: ID of the failed prompt
            error_details: What went wrong
            user_notes: Optional notes

        Returns:
            Execution report or None if prompt not found
        """
        for prompt in self.proposer.prompts:
            if prompt.id == prompt_id:
                return self.interface.mark_failed(prompt, error_details, user_notes)
        return None
