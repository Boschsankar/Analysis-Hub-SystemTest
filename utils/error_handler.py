"""
Error Handling and Validation Framework
Provides consistent error handling and validation across all tools.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, TypeVar, Optional, Dict, List
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)
    
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0
    
    def get_message(self) -> str:
        """Get a formatted message of all errors and warnings."""
        lines = []
        
        if self.errors:
            lines.append("ERRORS:")
            for error in self.errors:
                lines.append(f"  ✗ {error}")
        
        if self.warnings:
            lines.append("WARNINGS:")
            for warning in self.warnings:
                lines.append(f"  ⚠ {warning}")
        
        return "\n".join(lines) if lines else "Validation passed."


class SmartMeterException(Exception):
    """Base exception for Smart Meter Analysis tools."""
    pass


class ValidationException(SmartMeterException):
    """Raised when validation fails."""
    pass


class DependencyException(SmartMeterException):
    """Raised when a dependency is missing or incompatible."""
    pass


class DataException(SmartMeterException):
    """Raised when data processing fails."""
    pass


class ConfigurationException(SmartMeterException):
    """Raised when configuration is invalid."""
    pass


class ErrorHandler:
    """Centralized error handling."""
    
    @staticmethod
    def handle_exception(
        exc: Exception,
        context: str = "",
        log_level: int = logging.ERROR,
        reraise: bool = False,
    ) -> None:
        """
        Handle an exception with logging.
        
        Args:
            exc: The exception to handle
            context: Additional context information
            log_level: Logging level to use
            reraise: Whether to re-raise the exception
        """
        error_msg = f"Exception in {context}: {str(exc)}" if context else str(exc)
        logger.log(log_level, error_msg)
        logger.debug(traceback.format_exc())
        
        if reraise:
            raise exc
    
    @staticmethod
    def safe_execute(
        func: Callable[..., T],
        *args,
        default: Any = None,
        context: str = "",
        **kwargs,
    ) -> T:
        """
        Safely execute a function with error handling.
        
        Args:
            func: Function to execute
            default: Default return value on error
            context: Context information for logging
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
        
        Returns:
            Function result or default value on error
        """
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            ErrorHandler.handle_exception(exc, context=context or func.__name__)
            return default
    
    @staticmethod
    def format_error(exc: Exception) -> str:
        """Format an exception for display."""
        return f"{type(exc).__name__}: {str(exc)}"


def handle_errors(
    context: str = "",
    default: Any = None,
    log_errors: bool = True,
) -> Callable:
    """
    Decorator for automatic error handling.
    
    Args:
        context: Context information for error messages
        default: Default return value on error
        log_errors: Whether to log errors
    
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                if log_errors:
                    ErrorHandler.handle_exception(
                        exc,
                        context=context or func.__name__,
                    )
                return default
        return wrapper
    return decorator


def validate_input(
    validators: Dict[str, Callable[[Any], bool]],
) -> Callable:
    """
    Decorator for input validation.
    
    Args:
        validators: Dict of {param_name: validation_function}
    
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Basic input validation
            for key, validator in validators.items():
                if key in kwargs:
                    if not validator(kwargs[key]):
                        raise ValidationException(
                            f"Validation failed for parameter '{key}' with value '{kwargs[key]}'"
                        )
            return func(*args, **kwargs)
        return wrapper
    return decorator


class DataValidator:
    """Validates data integrity and format."""
    
    @staticmethod
    def validate_dataframe(df: Any) -> ValidationResult:
        """Validate a pandas DataFrame."""
        result = ValidationResult(is_valid=True, errors=[])
        
        try:
            import pandas as pd
        except ImportError:
            result.add_error("pandas is not installed")
            return result
        
        if not isinstance(df, pd.DataFrame):
            result.add_error(f"Expected DataFrame, got {type(df).__name__}")
            return result
        
        if df.empty:
            result.add_warning("DataFrame is empty")
        
        if df.isnull().sum().sum() > 0:
            null_count = df.isnull().sum().sum()
            result.add_warning(f"DataFrame contains {null_count} null values")
        
        return result
    
    @staticmethod
    def validate_columns(df: Any, required_columns: List[str]) -> ValidationResult:
        """Validate that DataFrame has required columns."""
        result = ValidationResult(is_valid=True, errors=[])
        
        try:
            import pandas as pd
        except ImportError:
            result.add_error("pandas is not installed")
            return result
        
        if not isinstance(df, pd.DataFrame):
            result.add_error(f"Expected DataFrame, got {type(df).__name__}")
            return result
        
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            result.add_error(f"Missing required columns: {missing_columns}")
        
        return result
    
    @staticmethod
    def validate_file_path(filepath: str) -> ValidationResult:
        """Validate a file path."""
        result = ValidationResult(is_valid=True, errors=[])
        
        import os
        
        if not filepath:
            result.add_error("File path cannot be empty")
        elif not os.path.exists(filepath):
            result.add_error(f"File not found: {filepath}")
        elif not os.path.isfile(filepath):
            result.add_error(f"Path is not a file: {filepath}")
        
        return result


__all__ = [
    "ValidationResult",
    "SmartMeterException",
    "ValidationException",
    "DependencyException",
    "DataException",
    "ConfigurationException",
    "ErrorHandler",
    "DataValidator",
    "handle_errors",
    "validate_input",
]
