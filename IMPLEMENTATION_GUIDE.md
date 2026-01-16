# Jarvis AI Agent — Реализация Рекомендаций (Implementation Guide)

**Дата:** Январь 16, 2026  
**Статус:** Ready for implementation  
**Приоритет:** Phase 7 (следующая фаза после Phase 6)

---

## 📋 Содержание

1. [Tool Auto-Discovery System](#tool-auto-discovery-system)
2. [Error Handling & Resilience](#error-handling--resilience)
3. [Structured Logging](#structured-logging)
4. [Smart Memory Management](#smart-memory-management)
5. [Caching Layer](#caching-layer)

---

## Tool Auto-Discovery System

### 📁 File Structure

```
src/jarvis/tools/
├── __init__.py              (updated)
├── base.py                  (existing)
├── registry.py              (existing)
├── discovery.py             ✨ NEW
├── loader.py                ✨ NEW
├── builtin/
│   ├── __init__.py
│   └── ...existing tools...
└── custom/                  ✨ NEW (for user tools)
    └── __init__.py

configs/
└── tools.yaml              ✨ NEW
```

### 1️⃣ Discovery Module

```python
# src/jarvis/tools/discovery.py
"""Tool discovery and loading mechanism."""

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any

import yaml

from jarvis.tools.base import Tool
from jarvis.tools.loader import ToolLoader

logger = logging.getLogger(__name__)


class ToolDiscovery:
    """
    Discover and load tools from various sources:
    - Built-in tools
    - External directories
    - Configuration files
    """

    def __init__(self):
        """Initialize discovery system."""
        self.loader = ToolLoader()
        self._discovered_tools: dict[str, Tool] = {}
        logger.info("ToolDiscovery initialized")

    def discover_builtin_tools(self) -> list[Tool]:
        """
        Discover built-in tools from jarvis.tools.builtin.

        Returns:
            List of built-in Tool instances
        """
        logger.info("Discovering built-in tools")
        tools = []

        try:
            # Import builtin module
            import jarvis.tools.builtin as builtin_module

            # Scan module for Tool subclasses
            for name, obj in inspect.getmembers(builtin_module):
                if inspect.isclass(obj) and issubclass(obj, Tool) and obj is not Tool:
                    try:
                        instance = obj()
                        tools.append(instance)
                        logger.info(f"Discovered built-in tool: {instance.name}")
                    except Exception as e:
                        logger.error(f"Failed to instantiate {name}: {e}")

        except ImportError as e:
            logger.error(f"Failed to import builtin tools: {e}")

        logger.info(f"Discovered {len(tools)} built-in tools")
        return tools

    def discover_from_directory(self, path: str) -> list[Tool]:
        """
        Discover tools from a directory.

        Looks for Python files with Tool subclasses.

        Args:
            path: Directory path to search

        Returns:
            List of Tool instances
        """
        logger.info(f"Discovering tools from directory: {path}")
        tools = []
        tool_dir = Path(path)

        if not tool_dir.exists():
            logger.warning(f"Tool directory does not exist: {path}")
            return tools

        # Find all .py files in directory
        for py_file in tool_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            try:
                module = self.loader.load_module_from_file(py_file)
                if module:
                    tools.extend(self._extract_tools_from_module(module))
            except Exception as e:
                logger.error(f"Failed to load tools from {py_file}: {e}")

        logger.info(f"Discovered {len(tools)} tools from directory")
        return tools

    def discover_from_config(self, config_file: str) -> list[Tool]:
        """
        Discover tools from configuration file.

        Example tools.yaml:
        ```yaml
        tools:
          - name: file_operations
            source: jarvis.tools.builtin
            enabled: true
          - name: custom_analysis
            source: ./custom_tools/analysis_tool.py
            enabled: true
            config:
              param1: value1
        ```

        Args:
            config_file: Path to YAML config

        Returns:
            List of Tool instances
        """
        logger.info(f"Discovering tools from config: {config_file}")
        tools = []

        try:
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)

            if not config or "tools" not in config:
                logger.warning(f"No tools defined in {config_file}")
                return tools

            for tool_spec in config.get("tools", []):
                if not tool_spec.get("enabled", True):
                    logger.debug(f"Skipping disabled tool: {tool_spec.get('name')}")
                    continue

                try:
                    tool = self._load_tool_from_spec(tool_spec)
                    if tool:
                        tools.append(tool)
                except Exception as e:
                    logger.error(f"Failed to load tool {tool_spec.get('name')}: {e}")

        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_file}")
        except Exception as e:
            logger.error(f"Failed to parse config file: {e}")

        logger.info(f"Discovered {len(tools)} tools from config")
        return tools

    def discover_installed_extras(self) -> list[Tool]:
        """
        Discover tools based on installed optional dependencies.

        For example, if 'pillow' is installed, load image tools.

        Returns:
            List of Tool instances for installed extras
        """
        logger.info("Checking for installed optional dependencies")
        tools = []

        optional_tools = {
            "PIL": "jarvis.tools.builtin.image",  # if Pillow installed
            "pandas": "jarvis.tools.builtin.data",  # if pandas installed
            "requests": "jarvis.tools.builtin.http",  # if requests installed
        }

        for package_name, module_name in optional_tools.items():
            try:
                __import__(package_name)
                logger.info(f"Detected {package_name}, loading optional tools")
                # Load module
                module = importlib.import_module(module_name)
                tools.extend(self._extract_tools_from_module(module))
            except ImportError:
                logger.debug(f"{package_name} not installed, skipping optional tools")

        return tools

    def discover_all(
        self,
        include_builtin: bool = True,
        custom_paths: list[str] | None = None,
        config_file: str | None = None,
        include_extras: bool = True,
    ) -> list[Tool]:
        """
        Discover all available tools.

        Args:
            include_builtin: Include built-in tools
            custom_paths: Additional paths to search
            config_file: Configuration file path
            include_extras: Include optional dependency tools

        Returns:
            Complete list of discovered tools
        """
        logger.info("Starting comprehensive tool discovery")
        all_tools = []

        # 1. Built-in tools
        if include_builtin:
            all_tools.extend(self.discover_builtin_tools())

        # 2. Custom directories
        if custom_paths:
            for path in custom_paths:
                all_tools.extend(self.discover_from_directory(path))

        # 3. Configuration file
        if config_file:
            all_tools.extend(self.discover_from_config(config_file))

        # 4. Optional dependencies
        if include_extras:
            all_tools.extend(self.discover_installed_extras())

        # 5. Deduplicate by name
        seen_names = set()
        unique_tools = []
        for tool in all_tools:
            if tool.name not in seen_names:
                unique_tools.append(tool)
                seen_names.add(tool.name)
            else:
                logger.warning(f"Duplicate tool name: {tool.name}, skipping")

        logger.info(f"Total tools discovered: {len(unique_tools)}")
        return unique_tools

    # Private methods

    def _extract_tools_from_module(self, module: Any) -> list[Tool]:
        """Extract Tool instances from a module."""
        tools = []
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, Tool) and obj is not Tool:
                try:
                    instance = obj()
                    tools.append(instance)
                    logger.info(f"Loaded tool: {instance.name}")
                except Exception as e:
                    logger.error(f"Failed to instantiate {name}: {e}")
        return tools

    def _load_tool_from_spec(self, spec: dict[str, Any]) -> Tool | None:
        """Load a single tool from config specification."""
        name = spec.get("name")
        source = spec.get("source")

        if not name or not source:
            logger.error(f"Invalid tool spec: {spec}")
            return None

        # If source is a module path
        if "." in source and not source.endswith(".py"):
            try:
                module = importlib.import_module(source)
                tools = self._extract_tools_from_module(module)
                for tool in tools:
                    if tool.name == name:
                        return tool
            except ImportError as e:
                logger.error(f"Failed to import module {source}: {e}")
                return None

        # If source is a file path
        if source.endswith(".py"):
            try:
                module = self.loader.load_module_from_file(Path(source))
                if module:
                    tools = self._extract_tools_from_module(module)
                    for tool in tools:
                        if tool.name == name:
                            return tool
            except Exception as e:
                logger.error(f"Failed to load tool from file {source}: {e}")
                return None

        return None
```

### 2️⃣ Loader Module

```python
# src/jarvis/tools/loader.py
"""Module loading utilities."""

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)


class ToolLoader:
    """Load Python modules from files dynamically."""

    @staticmethod
    def load_module_from_file(file_path: Path) -> ModuleType | None:
        """
        Load a Python module from a file path.

        Args:
            file_path: Path to Python file

        Returns:
            Loaded module or None if failed
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        try:
            module_name = f"jarvis_dynamic_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)

            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                logger.info(f"Loaded module: {module_name}")
                return module
        except Exception as e:
            logger.error(f"Failed to load module from {file_path}: {e}")
            return None

        return None
```

### 3️⃣ Updated main.py

```python
# src/jarvis/main.py (updated)
"""Main entry point for Jarvis CLI application."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from jarvis.config import get_config
from jarvis.core.orchestrator import Orchestrator
from jarvis.llm import GroqProvider, LocalStubProvider
from jarvis.memory import ConversationMemory
from jarvis.tools.discovery import ToolDiscovery
from jarvis.tools.registry import ToolRegistry

# ... rest of file ...

def _create_orchestrator() -> Orchestrator:
    """Create and initialize the orchestrator."""
    try:
        config = get_config()

        # Initialize LLM Provider
        use_local_env = os.getenv("USE_LOCAL_LLM", "").lower() in ("1", "true", "yes")
        if use_local_env:
            local_model = os.getenv("LOCAL_LLM_MODEL", "qwen2:4b")
            console.print(
                f"[yellow]USE_LOCAL_LLM enabled; using local Ollama model '{local_model}'.[/yellow]"
            )
            llm = LocalStubProvider(model=local_model)
        elif config.llm.groq_api_key:
            llm = GroqProvider(
                api_key=config.llm.groq_api_key,
                model=config.llm.model,
            )
        else:
            console.print(
                "[yellow]GROQ_API_KEY not set; using local stub LLM fallback.[/yellow]"
            )
            llm = LocalStubProvider()

        # ✨ NEW: Initialize Tool Registry with Discovery
        registry = ToolRegistry()
        discovery = ToolDiscovery()

        # Discover and register tools
        workspace_root = Path(__file__).parent.parent.parent
        custom_tools_path = workspace_root / "custom_tools"
        config_file = workspace_root / "configs" / "tools.yaml"

        tools = discovery.discover_all(
            include_builtin=True,
            custom_paths=[str(custom_tools_path)] if custom_tools_path.exists() else [],
            config_file=str(config_file) if config_file.exists() else None,
            include_extras=True,
        )

        for tool in tools:
            registry.register(tool)

        console.print(f"[green]Registered {len(tools)} tools[/green]")

        # Initialize Memory
        memory = ConversationMemory()

        # Create orchestrator
        return Orchestrator(llm, registry, memory)

    except Exception as e:
        console.print(f"[red]Failed to initialize orchestrator: {e}[/red]")
        raise
```

### 4️⃣ Configuration File Example

```yaml
# configs/tools.yaml
"""Tool configuration and registration."""

tools:
  # Built-in tools
  - name: echo
    source: jarvis.tools.builtin
    enabled: true
    description: Echo tool for testing

  - name: file_read
    source: jarvis.tools.builtin
    enabled: true

  - name: file_write
    source: jarvis.tools.builtin
    enabled: true

  - name: list_directory
    source: jarvis.tools.builtin
    enabled: true

  - name: shell_execute
    source: jarvis.tools.builtin
    enabled: true

  - name: web_fetch
    source: jarvis.tools.builtin
    enabled: true

  - name: web_search
    source: jarvis.tools.builtin
    enabled: true

  # Custom tools (if Pillow is installed)
  - name: image_resize
    source: ./custom_tools/image_tools.py
    enabled: false  # Set to true if pillow installed
    config:
      max_width: 1920
      max_height: 1080

  # Data tools (if pandas is installed)
  - name: csv_analyze
    source: ./custom_tools/data_tools.py
    enabled: false  # Set to true if pandas installed
```

### 5️⃣ Unit Tests

```python
# tests/unit/test_tool_discovery.py
"""Tests for tool discovery system."""

import pytest
from pathlib import Path
from jarvis.tools.discovery import ToolDiscovery
from jarvis.tools.base import Tool, RiskLevel, ToolParameter, ToolResult


class DummyTool(Tool):
    """Dummy tool for testing."""
    name = "dummy_tool"
    description = "Dummy tool"
    risk_level = RiskLevel.LOW

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="dummy")

    def get_parameters(self):
        return []


def test_discover_builtin_tools():
    """Test discovering built-in tools."""
    discovery = ToolDiscovery()
    tools = discovery.discover_builtin_tools()
    
    assert len(tools) > 0
    tool_names = [t.name for t in tools]
    assert "echo" in tool_names
    assert "file_read" in tool_names


def test_discover_from_nonexistent_directory():
    """Test discovering from non-existent directory."""
    discovery = ToolDiscovery()
    tools = discovery.discover_from_directory("/nonexistent/path")
    
    assert tools == []


@pytest.mark.parametrize("include_extras", [True, False])
def test_discover_all(include_extras):
    """Test comprehensive discovery."""
    discovery = ToolDiscovery()
    tools = discovery.discover_all(
        include_builtin=True,
        include_extras=include_extras,
    )
    
    assert len(tools) > 0
    # Check no duplicates
    names = [t.name for t in tools]
    assert len(names) == len(set(names))


def test_deduplication():
    """Test that duplicate tool names are deduplicated."""
    discovery = ToolDiscovery()
    tools = discovery.discover_all()
    
    names = [t.name for t in tools]
    assert len(names) == len(set(names))
```

---

## Error Handling & Resilience

### 1️⃣ Exceptions Module

```python
# src/jarvis/core/exceptions.py
"""Custom exceptions for Jarvis."""


class JarvisException(Exception):
    """Base exception for all Jarvis errors."""
    pass


class ToolExecutionError(JarvisException):
    """Tool execution failed."""
    pass


class ToolTimeoutError(ToolExecutionError):
    """Tool execution timed out."""
    pass


class ToolNotFoundError(ToolExecutionError):
    """Tool not found in registry."""
    pass


class LLMError(JarvisException):
    """LLM provider error."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timed out."""
    pass


class ValidationError(JarvisException):
    """Parameter validation failed."""
    pass


class MemoryError(JarvisException):
    """Memory management error."""
    pass
```

### 2️⃣ Resilience Module

```python
# src/jarvis/core/resilience.py
"""Resilience patterns for tool and LLM execution."""

import asyncio
import logging
import random
from typing import Any, Callable, TypeVar

from jarvis.core.exceptions import ToolTimeoutError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryPolicy:
    """Policy for retry logic."""

    def __init__(
        self,
        max_attempts: int = 3,
        backoff_factor: float = 2.0,
        initial_delay: float = 0.5,
        max_delay: float = 60.0,
        jitter: bool = True,
    ):
        """
        Initialize retry policy.

        Args:
            max_attempts: Maximum number of attempts
            backoff_factor: Exponential backoff factor
            initial_delay: Initial delay between retries
            max_delay: Maximum delay between retries
            jitter: Add random jitter to delays
        """
        self.max_attempts = max_attempts
        self.backoff_factor = backoff_factor
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = min(self.initial_delay * (self.backoff_factor ** attempt), self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if should retry given exception."""
        # Retry on timeout and connection errors
        retryable_exceptions = (
            asyncio.TimeoutError,
            ConnectionError,
            TimeoutError,
        )
        return isinstance(exception, retryable_exceptions) and attempt < self.max_attempts


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to call
        *args: Positional arguments
        policy: RetryPolicy (default: standard policy)
        **kwargs: Keyword arguments

    Returns:
        Function result

    Raises:
        Last exception if all retries exhausted
    """
    policy = policy or RetryPolicy()
    last_exception = None

    for attempt in range(policy.max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if not policy.should_retry(e, attempt):
                raise
            if attempt < policy.max_attempts - 1:
                delay = policy.get_delay(attempt)
                logger.warning(
                    f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}"
                )
                await asyncio.sleep(delay)

    raise last_exception


class TimeoutContext:
    """Context manager for timeouts."""

    def __init__(self, timeout: float):
        """
        Initialize timeout context.

        Args:
            timeout: Timeout in seconds
        """
        self.timeout = timeout
        self._task = None

    async def __aenter__(self):
        """Enter async context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if exc_type is asyncio.TimeoutError:
            raise ToolTimeoutError(f"Operation timed out after {self.timeout}s")

    async def run(self, coro):
        """Run coroutine with timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=self.timeout)
        except asyncio.TimeoutError as e:
            raise ToolTimeoutError(f"Operation timed out after {self.timeout}s") from e
```

### 3️⃣ Updated Orchestrator with Error Handling

```python
# src/jarvis/core/orchestrator.py (updated section)
"""Main Orchestrator with error handling."""

# ... imports ...
from jarvis.core.exceptions import (
    ToolExecutionError,
    ToolNotFoundError,
    LLMError,
)
from jarvis.core.resilience import retry_async, RetryPolicy

# ... rest of file ...

async def run(self, task: str) -> str:
    """
    Run orchestrator with error handling.

    Args:
        task: Task description

    Returns:
        Execution result
    """
    iteration = 0

    try:
        for iteration in range(self.max_iterations):
            logger.debug(f"ReAct iteration {iteration + 1}/{self.max_iterations}")

            # Get messages and add task
            messages = self.memory.get_all_messages()
            if not messages:
                messages.append({"role": "user", "content": task})

            try:
                # Call LLM with retry
                response = await retry_async(
                    self.llm.complete,
                    messages=messages,
                    policy=RetryPolicy(max_attempts=2),
                )

            except Exception as e:
                logger.error(f"LLM error on iteration {iteration}: {e}")
                if iteration == self.max_iterations - 1:
                    return "Could not complete task due to LLM errors."
                continue

            # Add LLM response to memory
            self.memory.add_message("assistant", response.content)

            # Process tool calls if any
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    try:
                        # Validate tool exists
                        tool = self.tool_registry.get(tool_call.name)
                        if not tool:
                            error = f"Tool '{tool_call.name}' not found"
                            logger.error(error)
                            self.memory.add_message(
                                "system",
                                f"Error: {error}",
                            )
                            continue

                        # Execute tool with timeout
                        result = await asyncio.wait_for(
                            self.executor.execute_tool(
                                tool_call.name,
                                tool_call.arguments,
                            ),
                            timeout=30.0,
                        )

                        # Add result to memory
                        self.memory.add_message(
                            "tool",
                            f"{tool_call.name}: {result.output}",
                        )

                    except asyncio.TimeoutError:
                        error_msg = f"Tool '{tool_call.name}' execution timed out"
                        logger.error(error_msg)
                        self.memory.add_message("system", f"Error: {error_msg}")

                    except ToolExecutionError as e:
                        logger.error(f"Tool execution error: {e}")
                        self.memory.add_message("system", f"Error: {e}")

                    except Exception as e:
                        logger.error(f"Unexpected tool error: {e}")
                        self.memory.add_message("system", f"Unexpected error: {e}")

            # Check if task completed (heuristic)
            if "completed" in response.content.lower() or "done" in response.content.lower():
                return response.content

    except KeyboardInterrupt:
        logger.info("Execution interrupted by user")
        return "Execution interrupted."

    except Exception as e:
        logger.critical(f"Orchestrator error: {e}")
        return f"Critical error occurred: {e}"

    return f"Completed after {iteration + 1} iterations"
```

---

## Structured Logging

### 1️⃣ Logging Configuration

```python
# src/jarvis/observability/logging.py
"""Structured logging configuration."""

import logging
import logging.config
from typing import Any

import structlog


def setup_logging(level: str = "INFO", json_output: bool = False):
    """
    Setup structured logging with structlog.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: Output as JSON (for production)
    """
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.extend([
            structlog.dev.ConsoleRenderer(),
        ])

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.basicConfig(
        level=level,
        format="%(message)s",
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
```

### 2️⃣ Metrics Module

```python
# src/jarvis/observability/metrics.py
"""Prometheus metrics for Jarvis."""

from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from typing import Any, Callable

# Tool metrics
tool_executions = Counter(
    "jarvis_tool_executions_total",
    "Total tool executions",
    ["tool_name", "status"],
)

tool_execution_duration = Histogram(
    "jarvis_tool_execution_duration_seconds",
    "Tool execution duration",
    ["tool_name"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
)

# LLM metrics
llm_requests = Counter(
    "jarvis_llm_requests_total",
    "Total LLM requests",
    ["provider", "status"],
)

llm_request_duration = Histogram(
    "jarvis_llm_request_duration_seconds",
    "LLM request duration",
    ["provider"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0),
)

llm_tokens_used = Counter(
    "jarvis_llm_tokens_used_total",
    "Total LLM tokens used",
    ["provider"],
)

# Memory metrics
memory_messages = Gauge(
    "jarvis_memory_messages_count",
    "Number of messages in memory",
)

memory_size_bytes = Gauge(
    "jarvis_memory_size_bytes",
    "Memory usage in bytes",
)

# Orchestrator metrics
orchestrator_iterations = Counter(
    "jarvis_orchestrator_iterations_total",
    "Total orchestrator iterations",
)

orchestrator_active_tasks = Gauge(
    "jarvis_orchestrator_active_tasks",
    "Active orchestrator tasks",
)


def track_tool_execution(tool_name: str):
    """Decorator to track tool execution metrics."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                status = "success" if result.success else "failure"
                tool_executions.labels(tool_name=tool_name, status=status).inc()
                tool_execution_duration.labels(tool_name=tool_name).observe(duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                tool_executions.labels(tool_name=tool_name, status="error").inc()
                tool_execution_duration.labels(tool_name=tool_name).observe(duration)
                raise
        return wrapper
    return decorator


def track_llm_request(provider: str):
    """Decorator to track LLM request metrics."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                llm_requests.labels(provider=provider, status="success").inc()
                llm_request_duration.labels(provider=provider).observe(duration)
                
                if hasattr(result, 'tokens_used') and result.tokens_used:
                    llm_tokens_used.labels(provider=provider).inc(result.tokens_used)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                llm_requests.labels(provider=provider, status="error").inc()
                llm_request_duration.labels(provider=provider).observe(duration)
                raise
        return wrapper
    return decorator
```

### 3️⃣ Usage in Orchestrator

```python
# src/jarvis/core/orchestrator.py (updated with logging)
"""Orchestrator with structured logging."""

from jarvis.observability.logging import get_logger
from jarvis.observability.metrics import (
    track_tool_execution,
    track_llm_request,
    orchestrator_iterations,
)

logger = get_logger("jarvis.orchestrator")


async def run(self, task: str) -> str:
    """Run with detailed logging."""
    
    logger.info(
        "orchestrator_start",
        task_length=len(task),
        max_iterations=self.max_iterations,
    )

    for iteration in range(self.max_iterations):
        orchestrator_iterations.inc()
        
        logger.debug(
            "iteration_start",
            iteration=iteration,
            total_iterations=self.max_iterations,
        )

        try:
            response = await self.llm.complete(messages)
            
            logger.info(
                "llm_response_received",
                tool_calls=len(response.tool_calls),
                content_length=len(response.content),
            )

            for tool_call in response.tool_calls:
                logger.info(
                    "tool_call_start",
                    tool_name=tool_call.name,
                    iteration=iteration,
                )

                result = await self.executor.execute_tool(...)
                
                logger.info(
                    "tool_call_complete",
                    tool_name=tool_call.name,
                    success=result.success,
                    iteration=iteration,
                )

        except Exception as e:
            logger.error(
                "orchestrator_error",
                error=str(e),
                error_type=type(e).__name__,
                iteration=iteration,
            )
            raise

    logger.info(
        "orchestrator_complete",
        total_iterations=iteration + 1,
    )
    return result
```

---

## Smart Memory Management

```python
# src/jarvis/memory/smart_memory.py
"""Smart memory with compression and context management."""

import logging
from typing import Any

from jarvis.llm import LLMProvider
from jarvis.memory.conversation import Message, ConversationMemory

logger = logging.getLogger(__name__)


class SmartConversationMemory(ConversationMemory):
    """
    Memory management with:
    - Max message limit
    - Automatic compression
    - Relevant context retrieval
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        max_messages: int = 100,
        compression_threshold: int = 50,
    ):
        """
        Initialize smart memory.

        Args:
            llm_provider: LLM for summarization
            max_messages: Maximum number of messages
            compression_threshold: Trigger compression at this count
        """
        super().__init__()
        self.llm_provider = llm_provider
        self.max_messages = max_messages
        self.compression_threshold = compression_threshold

    async def add_message(self, role: str, content: str) -> None:
        """Add message with auto-compression."""
        super().add_message(role, content)

        if len(self.messages) > self.compression_threshold and self.llm_provider:
            logger.info(f"Compressing memory ({len(self.messages)} messages)")
            await self.compress_old_messages()

        if len(self.messages) > self.max_messages:
            logger.warning(f"Memory exceeded max ({len(self.messages)}/{self.max_messages})")
            self.messages = self.messages[-self.max_messages :]

    async def compress_old_messages(self, keep_recent: int = 10) -> None:
        """
        Compress old messages using LLM summarization.

        Args:
            keep_recent: Keep this many recent messages
        """
        if not self.llm_provider or len(self.messages) <= keep_recent:
            return

        old_messages = self.messages[:-keep_recent]
        recent_messages = self.messages[-keep_recent:]

        # Prepare content for summarization
        conversation_text = "\n".join(
            f"{msg.role.upper()}: {msg.content}"
            for msg in old_messages
        )

        try:
            # Use LLM to summarize
            summary_prompt = f"Summarize this conversation:\n{conversation_text}"

            response = await self.llm_provider.complete(
                messages=[{"role": "user", "content": summary_prompt}]
            )

            # Replace old messages with summary
            self.messages = [
                Message(role="system", content=f"SUMMARY: {response.content}"),
                *recent_messages,
            ]

            logger.info(f"Memory compressed to {len(self.messages)} messages")

        except Exception as e:
            logger.error(f"Failed to compress memory: {e}")

    def get_relevant_context(
        self,
        task: str,
        limit: int = 10,
    ) -> list[Message]:
        """
        Get only relevant messages for current task.

        Simple heuristic: return recent messages + any matching keywords.

        Args:
            task: Current task
            limit: Max messages to return

        Returns:
            Filtered message list
        """
        relevant = []

        # Always include recent messages
        for msg in self.messages[-5:]:
            relevant.append(msg)

        # Search for keyword matches
        task_keywords = set(task.lower().split())
        for msg in self.messages[:-5]:
            msg_keywords = set(msg.content.lower().split())
            if task_keywords & msg_keywords:
                relevant.append(msg)

        # Limit and return
        return relevant[-limit:]
```

---

## Caching Layer

```python
# src/jarvis/core/cache.py
"""Tool result caching with TTL and invalidation."""

import logging
import time
from typing import Any
import hashlib
import json

from jarvis.tools.base import ToolResult

logger = logging.getLogger(__name__)


class CacheEntry:
    """Single cache entry with TTL."""

    def __init__(self, result: ToolResult, ttl: int = 3600):
        """
        Initialize cache entry.

        Args:
            result: Tool result to cache
            ttl: Time to live in seconds
        """
        self.result = result
        self.ttl = ttl
        self.created_at = time.time()

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl


class ToolResultCache:
    """Cache tool results with TTL and pattern-based invalidation."""

    def __init__(self, max_size: int = 1000):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of cached results
        """
        self.max_size = max_size
        self._cache: dict[str, CacheEntry] = {}
        logger.info(f"Cache initialized (max_size={max_size})")

    def _make_key(self, tool_name: str, params: dict[str, Any]) -> str:
        """Generate cache key from tool name and parameters."""
        # Sort params for consistent key generation
        params_json = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_json.encode()).hexdigest()
        return f"{tool_name}:{params_hash}"

    def get(self, tool_name: str, params: dict[str, Any]) -> ToolResult | None:
        """
        Get cached result.

        Args:
            tool_name: Tool name
            params: Tool parameters

        Returns:
            Cached result or None
        """
        key = self._make_key(tool_name, params)

        if key not in self._cache:
            return None

        entry = self._cache[key]
        if entry.is_expired():
            del self._cache[key]
            return None

        logger.info(f"Cache hit: {tool_name}")
        return entry.result

    def set(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: ToolResult,
        ttl: int = 3600,
    ) -> None:
        """
        Cache a result.

        Args:
            tool_name: Tool name
            params: Tool parameters
            result: Result to cache
            ttl: Time to live in seconds
        """
        # Don't cache failures
        if not result.success:
            return

        key = self._make_key(tool_name, params)

        # Enforce max size
        if len(self._cache) >= self.max_size:
            self._evict_lru()

        self._cache[key] = CacheEntry(result, ttl)
        logger.info(f"Cache set: {tool_name}")

    def invalidate(self, tool_name: str, pattern: str | None = None) -> int:
        """
        Invalidate cache entries.

        Args:
            tool_name: Tool name pattern
            pattern: Parameter pattern to match

        Returns:
            Number of entries invalidated
        """
        prefix = f"{tool_name}:"
        count = 0

        for key in list(self._cache.keys()):
            if key.startswith(prefix):
                del self._cache[key]
                count += 1

        logger.info(f"Invalidated {count} cache entries")
        return count

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.info("Cache cleared")

    def _evict_lru(self) -> None:
        """Evict least recently used entry (oldest)."""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at,
        )
        del self._cache[oldest_key]
        logger.debug(f"Evicted LRU entry: {oldest_key}")
```

---

## Summary

Эти модули обеспечивают:

✅ **Tool Discovery** - автоматическое обнаружение инструментов  
✅ **Error Handling** - retry logic, graceful degradation, specific exceptions  
✅ **Structured Logging** - observability для production  
✅ **Smart Memory** - управление контекстом, сжатие сообщений  
✅ **Caching** - улучшение производительности

**Порядок реализации:**
1. Tool Discovery (блокирующая для новых разработчиков)
2. Error Handling (критическое для reliability)
3. Structured Logging (важное для production)
4. Smart Memory (оптимизация для длинных диалогов)
5. Caching (performance boost)

