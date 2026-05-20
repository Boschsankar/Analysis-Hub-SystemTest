"""Streamlit landing page for the Smart Meter analysis tools."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType

import streamlit as st


@dataclass(frozen=True)
class ToolConfig:
    title: str
    module: str
    accent: str
    description: str
    button_label: str


TOOLS: tuple[ToolConfig, ...] = (
    ToolConfig(
        title="GW Data Analysis",
        module="_pages.gw_data_analysis",
        accent="#2e7d32",
        description="Gateway SoC, supply-source, phase, and location insights.",
        button_label="Open GW Analysis",
    ),
    ToolConfig(
        title="ESW Flag Control",
        module="_pages.esw_flag_control",
        accent="#1565c0",
        description="Inspect and modify critical ESW payload bits.",
        button_label="Open ESW Control",
    ),
    ToolConfig(
        title="Daily Data Analysis",
        module="_pages.daily_data_analysis",
        accent="#ef6c00",
        description="Review daily smart-meter status and data quality.",
        button_label="Open Daily Analysis",
    ),
    ToolConfig(
        title="Weekly Data Analysis",
        module="_pages.weekly_data_analysis",
        accent="#6a1b9a",
        description="Summarize weekly trends, gaps, and report health.",
        button_label="Open Weekly Analysis",
    ),
)

DEFAULT_STATUS = {"imported": False, "message": "", "opened": False}


def configure_page() -> None:
    st.set_page_config(page_title="Smart Meter Analysis Hub", layout="wide")
    st.markdown(
        """
        <style>
            .tool-card {
                border-left: 5px solid var(--accent-color);
                padding: 0.25rem 0 0.15rem 0.35rem;
                min-height: 118px;
            }
            .tool-card h3 {
                margin: 0 0 0.35rem;
                font-size: 1.05rem;
                font-weight: 700;
                letter-spacing: 0;
            }
            .tool-card p {
                margin: 0;
                color: #475569;
                font-size: 0.92rem;
                line-height: 1.35;
            }
            .status-pill {
                display: inline-block;
                margin-bottom: 0.55rem;
                padding: 0.16rem 0.55rem;
                border-radius: 999px;
                background: #f1f5f9;
                color: #334155;
                font-size: 0.78rem;
                font-weight: 700;
            }
            .status-pill.running {
                background: #dcfce7;
                color: #166534;
            }
            .status-pill.available {
                background: #dbeafe;
                color: #1d4ed8;
            }
            .status-pill.issue {
                background: #fee2e2;
                color: #991b1b;
            }
            .tool-banner {
                color: white;
                padding: 0.85rem 1rem;
                border-radius: 8px;
                margin-bottom: 0.75rem;
            }
            .tool-banner h3 {
                margin: 0;
                font-size: 1.1rem;
                font-weight: 700;
                letter-spacing: 0;
            }
            .tool-banner p {
                margin: 0.25rem 0 0;
                opacity: 0.95;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def rerun_app() -> None:
    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun:
        rerun()


def init_tool_status() -> None:
    if "tool_status" not in st.session_state:
        st.session_state.tool_status = {}
    if "selected_tool" not in st.session_state:
        st.session_state.selected_tool = TOOLS[0].title

    for tool in TOOLS:
        status = st.session_state.tool_status.setdefault(tool.module, DEFAULT_STATUS.copy())
        if "message" not in status:
            status["message"] = status.pop("msg", "")
        if "imported" not in status:
            status["imported"] = False
        if "opened" not in status:
            status["opened"] = False


def import_module_safe(module_name: str) -> tuple[ModuleType | None, str | None]:
    try:
        return importlib.import_module(module_name), None
    except Exception as exc:
        return None, f"{module_name} import failed: {exc}"


def run_tool(module: ModuleType, module_name: str) -> str | None:
    for entrypoint in ("run", "main"):
        callback = getattr(module, entrypoint, None)
        if callable(callback):
            try:
                callback()
                return None
            except Exception as exc:
                return f"{module_name}.{entrypoint} failed: {exc}"

    return f"{module_name} does not expose a callable run() or main()."


def update_status(
    module_name: str,
    imported: bool,
    message: str = "",
    opened: bool | None = None,
) -> None:
    current = st.session_state.tool_status.get(module_name, DEFAULT_STATUS.copy())
    st.session_state.tool_status[module_name] = {
        "imported": imported,
        "message": message,
        "opened": current["opened"] if opened is None else opened,
    }


def show_status(module_name: str) -> None:
    status = st.session_state.tool_status[module_name]
    if status["message"]:
        st.error(status["message"])
    elif status["opened"]:
        st.success("Running")
    elif status["imported"]:
        st.success("Available")
    else:
        st.info("Not checked")


def get_status_label(module_name: str) -> tuple[str, str]:
    status = st.session_state.tool_status[module_name]
    if status["message"]:
        return "Issue", "issue"
    if status["opened"]:
        return "Running", "running"
    if status["imported"]:
        return "Available", "available"
    return "Not checked", ""


def render_tool_switcher() -> ToolConfig:
    st.subheader("Tool Workspace")
    st.caption("Select a tool card to view, validate, or launch its dashboard.")

    cols = st.columns(4)
    for col, tool in zip(cols, TOOLS):
        label, status_class = get_status_label(tool.module)
        selected = st.session_state.selected_tool == tool.title
        button_label = "Selected" if selected else "View"
        with col:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="tool-card" style="--accent-color:{tool.accent};">
                        <span class="status-pill {status_class}">{label}</span>
                        <h3>{tool.title}</h3>
                        <p>{tool.description}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    button_label,
                    key=f"select_{tool.module}",
                    disabled=selected,
                    use_container_width=True,
                ):
                    st.session_state.selected_tool = tool.title
                    rerun_app()

    return next(tool for tool in TOOLS if tool.title == st.session_state.selected_tool)


def render_tool(tool: ToolConfig) -> None:
    status = st.session_state.tool_status[tool.module]
    st.markdown(
        f"""
        <div class="tool-banner" style="background:{tool.accent};">
            <h3>{tool.title}</h3>
            <p>{tool.description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    show_status(tool.module)

    launch_col, close_col = st.columns([1, 1])
    with launch_col:
        launch_clicked = st.button(
            tool.button_label,
            key=f"open_{tool.module}",
            disabled=status["opened"],
            use_container_width=True,
        )
    with close_col:
        close_clicked = st.button(
            "Close Tool",
            key=f"close_{tool.module}",
            disabled=not status["opened"],
            use_container_width=True,
        )

    if close_clicked:
        update_status(tool.module, False, opened=False)
        rerun_app()

    if launch_clicked:
        module, import_error = import_module_safe(tool.module)
        if import_error:
            update_status(tool.module, False, import_error, opened=False)
            st.error(import_error)
            return

        update_status(tool.module, True, opened=True)
        rerun_app()

    if not st.session_state.tool_status[tool.module]["opened"]:
        st.caption("Launch this tool to load its dashboard in the current view.")
        return

    module, import_error = import_module_safe(tool.module)
    if import_error:
        update_status(tool.module, False, import_error, opened=False)
        st.error(import_error)
        return

    update_status(tool.module, True, opened=True)
    execution_error = run_tool(module, tool.module)
    if execution_error:
        update_status(tool.module, False, execution_error, opened=False)
        st.error(execution_error)


def render_header() -> None:
    imported_count = sum(
        1 for status in st.session_state.tool_status.values() if status["imported"]
    )
    issue_count = sum(
        1 for status in st.session_state.tool_status.values() if status["message"]
    )

    st.title("Smart Meter Analysis Hub")
    st.caption("Central workspace for opening smart-meter analysis tools on demand.")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Available Tools", len(TOOLS))
    metric_cols[1].metric("Validated Tools", imported_count)
    metric_cols[2].metric("Tool Issues", issue_count)
    metric_cols[3].metric("Last Refreshed", datetime.now().strftime("%d-%m-%Y %H:%M"))


def import_all_tools() -> None:
    for tool in TOOLS:
        _, import_error = import_module_safe(tool.module)
        update_status(tool.module, import_error is None, import_error or "")


def reset_tool_status() -> None:
    for tool in TOOLS:
        update_status(tool.module, False, opened=False)


def main() -> None:
    configure_page()
    init_tool_status()
    render_header()

    st.divider()
    selected_tool = render_tool_switcher()
    st.divider()
    render_tool(selected_tool)

    st.divider()
    left, right = st.columns(2)
    with left:
        if st.button("Check Tool Status", use_container_width=True):
            import_all_tools()
            rerun_app()
    with right:
        if st.button("Reset Tool Status", use_container_width=True):
            reset_tool_status()
            rerun_app()


if __name__ == "__main__":
    main()
