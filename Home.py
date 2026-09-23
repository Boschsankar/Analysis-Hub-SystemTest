"""
Smart Meter Analysis Tools - Main Entry Point
Unified dashboard for all smart meter analysis utilities.
"""

from __future__ import annotations

import logging
import os
import sys
import importlib
from typing import Optional, Tuple

try:
    import streamlit as st
    _STREAMLIT_AVAILABLE = True
except Exception as _streamlit_err:  # noqa: F841
    st = None
    _STREAMLIT_AVAILABLE = False

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
    
    ToolMetadata(
    title="OD Performance Analytics",
    module_path="_pages.od_performance",
    accent_color="#00897b",
    description="Connect, Disconnect and OD command performance benchmarking with executive decision report.",
    button_label="Open OD Performance",
    category="analysis",
    dependencies=["pandas", "plotly", "openpyxl"],
    ),
    ToolMetadata(
        title="NMS HES Status Check",
        module_path="_pages.nms_hes_status_check",
        accent_color="#7c3aed",
        description="Monitor NMS vs HES health, communication drift, and healthy-percentage coverage.",
        button_label="Open NMS/HES Status Check",
        category="analysis",
        dependencies=["pandas", "numpy", "openpyxl"],
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
            html, body, [data-testid="stAppViewContainer"], .stApp {
                font-size: 15px !important;
                background: #f3f6fb;
            }

            .block-container {
                padding-top: 1rem;
                padding-left: 0.5rem;
                padding-right: 0.5rem;
                max-width: 100% !important;
                margin: 0;
            }

            .tool-card {
                border-left: 5px solid var(--accent-color);
                padding: 0.9rem 0.9rem 0.75rem;
                margin: 0.35rem 0;
                border-radius: 0.7rem;
                background-color: #ffffff;
                box-shadow: 0 1px 3px rgba(0,0,0,0.06);
                transition: all 0.2s ease;
                min-height: 160px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }
            .tool-card:hover {
                box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                transform: translateY(-2px);
            }
            .tool-card h3 {
                margin: 0 0 0.45rem;
                font-size: 1.1rem;
                font-weight: 700;
                line-height: 1.3;
            }
            .tool-card p {
                margin: 0.25rem 0 0.7rem;
                color: #555;
                font-size: 0.9rem;
                line-height: 1.45;
            }
            .status-badge {
                display: inline-block;
                padding: 0.28rem 0.7rem;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: 600;
                margin-bottom: 0.4rem;
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
                padding: 1.1rem 1.25rem;
                border-radius: 0.7rem;
                margin-bottom: 1rem;
            }
            .header-banner h1 {
                font-size: 1.8rem;
                margin-bottom: 0.2rem;
            }
            .header-banner p {
                font-size: 0.92rem;
                margin: 0;
            }
            div[data-testid="stSidebar"] {
                font-size: 0.95rem;
            }
            div[data-testid="stSidebarNav"] {
                padding-top: 0.5rem;
            }
            .stButton > button {
                height: 2.4rem;
                font-size: 0.9rem;
                padding: 0.45rem 0.8rem;
            }
            .stMetric {
                font-size: 0.95rem;
            }
            .stMetric > div {
                padding: 0.7rem 0.9rem;
            }
            .stDataFrame {
                font-size: 0.9rem;
            }
            .stSubheader {
                font-size: 1.05rem;
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
    
    # Display tools in a wide grid that fills the screen
    cols = st.columns(4)
    for idx, (tool_id, metadata) in enumerate(tools.items()):
        col = cols[idx % 4]
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
    # Home.py is intended to be run via Streamlit (streamlit run Home.py).
    # The environment-variable check is brittle and can fail even when Streamlit is
    # launching the script correctly. Run the app directly when Streamlit is available;
    # otherwise show a clear instruction for the supported launch methods.
    if _STREAMLIT_AVAILABLE:
        main()
    else:
        print("Please start the app using: streamlit run Home.py\nOr use the launcher: python run_app.py")
        sys.exit(1)
