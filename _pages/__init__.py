"""
Smart Meter Analysis Tools Package
Unified integration framework for all analysis modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, List, Any
import logging

# Configure logging
logger = logging.getLogger(__name__)


class ToolStatus(Enum):
    """Enum for tool status states."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class ToolMetadata:
    """Metadata for a single tool."""
    title: str
    module_path: str
    accent_color: str
    description: str
    button_label: str
    category: str = "analysis"
    version: str = "1.0.0"
    dependencies: List[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            object.__setattr__(self, 'dependencies', [])


class ToolRegistry:
    """Unified registry for all Smart Meter analysis tools."""
    
    def __init__(self):
        """Initialize the tool registry."""
        self._tools: Dict[str, ToolMetadata] = {}
        self._runners: Dict[str, Callable] = {}
        self._status: Dict[str, ToolStatus] = {}
        self._errors: Dict[str, str] = {}
    
    def register(self, tool_id: str, metadata: ToolMetadata, runner: Callable = None) -> None:
        """Register a new tool with the registry."""
        if tool_id in self._tools:
            logger.warning(f"Tool '{tool_id}' already registered. Overwriting.")
        self._tools[tool_id] = metadata
        if runner:
            self._runners[tool_id] = runner
        self._status[tool_id] = ToolStatus.AVAILABLE
        logger.info(f"Tool '{tool_id}' registered successfully.")
    
    def get_tool(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get tool metadata by ID."""
        return self._tools.get(tool_id)
    
    def get_all_tools(self) -> Dict[str, ToolMetadata]:
        """Get all registered tools."""
        return self._tools.copy()
    
    def get_runner(self, tool_id: str) -> Optional[Callable]:
        """Get the runner function for a tool."""
        return self._runners.get(tool_id)
    
    def set_status(self, tool_id: str, status: ToolStatus, error: str = "") -> None:
        """Update tool status."""
        if tool_id in self._tools:
            self._status[tool_id] = status
            if error:
                self._errors[tool_id] = error
            logger.debug(f"Tool '{tool_id}' status set to {status.value}")
    
    def get_status(self, tool_id: str) -> ToolStatus:
        """Get tool status."""
        return self._status.get(tool_id, ToolStatus.UNAVAILABLE)
    
    def get_error(self, tool_id: str) -> str:
        """Get error message for a tool."""
        return self._errors.get(tool_id, "")
    
    def is_available(self, tool_id: str) -> bool:
        """Check if tool is available."""
        return self.get_status(tool_id) == ToolStatus.AVAILABLE


# Global registry instance
REGISTRY = ToolRegistry()


def register_tool(tool_id: str, metadata: ToolMetadata, runner: Callable = None) -> Callable:
    """Decorator for registering tools."""
    def decorator(func: Callable) -> Callable:
        REGISTRY.register(tool_id, metadata, runner or func)
        return func
    return decorator


__all__ = [
    "ToolRegistry",
    "ToolMetadata",
    "ToolStatus",
    "REGISTRY",
    "register_tool",
]
