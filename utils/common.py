"""
Common utilities and UI widgets for Smart Meter Analysis tools.
"""

from __future__ import annotations

import streamlit as st
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def file_upload_widget(label: str = "Upload file", types: List[str] = None) -> Any:
    """
    Generic file uploader widget with error handling.
    
    Args:
        label: Label for the uploader
        types: Allowed file types
    
    Returns:
        Uploaded file or None
    """
    if types is None:
        types = ["xlsx", "csv", "log", "txt"]
    
    try:
        return st.file_uploader(label, type=types)
    except Exception as e:
        st.error(f"File upload error: {str(e)}")
        logger.error(f"File upload failed: {e}")
        return None


def kpi_widgets(summary_counts: Dict[str, Any]) -> None:
    """
    Render KPI metrics in a row.
    
    Args:
        summary_counts: Dictionary with KPI values
    """
    if not summary_counts:
        st.warning("No KPI data available")
        return
    
    try:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            col1.metric("Expected", summary_counts.get("Expected Count", 0))
        with col2:
            col2.metric("Achieved", summary_counts.get("Achieved Count", 0))
        with col3:
            col3.metric("Missing", summary_counts.get("Missing Count", 0))
        with col4:
            col4.metric("Unexpected", summary_counts.get("Unexpected Count", 0))
        with col5:
            col5.metric("Achieved %", f"{summary_counts.get('Achieved %', 0)}%")
    except Exception as e:
        st.error(f"KPI rendering error: {str(e)}")
        logger.error(f"KPI rendering failed: {e}")


def chart_summary(status_summary: Any) -> None:
    """
    Show bar and pie chart for status distribution.
    
    Args:
        status_summary: DataFrame with status data
    """
    if status_summary is None or status_summary.empty:
        st.warning("No chart data available")
        return
    
    try:
        colA, colB = st.columns(2)
        with colA:
            st.bar_chart(status_summary)
        with colB:
            st.pyplot(status_summary.plot.pie(y="Count", autopct="%1.1f%%").figure)
    except Exception as e:
        st.error(f"Chart rendering error: {str(e)}")
        logger.error(f"Chart rendering failed: {e}")


def render_tool_card(
    title: str,
    description: str,
    accent_color: str,
    status: str = "available",
    on_click: Optional[callable] = None,
) -> None:
    """
    Render a tool card with title, description, and status.
    
    Args:
        title: Tool title
        description: Tool description
        accent_color: Color for the card accent
        status: Status badge text
        on_click: Callback function on button click
    """
    try:
        st.markdown(
            f"""
            <div style="border-left: 5px solid {accent_color}; padding: 1rem; margin: 1rem 0; border-radius: 0.5rem; background-color: #f9f9f9;">
                <h3 style="margin-top: 0;">{title}</h3>
                <p>{description}</p>
                <small style="color: #666;">{status}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.error(f"Card rendering error: {str(e)}")
        logger.error(f"Card rendering failed: {e}")


__all__ = [
    "file_upload_widget",
    "kpi_widgets",
    "chart_summary",
    "render_tool_card",
]
