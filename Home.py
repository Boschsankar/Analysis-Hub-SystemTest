"""
Smart Meter Analysis Tools - Main Entry Point
Unified dashboard for all smart meter analysis utilities.
"""

from __future__ import annotations

import logging
import sys
import importlib
from typing import Optional, Tuple

import streamlit as st

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import integration framework
from _pages import ToolRegistry, ToolMetadata, ToolStatus, REGISTRY
from utils.dependencies import DEPENDENCY_MANAGER, validate_environment
from utils.platform_utils import PLATFORM_MANAGER
from utils.error_handler import ErrorHandler

# Tool definitions
TOOLS_METADATA = [
    ToolMetadata(
        title="GW Data Analysis",
        module_path="_pages.gw_data_analysis",
        accent_color="#2e7d32",
        description="Gateway SoC, supply-source, phase, and location insights.",
        button_label="Open GW Analysis",
        category="analysis",
        dependencies=["pandas", "plotly"],
    ),
    ToolMetadata(
        title="ESW Flag Control",
        module_path="_pages.esw_flag_control",
        accent_color="#1565c0",
        description="Inspect and modify critical ESW payload bits.",
        button_label="Open ESW Control",
        category="utilities",
    ),
    ToolMetadata(
        title="Daily Data Analysis",
        module_path="_pages.daily_data_analysis",
        accent_color="#ef6c00",
        description="Review daily smart-meter status and data quality.",
        button_label="Open Daily Analysis",
        category="analysis",
        dependencies=["pandas", "plotly"],
    ),
    ToolMetadata(
        title="Weekly Data Analysis",
        module_path="_pages.weekly_data_analysis",
        accent_color="#6a1b9a",
        description="Summarize weekly trends, gaps, and report health.",
        button_label="Open Weekly Analysis",
        category="analysis",
        dependencies=["pandas", "plotly"],
    ),
    ToolMetadata(
        title="Block Data Validation",
        module_path="_pages.block_data_validation_1p_hpl",
        accent_color="#b71c1c",
        description="Validate block OBIS registers against expected load profiles.",
        button_label="Open Block Validator",
        category="validation",
        dependencies=["pandas", "plotly"],
    ),
]


def configure_page() -> None:
    """Configure Streamlit page settings and styling."""
    st.set_page_config(
        page_title="Smart Meter Analysis Hub",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.markdown(
        """
        <style>
            .tool-card {
                border-left: 5px solid var(--accent-color);
                padding: 1rem;
                margin: 0.5rem 0;
                border-radius: 0.5rem;
                background-color: #f9f9f9;
                transition: all 0.3s ease;
            }
            .tool-card:hover {
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                transform: translateX(4px);
            }
            .tool-card h3 {
                margin: 0 0 0.5rem;
                font-size: 1.2rem;
                font-weight: 700;
            }
            .tool-card p {
                margin: 0.25rem 0;
                color: #666;
                font-size: 0.95rem;
            }
            .status-badge {
                display: inline-block;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.85rem;
                font-weight: 600;
                margin-bottom: 0.5rem;
            }
            .status-available {
                background: #dbeafe;
                color: #1d4ed8;
            }
            .status-error {
                background: #fee2e2;
                color: #991b1b;
            }
            .header-banner {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 2rem;
                border-radius: 0.5rem;
                margin-bottom: 2rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_session_state() -> None:
    """Initialize Streamlit session state variables."""
    if "current_tool" not in st.session_state:
        st.session_state.current_tool = None
    if "tool_statuses" not in st.session_state:
        st.session_state.tool_statuses = {}
    if "env_validated" not in st.session_state:
        st.session_state.env_validated = False


def validate_environment_once() -> Tuple[bool, str]:
    """Validate the environment once per session."""
    if st.session_state.env_validated:
        return True, "Environment already validated."
    
    is_valid, message = validate_environment()
    st.session_state.env_validated = True
    
    return is_valid, message


def register_tools() -> None:
    """Register all tools with the registry."""
    for metadata in TOOLS_METADATA:
        try:
            REGISTRY.register(metadata.module_path, metadata)
            logger.info(f"Tool registered: {metadata.title}")
        except Exception as e:
            logger.error(f"Failed to register tool '{metadata.title}': {e}")
            REGISTRY.set_status(
                metadata.module_path,
                ToolStatus.ERROR,
                f"Registration failed: {e}"
            )


def import_and_run_tool(tool_metadata: ToolMetadata) -> Optional[str]:
    """
    Safely import and run a tool.
    
    Returns:
        Error message if failed, None if successful
    """
    try:
        # Import the module
        module = importlib.import_module(tool_metadata.module_path)
        
        # Find and call the run function
        run_func = getattr(module, "run", None)
        if not callable(run_func):
            error_msg = f"Module '{tool_metadata.module_path}' does not have a callable 'run()' function."
            logger.error(error_msg)
            return error_msg
        
        # Execute the tool
        run_func()
        REGISTRY.set_status(tool_metadata.module_path, ToolStatus.AVAILABLE)
        return None
    
    except ImportError as e:
        error_msg = f"Failed to import module: {e}"
        logger.error(error_msg)
        REGISTRY.set_status(tool_metadata.module_path, ToolStatus.ERROR, error_msg)
        return error_msg
    
    except Exception as e:
        error_msg = f"Tool execution failed: {e}"
        logger.error(error_msg)
        REGISTRY.set_status(tool_metadata.module_path, ToolStatus.ERROR, error_msg)
        return error_msg


def render_tool_card(metadata: ToolMetadata, col) -> None:
    """Render a tool card in the given column."""
    with col:
        status = REGISTRY.get_status(metadata.module_path)
        status_badge = "✅ Available" if status == ToolStatus.AVAILABLE else "⚠️ Check Dependencies"
        
        st.markdown(
            f"""
            <div class="tool-card" style="border-left-color: {metadata.accent_color};">
                <h3>{metadata.title}</h3>
                <p>{metadata.description}</p>
                <span class="status-badge status-available">{status_badge}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        if st.button(
            metadata.button_label,
            key=f"btn_{metadata.module_path}",
            use_container_width=True,
        ):
            st.session_state.current_tool = metadata.module_path


def show_home_page() -> None:
    """Display the home page with tool cards."""
    st.markdown(
        """
        <div class="header-banner">
            <h1>📊 Smart Meter Analysis Hub</h1>
            <p>Comprehensive smart meter data analysis tools for SLA monitoring, data validation, and insights</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # System Information
    with st.expander("ℹ️ System Information", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        platform_info = PLATFORM_MANAGER.get_platform_info()
        
        with col1:
            st.metric("Platform", PLATFORM_MANAGER.system)
        with col2:
            st.metric("Python", platform_info["python_version"])
        with col3:
            st.metric("Tools Available", len(REGISTRY.get_all_tools()))
        
        # Dependency status
        st.subheader("Dependencies Status")
        st.code(DEPENDENCY_MANAGER.get_status_report())
    
    # Tools Grid
    st.subheader("🛠️ Available Tools")
    
    tools = REGISTRY.get_all_tools()
    if not tools:
        st.warning("No tools registered. Please check the configuration.")
        return
    
    # Display tools in a grid
    cols = st.columns(3)
    for idx, (tool_id, metadata) in enumerate(tools.items()):
        col = cols[idx % 3]
        render_tool_card(metadata, col)


def show_tool_page() -> None:
    """Display the currently selected tool."""
    tool_id = st.session_state.current_tool
    metadata = REGISTRY.get_tool(tool_id)
    
    if not metadata:
        st.error("Tool not found in registry.")
        return
    
    # Create a back button
    if st.button("← Back to Home"):
        st.session_state.current_tool = None
        st.rerun()
    
    # Display tool header
    st.markdown(
        f"""
        <h1 style="color: {metadata.accent_color};">
            {metadata.title}
        </h1>
        <p>{metadata.description}</p>
        """,
        unsafe_allow_html=True,
    )
    
    # Run the tool
    with st.spinner(f"Loading {metadata.title}..."):
        error = import_and_run_tool(metadata)
        if error:
            st.error(f"Error running tool: {error}")
            st.info("Please check your dependencies and try again.")


def main() -> None:
    """Main application entry point."""
    configure_page()
    initialize_session_state()
    
    # Validate environment
    is_valid, env_msg = validate_environment_once()
    if not is_valid:
        st.error("Environment validation failed!")
        st.error(env_msg)
        st.stop()
    
    # Register tools
    register_tools()
    
    # Show home or tool page
    if st.session_state.current_tool:
        show_tool_page()
    else:
        show_home_page()


if __name__ == "__main__":
    main()
