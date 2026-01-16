"""Dynamic tool loading helpers.

This module loads tool classes from modules/config specs and instantiates them
safely with proper error handling.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, List, Optional, Type

from jarvis.tools.base import Tool

logger = logging.getLogger(__name__)


class ToolLoader:
    """Helper for dynamic tool imports and instantiation.
    
    Provides safe loading with validation and clear error messages.
    """

    def load_from_spec(self, spec: dict[str, Any]) -> Optional[Tool]:
        """Load a tool from a spec dictionary.
        
        Expected spec format:
        {
            "name": "tool_name",
            "module": "package.module",
            "class": "ToolClass",
            "kwargs": {"param": "value"}  # optional
        }
        
        Args:
            spec: Tool specification dictionary.
            
        Returns:
            Tool instance or None if loading failed.
        """
        try:
            module_name = spec.get("module")
            class_name = spec.get("class")
            kwargs = spec.get("kwargs", {})
            
            if not module_name or not class_name:
                logger.error(f"Invalid spec: missing module or class in {spec}")
                return None
                
            # Import module
            module = importlib.import_module(module_name)
            
            # Get class
            if not hasattr(module, class_name):
                logger.error(f"Class {class_name} not found in {module_name}")
                return None
                
            tool_class = getattr(module, class_name)
            
            # Validate it's a Tool subclass
            if not self.validate_tool_class(tool_class):
                logger.error(f"{class_name} is not a Tool subclass")
                return None
                
            # Instantiate
            tool = tool_class(**kwargs)
            logger.debug(f"Loaded tool '{tool.name}' from {module_name}.{class_name}")
            return tool
            
        except ImportError as e:
            logger.error(f"Failed to import module for spec {spec}: {e}")
        except Exception as e:
            logger.error(f"Failed to load tool from spec {spec}: {e}")
            
        return None

    def load_from_class(self, tool_class: Type[Tool], **kwargs: Any) -> Optional[Tool]:
        """Load a tool from a class reference.
        
        Args:
            tool_class: Tool class to instantiate.
            **kwargs: Constructor arguments.
            
        Returns:
            Tool instance or None if loading failed.
        """
        try:
            if not self.validate_tool_class(tool_class):
                logger.error(f"{tool_class} is not a Tool subclass")
                return None
                
            tool = tool_class(**kwargs)
            logger.debug(f"Loaded tool '{tool.name}' from class {tool_class.__name__}")
            return tool
            
        except Exception as e:
            logger.error(f"Failed to instantiate {tool_class.__name__}: {e}")
            return None

    def load_from_factory(self, factory: Callable[[], Tool]) -> Optional[Tool]:
        """Load a tool from a factory callable.
        
        Args:
            factory: Callable that returns a Tool instance.
            
        Returns:
            Tool instance or None if loading failed.
        """
        try:
            tool = factory()
            if not isinstance(tool, Tool):
                logger.error(f"Factory did not return Tool instance: {type(tool)}")
                return None
                
            logger.debug(f"Loaded tool '{tool.name}' from factory")
            return tool
            
        except Exception as e:
            logger.error(f"Factory failed to create tool: {e}")
            return None

    def load_from_module_file(self, file_path: str) -> List[Tool]:
        """Load all Tool subclasses from a Python module file.
        
        Args:
            file_path: Path to Python module file.
            
        Returns:
            List of Tool instances found in the module.
        """
        tools: List[Tool] = []
        
        try:
            path = Path(file_path)
            if not path.exists() or path.suffix != ".py":
                logger.error(f"Invalid Python file: {file_path}")
                return tools
                
            # Load module from file
            module_name = path.stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                logger.error(f"Failed to load spec from {file_path}")
                return tools
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find Tool subclasses
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if self.validate_tool_class(obj) and obj is not Tool:
                    try:
                        tool = obj()
                        tools.append(tool)
                        logger.debug(f"Loaded tool '{tool.name}' from {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to instantiate {name} from {file_path}: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to load module from {file_path}: {e}")
            
        return tools

    def validate_tool_class(self, cls: Type[Any]) -> bool:
        """Validate that the provided class is a Tool subclass.
        
        Args:
            cls: Class to validate.
            
        Returns:
            True if cls is a non-abstract Tool subclass.
        """
        try:
            return (
                inspect.isclass(cls)
                and issubclass(cls, Tool)
                and cls is not Tool
                and not inspect.isabstract(cls)
            )
        except Exception:
            return False

