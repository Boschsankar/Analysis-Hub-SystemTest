"""
Cross-Platform Utilities
Provides platform-agnostic wrappers for system-specific operations.
"""

from __future__ import annotations

import sys
import platform
import logging
import io
import os
import tempfile
from typing import Tuple, List, Optional, Any
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


class PlatformManager:
    """Manages platform-specific operations."""
    
    def __init__(self):
        """Initialize the platform manager."""
        self.system = platform.system().lower()
        self.is_windows = self.system == "windows"
        self.is_linux = self.system == "linux"
        self.is_mac = self.system == "darwin"
    
    def get_platform_info(self) -> dict:
        """Get current platform information."""
        return {
            "system": platform.system(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }


class EmailService:
    """Cross-platform email service with Windows Outlook support and fallback."""
    
    @staticmethod
    def send_outlook_email(
        to_email: str,
        subject: str,
        html_body: str,
        attachments: List[Tuple[str, bytes]] = None,
    ) -> Tuple[bool, str]:
        """
        Send email via Outlook (Windows only).
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: Email body in HTML format
            attachments: List of (filename, bytes) tuples
        
        Returns:
            Tuple of (success, message)
        """
        if not PLATFORM_MANAGER.is_windows:
            return False, f"Outlook email not available on {PLATFORM_MANAGER.system}. Use email_fallback()."
        
        try:
            import pythoncom
            import win32com.client as win32
        except ImportError as e:
            return False, f"Outlook dependencies not available: {e}. Please install pywin32."
        
        try:
            pythoncom.CoInitialize()
            outlook = win32.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To = to_email
            mail.Subject = subject
            mail.HTMLBody = html_body
            
            temp_paths = []

            # Add attachments with their intended filenames. Outlook uses the
            # temporary path basename as the displayed attachment name.
            if attachments:
                for filename, file_bytes in attachments:
                    safe_name = Path(str(filename)).name or f"attachment{Path(str(filename)).suffix}"
                    temp_dir = Path(tempfile.gettempdir()) / f"smartmeter_mail_{uuid4().hex}"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = temp_dir / safe_name
                    temp_path.write_bytes(file_bytes)
                    temp_paths.append(str(temp_path))
                    attachment = mail.Attachments.Add(str(temp_path))
                    if f"cid:{safe_name}" in html_body:
                        try:
                            attachment.PropertyAccessor.SetProperty(
                                "http://schemas.microsoft.com/mapi/proptag/0x3712001F",
                                safe_name,
                            )
                        except Exception as cid_error:
                            logger.warning("Unable to set inline content id for %s: %s", safe_name, cid_error)
            
            mail.Send()
            pythoncom.CoUninitialize()
            return True, "Email sent successfully via Outlook"
        
        except Exception as e:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            logger.error(f"Outlook email failed: {e}")
            return False, f"Outlook email failed: {e}"
    
    @staticmethod
    def send_email_fallback(
        to_email: str,
        subject: str,
        html_body: str,
        attachments: List[Tuple[str, bytes]] = None,
    ) -> Tuple[bool, str]:
        """
        Fallback email method using SMTP (cross-platform).
        Note: Requires SMTP configuration.
        """
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email.mime.text import MIMEText
            from email import encoders
        except ImportError:
            return False, "SMTP modules not available."
        
        try:
            # This is a placeholder. Implement with actual SMTP settings.
            logger.warning("SMTP fallback not fully configured. Please configure SMTP settings.")
            return False, "SMTP fallback not configured. Use Outlook or configure SMTP settings."
        except Exception as e:
            logger.error(f"SMTP email failed: {e}")
            return False, f"SMTP email failed: {e}"
    
    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        html_body: str,
        attachments: List[Tuple[str, bytes]] = None,
        use_outlook: bool = True,
    ) -> Tuple[bool, str]:
        """
        Send email with automatic fallback.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: Email body in HTML format
            attachments: List of (filename, bytes) tuples
            use_outlook: Try Outlook first (Windows)
        
        Returns:
            Tuple of (success, message)
        """
        if use_outlook and PLATFORM_MANAGER.is_windows:
            success, msg = EmailService.send_outlook_email(to_email, subject, html_body, attachments)
            if success:
                return True, msg
            logger.info(f"Outlook failed, trying SMTP fallback: {msg}")
        
        return EmailService.send_email_fallback(to_email, subject, html_body, attachments)


class FileManager:
    """Cross-platform file operations."""
    
    @staticmethod
    def create_temp_directory(prefix: str = "smartmeter") -> str:
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        logger.debug(f"Created temporary directory: {temp_dir}")
        return temp_dir
    
    @staticmethod
    def save_to_temp_file(content: bytes, suffix: str = ".xlsx") -> str:
        """Save bytes to a temporary file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp.flush()
            logger.debug(f"Saved temporary file: {tmp.name}")
            return tmp.name
    
    @staticmethod
    def get_home_directory() -> str:
        """Get user's home directory."""
        return str(Path.home())
    
    @staticmethod
    def safe_path_join(*parts: str) -> str:
        """Safely join path components."""
        return str(Path(*parts))


class ProcessManager:
    """Cross-platform process operations."""
    
    @staticmethod
    def open_file(filepath: str) -> Tuple[bool, str]:
        """Open a file with the default application."""
        filepath = str(Path(filepath).absolute())
        
        if not os.path.exists(filepath):
            return False, f"File not found: {filepath}"
        
        try:
            if PLATFORM_MANAGER.is_windows:
                import subprocess
                subprocess.Popen(f'start "{filepath}"', shell=True)
            elif PLATFORM_MANAGER.is_mac:
                import subprocess
                subprocess.Popen(["open", filepath])
            else:  # Linux
                import subprocess
                subprocess.Popen(["xdg-open", filepath])
            
            logger.info(f"Opened file: {filepath}")
            return True, f"File opened: {filepath}"
        
        except Exception as e:
            logger.error(f"Failed to open file: {e}")
            return False, f"Failed to open file: {e}"


# Global instances
PLATFORM_MANAGER = PlatformManager()
EMAIL_SERVICE = EmailService()
FILE_MANAGER = FileManager()
PROCESS_MANAGER = ProcessManager()


__all__ = [
    "PlatformManager",
    "EmailService",
    "FileManager",
    "ProcessManager",
    "PLATFORM_MANAGER",
    "EMAIL_SERVICE",
    "FILE_MANAGER",
    "PROCESS_MANAGER",
]
