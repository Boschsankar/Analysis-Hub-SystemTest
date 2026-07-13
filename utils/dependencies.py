"""
Dependency Management System
Handles cross-platform compatibility and dependency verification.
"""

from __future__ import annotations

import sys
import platform
import importlib
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Dependency:
    """Represents a package dependency."""
    name: str
    import_name: str
    min_version: Optional[str] = None
    optional: bool = False
    platforms: List[str] = None  # List of supported platforms: ["windows", "linux", "darwin"]
    
    def __post_init__(self):
        if self.platforms is None:
            self.platforms = ["windows", "linux", "darwin"]


class DependencyManager:
    """Manages package dependencies and compatibility checks."""
    
    # Core dependencies
    CORE_DEPENDENCIES = [
        Dependency("streamlit", "streamlit", "1.0.0"),
        Dependency("pandas", "pandas", "1.0.0"),
        Dependency("numpy", "numpy", "1.0.0"),
        Dependency("plotly", "plotly", "4.0.0"),
        Dependency("openpyxl", "openpyxl", "2.6.0"),
    ]
    
    # Optional dependencies
    OPTIONAL_DEPENDENCIES = [
        Dependency("altair", "altair", "4.0.0", optional=True),
        Dependency("matplotlib", "matplotlib", "3.0.0", optional=True),
        Dependency("seaborn", "seaborn", "0.10.0", optional=True),
        Dependency("pywin32", "win32com", optional=True, platforms=["windows"]),
        Dependency("python-dateutil", "dateutil", "2.8.0", optional=True),
    ]
    
    def __init__(self):
        """Initialize the dependency manager."""
        self._installed_packages: Dict[str, str] = {}
        self._missing_packages: Dict[str, str] = {}
        self._platform = platform.system().lower()
        self._python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    
    def check_core_dependencies(self) -> Tuple[bool, Dict[str, str]]:
        """Check if all core dependencies are available."""
        missing = {}
        for dep in self.CORE_DEPENDENCIES:
            if not self._check_dependency(dep):
                missing[dep.name] = f"Required: {dep.name}>={dep.min_version}"
        return len(missing) == 0, missing
    
    def check_optional_dependencies(self) -> Dict[str, bool]:
        """Check optional dependencies availability."""
        status = {}
        for dep in self.OPTIONAL_DEPENDENCIES:
            status[dep.name] = self._check_dependency(dep)
        return status
    
    def _check_dependency(self, dep: Dependency) -> bool:
        """Check if a single dependency is available."""
        # Check platform compatibility
        if dep.platforms and self._platform not in dep.platforms:
            logger.info(f"Dependency '{dep.name}' not compatible with {self._platform}. Skipping.")
            return False
        
        try:
            module = importlib.import_module(dep.import_name)
            version = getattr(module, "__version__", "unknown")
            self._installed_packages[dep.name] = version
            logger.debug(f"Dependency '{dep.name}' available (version: {version})")
            return True
        except ImportError as e:
            if not dep.optional:
                logger.error(f"Core dependency '{dep.name}' not found: {e}")
            else:
                logger.warning(f"Optional dependency '{dep.name}' not found: {e}")
            self._missing_packages[dep.name] = str(e)
            return False
        except Exception as e:
            logger.error(f"Error checking dependency '{dep.name}': {e}")
            return False
    
    def get_installed_packages(self) -> Dict[str, str]:
        """Get all installed packages and versions."""
        if not self._installed_packages:
            self.check_core_dependencies()
            self.check_optional_dependencies()
        return self._installed_packages
    
    def get_missing_packages(self) -> Dict[str, str]:
        """Get all missing packages."""
        if not self._missing_packages:
            self.check_core_dependencies()
            self.check_optional_dependencies()
        return self._missing_packages
    
    def get_status_report(self) -> str:
        """Generate a status report for all dependencies."""
        report = []
        report.append("=" * 60)
        report.append("DEPENDENCY STATUS REPORT")
        report.append("=" * 60)
        report.append(f"Platform: {self._platform}")
        report.append(f"Python Version: {self._python_version}")
        report.append("")
        
        installed = self.get_installed_packages()
        missing = self.get_missing_packages()
        
        if installed:
            report.append("INSTALLED PACKAGES:")
            for name, version in sorted(installed.items()):
                report.append(f"  ✓ {name}: {version}")
            report.append("")
        
        if missing:
            report.append("MISSING PACKAGES:")
            for name, error in sorted(missing.items()):
                report.append(f"  ✗ {name}: {error}")
            report.append("")
        
        report.append("=" * 60)
        return "\n".join(report)
    
    def get_system_info(self) -> Dict[str, str]:
        """Get system information."""
        return {
            "platform": self._platform,
            "python_version": self._python_version,
            "system": platform.platform(),
        }


# Global instance
DEPENDENCY_MANAGER = DependencyManager()


def validate_environment() -> Tuple[bool, str]:
    """Validate the execution environment."""
    is_valid, missing = DEPENDENCY_MANAGER.check_core_dependencies()
    
    if not is_valid:
        error_msg = "Missing core dependencies:\n" + "\n".join(
            f"  - {name}: {reason}" for name, reason in missing.items()
        )
        return False, error_msg
    
    return True, "Environment is valid. All core dependencies are available."


__all__ = [
    "Dependency",
    "DependencyManager",
    "DEPENDENCY_MANAGER",
    "validate_environment",
]
