"""Self-improvement module for codebase analysis and improvement proposals.

This module provides supervised self-improvement capabilities where the agent can:
1. Analyze its own workspace to identify improvement opportunities
2. Generate targeted prompts for VS Code Copilot Chat
3. Track approval/rejection history to learn patterns

All workspace modifications must go through VS Code Copilot Agents, and every
prompt requires explicit human approval (safety gate).
"""

# Data models
from jarvis.self_improvement.copilot_interface import (
    CopilotInterface,
    IntegrationMethod,
    InterfaceConfig,
)

# Core components
from jarvis.self_improvement.detector import (
    BaseAnalyzer,
    ComplexityAnalyzer,
    DetectorConfig,
    ImprovementDetector,
    PylintAnalyzer,
)
from jarvis.self_improvement.models import (
    ApprovalDecision,
    ApprovalRequest,
    Category,
    ChangeType,
    CopilotPrompt,
    DecisionType,
    EstimatedEffort,
    ExecutionReport,
    ExecutionStatus,
    ExpectedChange,
    ImprovementOpportunity,
    LineRange,
    OpportunityContext,
    RiskLevel,
    Severity,
    ValidationResult,
    ValidationStatus,
)
from jarvis.self_improvement.orchestrator import (
    CycleResult,
    OrchestratorConfig,
    SelfImprovementOrchestrator,
)
from jarvis.self_improvement.proposer import PromptProposer
from jarvis.self_improvement.researcher import ImprovementResearcher, ResearchResult
from jarvis.self_improvement.tracker import ApprovalTracker, CooldownState, RateLimitConfig

__all__ = [
    # Models
    "ApprovalDecision",
    "ApprovalRequest",
    "Category",
    "ChangeType",
    "CopilotPrompt",
    "DecisionType",
    "EstimatedEffort",
    "ExecutionReport",
    "ExecutionStatus",
    "ExpectedChange",
    "ImprovementOpportunity",
    "LineRange",
    "OpportunityContext",
    "RiskLevel",
    "Severity",
    "ValidationResult",
    "ValidationStatus",
    # Detector
    "BaseAnalyzer",
    "ComplexityAnalyzer",
    "DetectorConfig",
    "ImprovementDetector",
    "PylintAnalyzer",
    # Proposer
    "PromptProposer",
    # Researcher
    "ImprovementResearcher",
    "ResearchResult",
    # Tracker
    "ApprovalTracker",
    "CooldownState",
    "RateLimitConfig",
    # Interface
    "CopilotInterface",
    "IntegrationMethod",
    "InterfaceConfig",
    # Orchestrator
    "CycleResult",
    "OrchestratorConfig",
    "SelfImprovementOrchestrator",
]
