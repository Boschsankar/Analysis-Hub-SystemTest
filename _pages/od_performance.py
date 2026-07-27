"""
_pages/od_performance.py

HES On-Demand Performance Decision Dashboard
Integrated page module for Smart Meter Analysis Hub.

Optimised version:
- No __file__ usage
- Uses Path.cwd() for Analysis Hub compatibility
- Analysis runs only when user clicks Run Performance Analysis
- Excel read is cached
- Excel and HTML reports are prepared only on demand
- Trend charts are optional for better performance
- Meter SN + Retry + Duration shown on command trend graph points
"""

from __future__ import annotations

import io
import hashlib
from datetime import datetime
from pathlib import Path
from html import escape

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.io as pio


# =========================================================
# PAGE METADATA FOR ANALYSIS HUB
# =========================================================
PAGE_INFO = {
    "title": "OD Performance Analytics",
    "icon": "⚡",
    "category": "analysis",
    "owner": "HES",
}


# =========================================================
# SAFE PATH CONFIGURATION - NO __file__
# =========================================================
PROJECT_ROOT = Path.cwd()
REPORT_DIR = PROJECT_ROOT / "reports"


# =========================================================
# CSS
# =========================================================
def load_css() -> None:
    st.markdown(
        """
        <style>
            [data-testid="stMainBlockContainer"] {
                max-width: 92% !important;
                margin-left: auto !important;
                margin-right: auto !important;
                padding-top: 2rem !important;
                padding-bottom: 3rem !important;
            }

            .metric-card {
                background-color: #f8f9fa;
                border-radius: 10px;
                padding: 16px;
                border-left: 5px solid #0066cc;
                box-shadow: 0 2px 5px rgba(0,0,0,0.06);
                min-height: 115px;
            }

            .metric-card-success {
                background-color: #f0fff4;
                border-radius: 10px;
                padding: 16px;
                border-left: 5px solid #38a169;
                box-shadow: 0 2px 5px rgba(0,0,0,0.06);
                min-height: 115px;
            }

            .metric-card-warning {
                background-color: #fffaf0;
                border-radius: 10px;
                padding: 16px;
                border-left: 5px solid #dd6b20;
                box-shadow: 0 2px 5px rgba(0,0,0,0.06);
                min-height: 115px;
            }

            .metric-card-fail {
                background-color: #fff5f5;
                border-radius: 10px;
                padding: 16px;
                border-left: 5px solid #e53e3e;
                box-shadow: 0 2px 5px rgba(0,0,0,0.06);
                min-height: 115px;
            }

            .section-header {
                color: #1a202c;
                font-weight: 700;
                margin-top: 28px;
                margin-bottom: 16px;
                border-bottom: 2px solid #edf2f7;
                padding-bottom: 6px;
                font-size: 23px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# SESSION STATE
# =========================================================
def init_state() -> None:
    defaults = {
        "od_uploader_version": 0,
        "od_last_upload_signature": None,
        "od_analysis_ready": False,
        "od_processed_df": None,
        "od_upload_audit_rows": None,
        "od_excel_bytes": None,
        "od_html_text": None,
        "od_last_report_timestamp": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_analysis_widget_states() -> None:
    keys_to_clear = [
        "od_selected_meter_commands",
        "od_selected_meters",
        "od_reference_meter",
        "od_selected_trend_commands",
        "od_excel_bytes",
        "od_html_text",
        "od_last_report_timestamp",
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    st.session_state["od_analysis_ready"] = False
    st.session_state["od_processed_df"] = None
    st.session_state["od_upload_audit_rows"] = None


# =========================================================
# DATA HELPERS
# =========================================================
@st.cache_data(show_spinner=False)
def read_excel_cached(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(file_bytes))


def parse_duration_to_seconds(duration_value):
    if pd.isna(duration_value):
        return np.nan

    if isinstance(duration_value, pd.Timedelta):
        return duration_value.total_seconds()

    if isinstance(duration_value, (int, float, np.integer, np.floating)):
        return float(duration_value)

    duration_str = str(duration_value).strip()

    if duration_str in ["-", "", "nan", "NaN", "None"]:
        return np.nan

    try:
        parts = duration_str.split(":")

        if len(parts) == 3:
            h, m, s = parts
            return float(h) * 3600 + float(m) * 60 + float(s)

        if len(parts) == 2:
            m, s = parts
            return float(m) * 60 + float(s)

        return float(duration_str)

    except Exception:
        return np.nan


def safe_upper(value):
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_meter_serial(value):
    if pd.isna(value):
        return "UNKNOWN"

    return (
        str(value)
        .strip()
        .replace("\n", "")
        .replace("\t", "")
        .replace("\r", "")
        .upper()
    )


def parse_datetime_column(series):
    parsed = pd.to_datetime(
        series,
        format="%d-%m-%Y %H:%M:%S",
        errors="coerce",
    )

    fallback = pd.to_datetime(
        series,
        errors="coerce",
        dayfirst=True,
    )

    return parsed.fillna(fallback)


def percentile_90(series):
    clean_series = series.dropna()
    return np.percentile(clean_series, 90) if len(clean_series) > 0 else np.nan


def percentile_95(series):
    clean_series = series.dropna()
    return np.percentile(clean_series, 95) if len(clean_series) > 0 else np.nan


def coefficient_of_variation(series):
    clean_series = series.dropna()

    if len(clean_series) == 0:
        return np.nan

    mean_val = clean_series.mean()

    if mean_val == 0:
        return 0

    return clean_series.std() / mean_val


def validate_required_columns(df, required_columns):
    return [col for col in required_columns if col not in df.columns]


def create_upload_signature(uploaded_files):
    if not uploaded_files:
        return None

    signature_parts = []

    for file in uploaded_files:
        file_bytes = file.getvalue()
        file_hash = hashlib.md5(file_bytes).hexdigest()
        signature_parts.append(
            f"{file.name}_{len(file_bytes)}_{file_hash}"
        )

    return "|".join(sorted(signature_parts))


def classify_meter_delta(delta_percent, tolerance_percent):
    if pd.isna(delta_percent):
        return "Not Comparable"

    if delta_percent >= tolerance_percent:
        return "Slower"

    if delta_percent <= -tolerance_percent:
        return "Faster"

    return "Comparable"


def add_risk(risk_register, severity, area, finding, impact, recommendation):
    risk_register.append(
        {
            "Severity": severity,
            "Area": area,
            "Finding": finding,
            "Impact": impact,
            "Recommendation": recommendation,
        }
    )


def render_card(title, value, subtitle, style="metric-card"):
    st.markdown(
        f"""
        <div class='{style}'>
            <p style='color:#718096; margin:0; font-size:12px; font-weight:600;'>{title}</p>
            <h3 style='margin:6px 0 0 0;'>{value}</h3>
            <p style='color:#718096; margin:6px 0 0 0; font-size:12px;'>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# HTML REPORT HELPERS
# =========================================================
def df_to_html_table(df, title):
    if df is None or df.empty:
        return f"""
        <section class="report-section">
            <h2>{escape(title)}</h2>
            <p class="empty-note">No data available.</p>
        </section>
        """

    return f"""
    <section class="report-section">
        <h2>{escape(title)}</h2>
        {df.to_html(index=False, escape=False, classes="report-table")}
    </section>
    """


def html_metric_card(title, value, subtitle, status_class="neutral"):
    return f"""
    <div class="html-card {status_class}">
        <div class="html-card-title">{escape(str(title))}</div>
        <div class="html-card-value">{escape(str(value))}</div>
        <div class="html-card-subtitle">{escape(str(subtitle))}</div>
    </div>
    """


def build_plotly_html_sections(figures, offline_mode=False):
    chart_sections = []

    for idx, item in enumerate(figures):
        title, fig = item

        if offline_mode and idx == 0:
            include_plotlyjs = "inline"
        elif not offline_mode and idx == 0:
            include_plotlyjs = "cdn"
        else:
            include_plotlyjs = False

        chart_html = pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs=include_plotlyjs,
            config={
                "displaylogo": False,
                "responsive": True,
            },
        )

        chart_sections.append(
            f"""
            <section class="report-section">
                <h2>{escape(title)}</h2>
                <div class="chart-container">
                    {chart_html}
                </div>
            </section>
            """
        )

    return "\n".join(chart_sections)


def build_html_report(
    executive_summary_df,
    risk_df,
    display_command_summary,
    fastest_slowest_display,
    display_meter_comparison,
    meter_summary,
    processed_df,
    upload_audit_rows,
    html_figures,
    overall_status,
    release_verdict,
    health_score,
    total_requests,
    success_rate,
    avg_duration,
    median_duration,
    p95_duration,
    max_retry,
    failure_count,
    final_recommendation,
    unit_label,
    offline_mode=False,
):
    generated_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    if risk_df is None or risk_df.empty:
        risk_export_df = pd.DataFrame(
            [{"Result": "No major risk identified"}]
        )
    else:
        risk_export_df = risk_df.copy()

    current_file_summary = processed_df.groupby("Source_Log_File").agg(
        Valid_Rows=("Command Name", "count"),
        Unique_Meters=("Meter Sr. No", "nunique"),
        Unique_Commands=("Command Name", "nunique"),
    ).reset_index()

    current_meter_list = pd.DataFrame(
        {
            "Current Meter Serial Number": sorted(
                processed_df["Meter Sr. No"].dropna().unique()
            )
        }
    )

    preview_df = processed_df[
        [
            "Command Start",
            "Command End",
            "Command Name",
            "Meter Sr. No",
            "Duration_Converted",
            "Retry",
            "Status",
            "Source_Log_File",
        ]
    ].copy()

    preview_df.columns = [
        "Command Start",
        "Command End",
        "Command Name",
        "Meter Sr. No",
        f"Duration ({unit_label})",
        "Retry",
        "Status",
        "Source Log",
    ]

    assessment_class = "success"
    if "CONDITIONAL" in str(overall_status):
        assessment_class = "warning"
    elif "FAIL" in str(overall_status):
        assessment_class = "danger"

    verdict_class = "success"
    if "CONDITIONAL" in str(release_verdict):
        verdict_class = "warning"
    elif "NO GO" in str(release_verdict):
        verdict_class = "danger"

    risk_count = 0 if risk_df is None else len(risk_df)

    metric_cards = f"""
    <div class="card-grid">
        {html_metric_card("Overall Assessment", overall_status, "Decision status", assessment_class)}
        {html_metric_card("Release Verdict", release_verdict, "Go / Conditional Go / No Go", verdict_class)}
        {html_metric_card("Health Score", f"{health_score}/100", "Higher score means lower risk", assessment_class)}
        {html_metric_card("Risk Areas", risk_count, "Auto-detected findings", "success" if risk_count == 0 else "warning")}
        {html_metric_card("Total Requests", f"{total_requests:,}", "Current uploaded dataset", "neutral")}
        {html_metric_card("Success Rate", f"{success_rate:.2f}%", f"Failed: {failure_count:,}", "success" if success_rate >= 95 else "danger")}
        {html_metric_card("Average Duration", f"{avg_duration:.2f} {unit_label}", "Mean response", "neutral")}
        {html_metric_card("Median Duration", f"{median_duration:.2f} {unit_label}", "P50 response", "neutral")}
        {html_metric_card("P95 Latency", f"{p95_duration:.2f} {unit_label}", "Slowest 5 percent threshold", "warning")}
        {html_metric_card("Max Retry", max_retry, "Worst retry count", "danger" if max_retry > 1 else "success")}
    </div>
    """

    chart_sections = build_plotly_html_sections(
        html_figures,
        offline_mode=offline_mode,
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>HES OD Performance Decision Report</title>
        <style>
            body {{
                font-family: "Segoe UI", Arial, sans-serif;
                background: #f5f7fb;
                color: #1a202c;
                margin: 0;
                padding: 0;
            }}

            .report-container {{
                max-width: 1320px;
                margin: 0 auto;
                padding: 28px;
            }}

            .hero {{
                background: linear-gradient(135deg, #0f4c81, #1a73e8);
                color: white;
                padding: 28px;
                border-radius: 16px;
                margin-bottom: 24px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}

            .hero h1 {{
                margin: 0;
                font-size: 30px;
            }}

            .hero p {{
                margin: 8px 0 0 0;
                font-size: 14px;
                opacity: 0.95;
            }}

            .final-recommendation {{
                background: #fffaf0;
                border-left: 6px solid #dd6b20;
                padding: 16px;
                border-radius: 10px;
                margin: 18px 0 24px 0;
                font-size: 15px;
            }}

            .card-grid {{
                display: grid;
                grid-template-columns: repeat(5, minmax(190px, 1fr));
                gap: 14px;
                margin-bottom: 24px;
            }}

            .html-card {{
                background: white;
                padding: 16px;
                border-radius: 12px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.08);
                border-left: 6px solid #3182ce;
                min-height: 100px;
            }}

            .html-card.success {{
                border-left-color: #38a169;
                background: #f0fff4;
            }}

            .html-card.warning {{
                border-left-color: #dd6b20;
                background: #fffaf0;
            }}

            .html-card.danger {{
                border-left-color: #e53e3e;
                background: #fff5f5;
            }}

            .html-card.neutral {{
                border-left-color: #3182ce;
                background: #ffffff;
            }}

            .html-card-title {{
                color: #718096;
                font-size: 12px;
                font-weight: 700;
                text-transform: uppercase;
            }}

            .html-card-value {{
                font-size: 24px;
                font-weight: 700;
                margin-top: 8px;
                color: #1a202c;
            }}

            .html-card-subtitle {{
                color: #718096;
                font-size: 12px;
                margin-top: 6px;
            }}

            .report-section {{
                background: white;
                border-radius: 14px;
                padding: 20px;
                margin-bottom: 22px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.07);
            }}

            .report-section h2 {{
                margin-top: 0;
                color: #1a202c;
                border-bottom: 2px solid #edf2f7;
                padding-bottom: 8px;
                font-size: 22px;
            }}

            .report-table {{
                border-collapse: collapse;
                width: 100%;
                font-size: 13px;
            }}

            .report-table th {{
                background: #edf2f7;
                color: #1a202c;
                padding: 9px;
                text-align: left;
                border: 1px solid #d8dee9;
            }}

            .report-table td {{
                padding: 8px;
                border: 1px solid #e2e8f0;
                vertical-align: top;
            }}

            .report-table tr:nth-child(even) {{
                background: #f8fafc;
            }}

            .chart-container {{
                width: 100%;
                overflow-x: auto;
            }}

            .empty-note {{
                color: #718096;
                font-style: italic;
            }}

            .footer {{
                color: #718096;
                font-size: 12px;
                text-align: center;
                margin-top: 35px;
                padding-bottom: 20px;
            }}

            @media print {{
                body {{
                    background: white;
                }}

                .report-section {{
                    page-break-inside: avoid;
                    box-shadow: none;
                    border: 1px solid #e2e8f0;
                }}

                .hero {{
                    box-shadow: none;
                }}
            }}
        </style>
    </head>

    <body>
        <div class="report-container">

            <div class="hero">
                <h1>⚡ HES On-Demand Performance Decision Report</h1>
                <p>Generated on: {generated_time}</p>
                <p>Report Type: Executive HTML Dashboard + Analytical Summary</p>
            </div>

            <div class="final-recommendation">
                <strong>Final Recommendation:</strong> {escape(str(final_recommendation))}
            </div>

            {metric_cards}

            {df_to_html_table(executive_summary_df, "Executive Summary")}
            {df_to_html_table(risk_export_df, "Risk Register and Recommendations")}
            {df_to_html_table(display_command_summary, "Command Health Assessment")}
            {df_to_html_table(fastest_slowest_display, "Fastest vs Slowest Meter")}
            {df_to_html_table(display_meter_comparison, "Meter-to-Meter Benchmark Matrix")}
            {df_to_html_table(meter_summary, "Meter Summary")}

            {chart_sections}

            {df_to_html_table(current_file_summary, "Current Upload File Summary")}
            {df_to_html_table(current_meter_list, "Current Meter List")}
            {df_to_html_table(pd.DataFrame(upload_audit_rows), "Upload Audit")}
            {df_to_html_table(preview_df, "Cleaned Analytical Dataset Preview")}

            <div class="footer">
                HES OD Performance Decision Report generated from current uploaded dataset.
            </div>

        </div>
    </body>
    </html>
    """


# =========================================================
# DATA PROCESSING
# =========================================================
def process_uploaded_files(uploaded_files, unit_factor):
    aggregated_list = []
    upload_audit_rows = []

    for uploaded_file in uploaded_files:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.getvalue()

        df = read_excel_cached(file_bytes)
        df = df.copy()
        df["Source_Log_File"] = uploaded_file.name

        aggregated_list.append(df)

        upload_audit_rows.append(
            {
                "Loaded File": uploaded_file.name,
                "Rows Loaded": len(df),
            }
        )

    if not aggregated_list:
        raise ValueError("No valid Excel logs could be processed.")

    raw_df = pd.concat(aggregated_list, ignore_index=True)

    required_columns = [
        "Command Name",
        "Total Duration",
        "Command Start",
        "Command End",
        "Status",
    ]

    missing_columns = validate_required_columns(raw_df, required_columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {', '.join(missing_columns)}"
        )

    if "Retry" in raw_df.columns:
        raw_df["Retry"] = pd.to_numeric(
            raw_df["Retry"],
            errors="coerce",
        ).fillna(0).astype(int)
    else:
        raw_df["Retry"] = 0

    if "Meter Sr. No" not in raw_df.columns:
        raw_df["Meter Sr. No"] = "UNKNOWN"

    raw_df["Command Name"] = raw_df["Command Name"].apply(clean_text)
    raw_df["Meter Sr. No"] = raw_df["Meter Sr. No"].apply(clean_meter_serial)
    raw_df["Status"] = raw_df["Status"].apply(clean_text)

    raw_df["Duration_Seconds"] = raw_df["Total Duration"].apply(
        parse_duration_to_seconds
    )
    raw_df["Command Start"] = parse_datetime_column(raw_df["Command Start"])
    raw_df["Command End"] = parse_datetime_column(raw_df["Command End"])
    raw_df["Duration_Converted"] = raw_df["Duration_Seconds"] / unit_factor
    raw_df["Status_Normalized"] = raw_df["Status"].apply(safe_upper)

    processed_df = raw_df.dropna(
        subset=["Command Name", "Duration_Seconds", "Command Start"]
    ).copy()

    processed_df = processed_df.sort_values(
        by="Command Start",
        ascending=True,
    ).reset_index(drop=True)

    processed_df = processed_df.drop_duplicates(
        subset=[
            "Source_Log_File",
            "Command Name",
            "Meter Sr. No",
            "Command Start",
            "Duration_Seconds",
            "Status",
        ],
        keep="first",
    ).reset_index(drop=True)

    if processed_df.empty:
        raise ValueError("No valid rows found after cleaning.")

    processed_df["Same_OD_Request_Key"] = (
        processed_df["Command Name"].astype(str)
        + " | "
        + processed_df["Meter Sr. No"].astype(str)
    )

    processed_df["Attempt_Sequence"] = processed_df.groupby(
        "Same_OD_Request_Key"
    ).cumcount() + 1

    return processed_df, upload_audit_rows


# =========================================================
# REPORT GENERATION
# =========================================================
def build_excel_report(
    executive_summary_df,
    risk_df,
    display_command_summary,
    meter_summary,
    display_meter_comparison,
    fastest_slowest_display,
    upload_audit_rows,
    processed_df,
):
    output_buffer = io.BytesIO()

    with pd.ExcelWriter(output_buffer, engine="openpyxl") as excel_writer:
        executive_summary_df.to_excel(
            excel_writer,
            sheet_name="Executive Summary",
            index=False,
        )

        if not risk_df.empty:
            risk_df.to_excel(
                excel_writer,
                sheet_name="Risk Register",
                index=False,
            )
        else:
            pd.DataFrame(
                [{"Result": "No major risk identified"}]
            ).to_excel(
                excel_writer,
                sheet_name="Risk Register",
                index=False,
            )

        display_command_summary.to_excel(
            excel_writer,
            sheet_name="Command Health",
            index=False,
        )

        if not meter_summary.empty:
            meter_summary.to_excel(
                excel_writer,
                sheet_name="Meter Summary",
                index=False,
            )

        if not display_meter_comparison.empty:
            display_meter_comparison.to_excel(
                excel_writer,
                sheet_name="Meter Comparison",
                index=False,
            )

        if not fastest_slowest_display.empty:
            fastest_slowest_display.to_excel(
                excel_writer,
                sheet_name="Fastest Slowest Meter",
                index=False,
            )

        pd.DataFrame(upload_audit_rows).to_excel(
            excel_writer,
            sheet_name="Upload Audit",
            index=False,
        )

        pd.DataFrame(
            {
                "Current Meter Serial Number": sorted(
                    processed_df["Meter Sr. No"].dropna().unique()
                )
            }
        ).to_excel(
            excel_writer,
            sheet_name="Current Meter List",
            index=False,
        )

        processed_df.to_excel(
            excel_writer,
            sheet_name="Cleaned Raw Logs",
            index=False,
        )

    return output_buffer.getvalue()


# =========================================================
# MAIN RUN FUNCTION
# =========================================================
def run() -> None:
    init_state()
    load_css()

    st.title("⚡ HES On-Demand Performance Analytics")

    st.markdown(
        """
        Upload HES audit log Excel files to generate a simplified, decision-ready performance report.

        This optimised Analysis-Hub version focuses on:

        - Executive decision summary
        - Risk areas and recommendations
        - Command health
        - Meter-to-meter benchmark
        - Command trend view with Meter SN, Retry Count and Duration labels
        - Excel and HTML dashboard report
        """
    )

    # =====================================================
    # SIDEBAR
    # =====================================================
    with st.sidebar:
        st.header("⚙️ OD Performance Controls")

        if st.button("🗑️ Clear Previous OD Data & Reload"):
            st.cache_data.clear()
            st.cache_resource.clear()

            next_version = st.session_state.get("od_uploader_version", 0) + 1

            for key in list(st.session_state.keys()):
                if key.startswith("od_"):
                    del st.session_state[key]

            st.session_state["od_uploader_version"] = next_version
            st.session_state["od_last_upload_signature"] = None
            st.session_state["od_analysis_ready"] = False
            st.session_state["od_processed_df"] = None
            st.session_state["od_upload_audit_rows"] = None

            st.rerun()

        uploaded_files = st.file_uploader(
            "Upload HES Excel Logs",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key=f"od_hes_log_uploader_{st.session_state['od_uploader_version']}",
        )

        unit_selection = st.radio(
            "Duration Display Unit",
            options=["Seconds (s)", "Minutes (min)"],
            index=0,
            key="od_unit_selection",
        )

        unit_factor = 60.0 if "Minutes" in unit_selection else 1.0
        unit_label = "min" if "Minutes" in unit_selection else "s"

        st.markdown("---")
        st.subheader("🎯 Decision Thresholds")

        success_threshold = st.slider(
            "Minimum acceptable success rate (%)",
            min_value=80,
            max_value=100,
            value=95,
            step=1,
            key="od_success_threshold",
        )

        p95_multiplier_threshold = st.slider(
            "P95 risk threshold vs average",
            min_value=1.2,
            max_value=5.0,
            value=2.0,
            step=0.1,
            help="Example: 2.0 means P95 greater than 2x average is treated as a risk.",
            key="od_p95_multiplier_threshold",
        )

        comparison_tolerance = st.slider(
            "Meter performance gap tolerance (%)",
            min_value=1,
            max_value=50,
            value=10,
            step=1,
            key="od_comparison_tolerance",
        )

        high_gap_threshold = st.slider(
            "High meter gap threshold (%)",
            min_value=10,
            max_value=100,
            value=30,
            step=5,
            key="od_high_gap_threshold",
        )

        show_meter_charts = st.checkbox(
            "Show Meter Benchmark Charts",
            value=True,
            key="od_show_meter_charts",
        )

        show_trend_charts = st.checkbox(
            "Show Command Trend Charts",
            value=False,
            key="od_show_trend_charts",
            help="Turn this on only when trend charts are required. This keeps the tool faster.",
        )

        st.markdown("---")
        st.subheader("📄 Report Settings")

        html_report_mode = st.radio(
            "HTML Report Mode",
            options=[
                "Lightweight HTML - charts use CDN",
                "Self-contained HTML - larger file",
            ],
            index=0,
            key="od_html_report_mode",
        )

        html_offline_mode = html_report_mode.startswith("Self-contained")

        run_analysis = st.button(
            "🚀 Run Performance Analysis",
            type="primary",
        )

    # =====================================================
    # UPLOAD STATE DETECTION
    # =====================================================
    current_upload_signature = create_upload_signature(uploaded_files)

    if current_upload_signature != st.session_state.get("od_last_upload_signature"):
        clear_analysis_widget_states()
        st.session_state["od_last_upload_signature"] = current_upload_signature

    # =====================================================
    # STANDBY
    # =====================================================
    if not uploaded_files:
        st.info(
            """
            ℹ️ Upload the latest HES audit logs from the sidebar.

            Required columns:
            - Command Name
            - Total Duration
            - Command Start
            - Command End
            - Status

            Optional but recommended:
            - Meter Sr. No
            - Retry
            """
        )
        return

    if run_analysis:
        try:
            with st.spinner("Processing uploaded HES logs..."):
                processed_df, upload_audit_rows = process_uploaded_files(
                    uploaded_files,
                    unit_factor,
                )

            st.session_state["od_processed_df"] = processed_df
            st.session_state["od_upload_audit_rows"] = upload_audit_rows
            st.session_state["od_analysis_ready"] = True
            st.session_state["od_excel_bytes"] = None
            st.session_state["od_html_text"] = None

            st.success("✅ Performance analysis completed.")

        except Exception as e:
            st.error(f"❌ Error while processing OD performance logs: {str(e)}")
            return

    if not st.session_state.get("od_analysis_ready"):
        st.info("Upload files and click **🚀 Run Performance Analysis** to start.")
        return

    processed_df = st.session_state["od_processed_df"]
    upload_audit_rows = st.session_state["od_upload_audit_rows"]

    # =====================================================
    # SIDEBAR AUDIT
    # =====================================================
    with st.sidebar:
        st.markdown("---")
        st.subheader("📂 Current Upload Audit")

        st.metric("Rows Analysed", len(processed_df))
        st.metric("Meters Detected", processed_df["Meter Sr. No"].nunique())

        with st.expander("Current Files"):
            for file_name in sorted(processed_df["Source_Log_File"].unique()):
                st.write(f"✅ {file_name}")

        with st.expander("Current Meter SN List"):
            for meter in sorted(processed_df["Meter Sr. No"].dropna().unique()):
                st.write(meter)

    # =====================================================
    # CORE METRICS
    # =====================================================
    total_requests = len(processed_df)
    success_count = (processed_df["Status_Normalized"] == "SUCCESS").sum()
    failure_count = total_requests - success_count

    success_rate = (
        success_count / total_requests * 100 if total_requests > 0 else 0
    )
    avg_duration = processed_df["Duration_Converted"].mean()
    median_duration = processed_df["Duration_Converted"].median()
    p95_duration = percentile_95(processed_df["Duration_Converted"])
    max_retry = int(processed_df["Retry"].max())

    # =====================================================
    # COMMAND SUMMARY
    # =====================================================
    command_summary = processed_df.groupby("Command Name").agg(
        Total_Requests=("Duration_Converted", "count"),
        Success_Count=("Status_Normalized", lambda x: (x == "SUCCESS").sum()),
        Failure_Count=("Status_Normalized", lambda x: (x != "SUCCESS").sum()),
        Avg_Duration=("Duration_Converted", "mean"),
        Median_Duration=("Duration_Converted", "median"),
        P90_Duration=("Duration_Converted", percentile_90),
        P95_Duration=("Duration_Converted", percentile_95),
        Max_Duration=("Duration_Converted", "max"),
        Avg_Retry=("Retry", "mean"),
        Max_Retry=("Retry", "max"),
        Stability_CV=("Duration_Converted", coefficient_of_variation),
    ).reset_index()

    command_summary["Success_Rate_%"] = (
        command_summary["Success_Count"]
        / command_summary["Total_Requests"]
        * 100
    )

    round_cols = [
        "Avg_Duration",
        "Median_Duration",
        "P90_Duration",
        "P95_Duration",
        "Max_Duration",
        "Avg_Retry",
        "Stability_CV",
        "Success_Rate_%",
    ]

    for col in round_cols:
        command_summary[col] = command_summary[col].round(2)

    command_summary["Tail_Risk_Flag"] = np.where(
        command_summary["P95_Duration"]
        > command_summary["Avg_Duration"] * p95_multiplier_threshold,
        "Yes",
        "No",
    )

    command_summary["Command_Health"] = np.where(
        (command_summary["Success_Rate_%"] < success_threshold)
        | (command_summary["Tail_Risk_Flag"] == "Yes")
        | (command_summary["Max_Retry"] > 1),
        "Attention Required",
        "Healthy",
    )

    # =====================================================
    # FILTERS
    # =====================================================
    st.markdown(
        "<div class='section-header'>🎛️ Analysis Filters</div>",
        unsafe_allow_html=True,
    )

    available_commands = sorted(processed_df["Command Name"].dropna().unique())

    default_meter_commands = [
        cmd
        for cmd in available_commands
        if "connect" in cmd.lower() or "disconnect" in cmd.lower()
    ]

    if not default_meter_commands:
        default_meter_commands = available_commands

    selected_meter_commands = st.multiselect(
        "Select OD command(s) for meter-to-meter benchmark",
        options=available_commands,
        default=default_meter_commands,
        key="od_selected_meter_commands",
    )

    meter_benchmark_df = processed_df[
        processed_df["Command Name"].isin(selected_meter_commands)
    ].copy()

    available_meters = sorted(
        meter_benchmark_df["Meter Sr. No"].dropna().unique()
    )

    selected_meters = st.multiselect(
        "Select meters to compare",
        options=available_meters,
        default=available_meters[:2] if len(available_meters) >= 2 else available_meters,
        key="od_selected_meters",
    )

    meter_benchmark_df = meter_benchmark_df[
        meter_benchmark_df["Meter Sr. No"].isin(selected_meters)
    ].copy()

    # =====================================================
    # METER BENCHMARK
    # =====================================================
    meter_summary = pd.DataFrame()
    meter_comparison = pd.DataFrame()
    display_meter_comparison = pd.DataFrame()
    fastest_slowest_display = pd.DataFrame()

    max_meter_gap = 0
    max_meter_gap_command = "NA"

    if not meter_benchmark_df.empty:
        meter_summary = meter_benchmark_df.groupby(
            ["Command Name", "Meter Sr. No"]
        ).agg(
            Total_Requests=("Duration_Converted", "count"),
            Success_Count=("Status_Normalized", lambda x: (x == "SUCCESS").sum()),
            Failure_Count=("Status_Normalized", lambda x: (x != "SUCCESS").sum()),
            Avg_Duration=("Duration_Converted", "mean"),
            Median_Duration=("Duration_Converted", "median"),
            P95_Duration=("Duration_Converted", percentile_95),
            Max_Duration=("Duration_Converted", "max"),
            Avg_Retry=("Retry", "mean"),
            Max_Retry=("Retry", "max"),
        ).reset_index()

        meter_summary["Success_Rate_%"] = (
            meter_summary["Success_Count"]
            / meter_summary["Total_Requests"]
            * 100
        )

        for col in [
            "Avg_Duration",
            "Median_Duration",
            "P95_Duration",
            "Max_Duration",
            "Avg_Retry",
            "Success_Rate_%",
        ]:
            meter_summary[col] = meter_summary[col].round(2)

        if selected_meters:
            reference_meter = st.selectbox(
                "Select reference meter for benchmark delta",
                options=selected_meters,
                index=0,
                key="od_reference_meter",
            )

            reference_df = meter_summary[
                meter_summary["Meter Sr. No"] == reference_meter
            ][
                [
                    "Command Name",
                    "Avg_Duration",
                    "P95_Duration",
                    "Success_Rate_%",
                    "Avg_Retry",
                ]
            ].copy()

            reference_df = reference_df.rename(
                columns={
                    "Avg_Duration": "Reference_Avg_Duration",
                    "P95_Duration": "Reference_P95_Duration",
                    "Success_Rate_%": "Reference_Success_Rate_%",
                    "Avg_Retry": "Reference_Avg_Retry",
                }
            )

            meter_comparison = meter_summary.merge(
                reference_df,
                on="Command Name",
                how="left",
            )

            meter_comparison["Avg_Gap"] = (
                meter_comparison["Avg_Duration"]
                - meter_comparison["Reference_Avg_Duration"]
            )

            meter_comparison["Avg_Gap_%"] = np.where(
                meter_comparison["Reference_Avg_Duration"] > 0,
                meter_comparison["Avg_Gap"]
                / meter_comparison["Reference_Avg_Duration"]
                * 100,
                np.nan,
            )

            meter_comparison["P95_Gap_%"] = np.where(
                meter_comparison["Reference_P95_Duration"] > 0,
                (
                    meter_comparison["P95_Duration"]
                    - meter_comparison["Reference_P95_Duration"]
                )
                / meter_comparison["Reference_P95_Duration"]
                * 100,
                np.nan,
            )

            meter_comparison["Success_Rate_Gap_%"] = (
                meter_comparison["Success_Rate_%"]
                - meter_comparison["Reference_Success_Rate_%"]
            )

            meter_comparison["Retry_Gap"] = (
                meter_comparison["Avg_Retry"]
                - meter_comparison["Reference_Avg_Retry"]
            )

            meter_comparison["Meter_Status"] = meter_comparison["Avg_Gap_%"].apply(
                lambda x: classify_meter_delta(x, comparison_tolerance)
            )

            for col in [
                "Avg_Gap",
                "Avg_Gap_%",
                "P95_Gap_%",
                "Success_Rate_Gap_%",
                "Retry_Gap",
            ]:
                meter_comparison[col] = meter_comparison[col].round(2)

            fastest_rows = meter_summary.loc[
                meter_summary.groupby("Command Name")["Avg_Duration"].idxmin()
            ][["Command Name", "Meter Sr. No", "Avg_Duration"]]

            slowest_rows = meter_summary.loc[
                meter_summary.groupby("Command Name")["Avg_Duration"].idxmax()
            ][["Command Name", "Meter Sr. No", "Avg_Duration"]]

            fastest_slowest_df = fastest_rows.merge(
                slowest_rows,
                on="Command Name",
                suffixes=("_Fastest", "_Slowest"),
            )

            fastest_slowest_df["Gap"] = (
                fastest_slowest_df["Avg_Duration_Slowest"]
                - fastest_slowest_df["Avg_Duration_Fastest"]
            )

            fastest_slowest_df["Gap_%"] = np.where(
                fastest_slowest_df["Avg_Duration_Fastest"] > 0,
                fastest_slowest_df["Gap"]
                / fastest_slowest_df["Avg_Duration_Fastest"]
                * 100,
                np.nan,
            )

            fastest_slowest_df["Gap"] = fastest_slowest_df["Gap"].round(2)
            fastest_slowest_df["Gap_%"] = fastest_slowest_df["Gap_%"].round(2)

            fastest_slowest_display = fastest_slowest_df.copy()
            fastest_slowest_display.columns = [
                "Command Name",
                "Fastest Meter",
                f"Fastest Avg ({unit_label})",
                "Slowest Meter",
                f"Slowest Avg ({unit_label})",
                f"Gap ({unit_label})",
                "Gap (%)",
            ]

            if not fastest_slowest_df.empty:
                max_meter_gap = fastest_slowest_df["Gap_%"].max()
                max_gap_row = fastest_slowest_df.loc[
                    fastest_slowest_df["Gap_%"].idxmax()
                ]
                max_meter_gap_command = max_gap_row["Command Name"]

    # =====================================================
    # DECISION ENGINE
    # =====================================================
    risk_register = []
    strengths = []

    health_score = 100

    if success_rate < success_threshold:
        health_score -= 25
        add_risk(
            risk_register,
            "High",
            "Execution Reliability",
            f"Success rate is {success_rate:.2f}%, below target {success_threshold}%",
            "OD execution reliability may not be acceptable for rollout.",
            "Review failed commands, meter responses and HES error patterns.",
        )
    else:
        strengths.append(f"Success rate is healthy at {success_rate:.2f}%.")

    if max_retry > 1:
        health_score -= 20
        add_risk(
            risk_register,
            "High",
            "Communication Stability",
            f"Maximum retry count observed is {max_retry}",
            "Retry spikes may increase execution time and cause unstable OD behaviour.",
            "Validate communication path, RF quality, network hops and meter response.",
        )
    else:
        strengths.append("Retry behaviour is stable; no high retry spike detected.")

    if p95_duration > avg_duration * p95_multiplier_threshold:
        health_score -= 20
        add_risk(
            risk_register,
            "Medium",
            "Tail Latency",
            f"P95 latency {p95_duration:.2f} {unit_label} is greater than {p95_multiplier_threshold}x average",
            "Slowest 5% executions are significantly slower than normal behaviour.",
            "Investigate slowest OD attempts, HES queue delay and communication latency.",
        )
    else:
        strengths.append("Tail latency is within the configured acceptable range.")

    if max_meter_gap >= high_gap_threshold:
        health_score -= 15
        add_risk(
            risk_register,
            "Medium",
            "Meter Benchmark",
            f"Highest meter-to-meter gap is {max_meter_gap:.2f}% for {max_meter_gap_command}",
            "One meter behaves slower than another for the same OD command.",
            "Check slow meter communication route, retries, firmware and signal quality.",
        )
    elif not meter_summary.empty:
        strengths.append("Meter-to-meter performance variation is within acceptable range.")

    if command_summary["Command_Health"].eq("Attention Required").any():
        impacted_commands = command_summary[
            command_summary["Command_Health"] == "Attention Required"
        ]["Command Name"].tolist()

        health_score -= 10

        add_risk(
            risk_register,
            "Medium",
            "Command Health",
            f"{len(impacted_commands)} command(s) require attention",
            "One or more commands show failure, retry or tail latency risk.",
            "Review command-level health table and validate impacted OD commands.",
        )

    health_score = max(0, min(100, health_score))

    if health_score >= 85:
        overall_status = "🟢 PASS"
        release_verdict = "🟢 GO"
        final_recommendation = (
            "Proceed. Current performance is acceptable based on configured thresholds."
        )
    elif health_score >= 70:
        overall_status = "🟡 CONDITIONAL PASS"
        release_verdict = "🟡 CONDITIONAL GO"
        final_recommendation = (
            "Proceed only after validating highlighted risk areas."
        )
    else:
        overall_status = "🔴 FAIL"
        release_verdict = "🔴 NO GO"
        final_recommendation = (
            "Do not proceed until high-risk findings are resolved."
        )

    risk_df = pd.DataFrame(risk_register)

    executive_summary_df = pd.DataFrame(
        [
            {
                "Overall Assessment": overall_status,
                "Release Verdict": release_verdict,
                "Health Score": health_score,
                "Total Requests": total_requests,
                "Success Rate (%)": round(success_rate, 2),
                f"Average Duration ({unit_label})": round(avg_duration, 2),
                f"P95 Latency ({unit_label})": round(p95_duration, 2),
                "Max Retry": max_retry,
                "Risk Count": len(risk_register),
                "Final Recommendation": final_recommendation,
            }
        ]
    )

    # =====================================================
    # EXECUTIVE DASHBOARD
    # =====================================================
    st.markdown(
        "<div class='section-header'>🚦 Executive Performance Assessment</div>",
        unsafe_allow_html=True,
    )

    e1, e2, e3, e4 = st.columns(4)

    with e1:
        render_card(
            "Overall Assessment",
            overall_status,
            "Decision based on success, retry, latency and meter gap",
            "metric-card-success"
            if health_score >= 85
            else "metric-card-warning"
            if health_score >= 70
            else "metric-card-fail",
        )

    with e2:
        render_card(
            "Health Score",
            f"{health_score}/100",
            "Higher score means lower performance risk",
            "metric-card-success"
            if health_score >= 85
            else "metric-card-warning"
            if health_score >= 70
            else "metric-card-fail",
        )

    with e3:
        render_card(
            "Release Verdict",
            release_verdict,
            "Go / Conditional Go / No Go",
            "metric-card-success"
            if release_verdict.startswith("🟢")
            else "metric-card-warning"
            if release_verdict.startswith("🟡")
            else "metric-card-fail",
        )

    with e4:
        render_card(
            "Risk Areas",
            len(risk_register),
            "Auto-detected risk findings",
            "metric-card-success"
            if len(risk_register) == 0
            else "metric-card-warning"
            if len(risk_register) <= 2
            else "metric-card-fail",
        )

    st.markdown("### 📌 Executive Summary Insight")

    if strengths:
        for item in strengths[:5]:
            st.success(f"✅ {item}")

    if risk_register:
        for risk in risk_register[:5]:
            st.warning(
                f"⚠️ **{risk['Area']}** — {risk['Finding']} "
                f"**Recommendation:** {risk['Recommendation']}"
            )
    else:
        st.success("✅ No major risk areas detected based on configured thresholds.")

    st.info(f"📌 **Final Recommendation:** {final_recommendation}")

    # =====================================================
    # KPI OVERVIEW
    # =====================================================
    st.markdown(
        "<div class='section-header'>📊 Critical KPI Overview</div>",
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4, k5, k6 = st.columns(6)

    with k1:
        render_card("Total Requests", f"{total_requests:,}", "Current uploaded dataset")

    with k2:
        render_card(
            "Success Rate",
            f"{success_rate:.2f}%",
            f"Failed: {failure_count:,}",
            "metric-card-success"
            if success_rate >= success_threshold
            else "metric-card-fail",
        )

    with k3:
        render_card("Average", f"{avg_duration:.2f} {unit_label}", "Mean response")

    with k4:
        render_card("Median", f"{median_duration:.2f} {unit_label}", "P50 response")

    with k5:
        render_card(
            "P95 Latency",
            f"{p95_duration:.2f} {unit_label}",
            "Slowest 5% threshold",
            "metric-card-warning"
            if p95_duration > avg_duration * p95_multiplier_threshold
            else "metric-card-success",
        )

    with k6:
        render_card(
            "Max Retry",
            f"{max_retry}",
            "Worst retry count",
            "metric-card-fail" if max_retry > 1 else "metric-card-success",
        )

    # =====================================================
    # RISK REGISTER
    # =====================================================
    st.markdown(
        "<div class='section-header'>⚠️ Risk Register & Recommendations</div>",
        unsafe_allow_html=True,
    )

    if risk_df.empty:
        st.success("✅ No major risk identified.")
    else:
        st.dataframe(
            risk_df,
            hide_index=True,
            use_container_width=True,
        )

    # =====================================================
    # COMMAND HEALTH
    # =====================================================
    st.markdown(
        "<div class='section-header'>🩺 Command Health Assessment</div>",
        unsafe_allow_html=True,
    )

    display_command_summary = command_summary[
        [
            "Command Name",
            "Total_Requests",
            "Success_Rate_%",
            "Avg_Duration",
            "Median_Duration",
            "P95_Duration",
            "Max_Duration",
            "Avg_Retry",
            "Max_Retry",
            "Tail_Risk_Flag",
            "Command_Health",
        ]
    ].copy()

    display_command_summary.columns = [
        "Command Name",
        "Total Requests",
        "Success Rate (%)",
        f"Avg Duration ({unit_label})",
        f"Median Duration ({unit_label})",
        f"P95 Duration ({unit_label})",
        f"Max Duration ({unit_label})",
        "Avg Retry",
        "Max Retry",
        "Tail Risk",
        "Command Health",
    ]

    st.dataframe(
        display_command_summary,
        hide_index=True,
        use_container_width=True,
    )

    # =====================================================
    # METER BENCHMARK
    # =====================================================
    st.markdown(
        "<div class='section-header'>🔀 Meter-to-Meter Benchmark</div>",
        unsafe_allow_html=True,
    )

    html_figures = []

    if meter_summary.empty:
        st.warning("⚠️ No meter benchmark data available for selected filters.")
    else:
        m1, m2, m3 = st.columns(3)

        with m1:
            render_card(
                "Meters Compared",
                meter_benchmark_df["Meter Sr. No"].nunique(),
                "Selected meter count",
            )

        with m2:
            render_card(
                "Commands Compared",
                meter_benchmark_df["Command Name"].nunique(),
                "Selected OD command count",
            )

        with m3:
            render_card(
                "Max Meter Gap",
                f"{max_meter_gap:.2f}%",
                f"Highest gap: {max_meter_gap_command}",
                "metric-card-warning"
                if max_meter_gap >= high_gap_threshold
                else "metric-card-success",
            )

        if not fastest_slowest_display.empty:
            st.markdown("### 🏁 Fastest vs Slowest Meter")

            st.dataframe(
                fastest_slowest_display,
                hide_index=True,
                use_container_width=True,
            )

        if not meter_comparison.empty:
            display_meter_comparison = meter_comparison[
                [
                    "Command Name",
                    "Meter Sr. No",
                    "Total_Requests",
                    "Success_Rate_%",
                    "Avg_Duration",
                    "Reference_Avg_Duration",
                    "Avg_Gap",
                    "Avg_Gap_%",
                    "P95_Duration",
                    "P95_Gap_%",
                    "Avg_Retry",
                    "Retry_Gap",
                    "Max_Retry",
                    "Meter_Status",
                ]
            ].copy()

            display_meter_comparison.columns = [
                "Command Name",
                "Meter Sr. No",
                "Total Requests",
                "Success Rate (%)",
                f"Avg Duration ({unit_label})",
                f"Reference Avg ({unit_label})",
                f"Avg Gap ({unit_label})",
                "Avg Gap (%)",
                f"P95 Duration ({unit_label})",
                "P95 Gap (%)",
                "Avg Retry",
                "Retry Gap",
                "Max Retry",
                "Meter Status",
            ]

            st.markdown("### 📋 Meter Benchmark Matrix")

            st.dataframe(
                display_meter_comparison,
                hide_index=True,
                use_container_width=True,
            )

        if show_meter_charts:
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                fig_meter_avg = px.bar(
                    meter_summary,
                    x="Command Name",
                    y="Avg_Duration",
                    color="Meter Sr. No",
                    barmode="group",
                    title=f"Meter Average Duration Comparison ({unit_label})",
                    labels={
                        "Avg_Duration": f"Average Duration ({unit_label})",
                        "Command Name": "OD Command",
                        "Meter Sr. No": "Meter",
                    },
                )

                fig_meter_avg.update_layout(
                    height=420,
                    xaxis_tickangle=-30,
                    margin=dict(l=40, r=20, t=60, b=100),
                )

                st.plotly_chart(fig_meter_avg, use_container_width=True)
                html_figures.append(("Meter Average Duration Comparison", fig_meter_avg))

            with chart_col2:
                fig_meter_p95 = px.bar(
                    meter_summary,
                    x="Command Name",
                    y="P95_Duration",
                    color="Meter Sr. No",
                    barmode="group",
                    title=f"Meter P95 Latency Comparison ({unit_label})",
                    labels={
                        "P95_Duration": f"P95 Duration ({unit_label})",
                        "Command Name": "OD Command",
                        "Meter Sr. No": "Meter",
                    },
                )

                fig_meter_p95.update_layout(
                    height=420,
                    xaxis_tickangle=-30,
                    margin=dict(l=40, r=20, t=60, b=100),
                )

                st.plotly_chart(fig_meter_p95, use_container_width=True)
                html_figures.append(("Meter P95 Latency Comparison", fig_meter_p95))

    # =====================================================
    # COMMAND TREND VIEW - OPTIONAL
    # =====================================================
    st.markdown(
        "<div class='section-header'>📉 Command Trend View</div>",
        unsafe_allow_html=True,
    )

    if show_trend_charts:
        default_trend_commands = (
            selected_meter_commands if selected_meter_commands else available_commands[:3]
        )

        selected_trend_commands = st.multiselect(
            "Select command(s) to view trend",
            options=available_commands,
            default=default_trend_commands,
            key="od_selected_trend_commands",
        )

        trend_df = processed_df[
            processed_df["Command Name"].isin(selected_trend_commands)
        ].copy()

        if trend_df.empty:
            st.warning("⚠️ No trend data available for selected command filters.")
        else:
            for command in selected_trend_commands:
                cmd_trend = trend_df[trend_df["Command Name"] == command].copy()

                if cmd_trend.empty:
                    continue

                cmd_trend = cmd_trend.sort_values(
                    by="Command Start",
                    ascending=True,
                ).reset_index(drop=True)

                cmd_trend["Attempt_Index"] = range(1, len(cmd_trend) + 1)

                cmd_trend["Point_Label"] = (
                    cmd_trend["Meter Sr. No"].astype(str)
                    + " | R:"
                    + cmd_trend["Retry"].astype(str)
                    + " | "
                    + cmd_trend["Duration_Converted"].round(1).astype(str)
                    + unit_label
                )

                cmd_trend["Retry_Status"] = np.where(
                    cmd_trend["Retry"] > 1,
                    "High Retry",
                    np.where(
                        cmd_trend["Retry"] == 1,
                        "Retry",
                        "No Retry",
                    ),
                )

                cmd_trend["Hover_Info"] = (
                    "Timestamp: "
                    + cmd_trend["Command Start"].dt.strftime("%d-%m-%Y %H:%M:%S")
                    + "<br>Meter: "
                    + cmd_trend["Meter Sr. No"].astype(str)
                    + "<br>Duration: "
                    + cmd_trend["Duration_Converted"].round(2).astype(str)
                    + f" {unit_label}"
                    + "<br>Retry: "
                    + cmd_trend["Retry"].astype(str)
                    + "<br>Status: "
                    + cmd_trend["Status"].astype(str)
                    + "<br>Source: "
                    + cmd_trend["Source_Log_File"].astype(str)
                )

                fig_cmd_trend = px.scatter(
                    cmd_trend,
                    x="Attempt_Index",
                    y="Duration_Converted",
                    color="Retry_Status",
                    text="Point_Label",
                    title=f"Command Trend: {command}",
                    labels={
                        "Attempt_Index": "Chronological Attempt",
                        "Duration_Converted": f"Duration ({unit_label})",
                        "Retry_Status": "Retry Status",
                    },
                    color_discrete_map={
                        "No Retry": "#38a169",
                        "Retry": "#dd6b20",
                        "High Retry": "#e53e3e",
                    },
                )

                fig_cmd_trend.update_traces(
                    textposition="top center",
                    textfont=dict(size=10, color="black"),
                    hovertext=cmd_trend["Hover_Info"],
                    hoverinfo="text",
                    marker=dict(size=11),
                )

                max_y = cmd_trend["Duration_Converted"].max()

                fig_cmd_trend.update_layout(
                    height=500,
                    margin=dict(l=45, r=30, t=70, b=80),
                    yaxis=dict(
                        range=[0, max_y * 1.45 if max_y > 0 else 1],
                    ),
                    uniformtext_minsize=8,
                    uniformtext_mode="show",
                )

                st.plotly_chart(fig_cmd_trend, use_container_width=True)
                html_figures.append((f"Command Trend - {command}", fig_cmd_trend))
    else:
        st.info(
            "Trend charts are disabled by default for faster loading. "
            "Enable **Show Command Trend Charts** from the sidebar when required."
        )

    # =====================================================
    # VALIDATION PANEL
    # =====================================================
    with st.expander("🔍 Current Upload Validation"):
        v1, v2 = st.columns(2)

        with v1:
            current_file_summary = processed_df.groupby("Source_Log_File").agg(
                Valid_Rows=("Command Name", "count"),
                Unique_Meters=("Meter Sr. No", "nunique"),
                Unique_Commands=("Command Name", "nunique"),
            ).reset_index()

            st.markdown("### Uploaded Files")

            st.dataframe(
                current_file_summary,
                hide_index=True,
                use_container_width=True,
            )

        with v2:
            current_meter_list = pd.DataFrame(
                {
                    "Current Meter Serial Number": sorted(
                        processed_df["Meter Sr. No"].dropna().unique()
                    )
                }
            )

            st.markdown("### Current Meter List")

            st.dataframe(
                current_meter_list,
                hide_index=True,
                use_container_width=True,
            )

        st.info(
            "If an old meter appears here, it exists in the currently uploaded files. "
            "If it does not appear here, it is not used in the current analysis."
        )

    # =====================================================
    # REPORT GENERATION - ON DEMAND
    # =====================================================
    st.markdown(
        "<div class='section-header'>📥 Download Decision Reports</div>",
        unsafe_allow_html=True,
    )

    report_col1, report_col2, report_col3 = st.columns(3)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with report_col1:
        if st.button("📊 Prepare Excel Report"):
            excel_bytes = build_excel_report(
                executive_summary_df=executive_summary_df,
                risk_df=risk_df,
                display_command_summary=display_command_summary,
                meter_summary=meter_summary,
                display_meter_comparison=display_meter_comparison,
                fastest_slowest_display=fastest_slowest_display,
                upload_audit_rows=upload_audit_rows,
                processed_df=processed_df,
            )

            st.session_state["od_excel_bytes"] = excel_bytes
            st.session_state["od_last_report_timestamp"] = timestamp

            st.success("✅ Excel report prepared.")

    with report_col2:
        if st.button("🌐 Generate HTML Dashboard"):
            html_report = build_html_report(
                executive_summary_df=executive_summary_df,
                risk_df=risk_df,
                display_command_summary=display_command_summary,
                fastest_slowest_display=fastest_slowest_display,
                display_meter_comparison=display_meter_comparison,
                meter_summary=meter_summary,
                processed_df=processed_df,
                upload_audit_rows=upload_audit_rows,
                html_figures=html_figures,
                overall_status=overall_status,
                release_verdict=release_verdict,
                health_score=health_score,
                total_requests=total_requests,
                success_rate=success_rate,
                avg_duration=avg_duration,
                median_duration=median_duration,
                p95_duration=p95_duration,
                max_retry=max_retry,
                failure_count=failure_count,
                final_recommendation=final_recommendation,
                unit_label=unit_label,
                offline_mode=html_offline_mode,
            )

            st.session_state["od_html_text"] = html_report
            st.session_state["od_last_report_timestamp"] = timestamp

            st.success("✅ HTML dashboard report generated.")

    excel_bytes_available = st.session_state.get("od_excel_bytes")
    html_text_available = st.session_state.get("od_html_text")
    report_timestamp = st.session_state.get("od_last_report_timestamp") or timestamp

    if excel_bytes_available:
        st.download_button(
            label="💾 Download Excel Report (.xlsx)",
            data=excel_bytes_available,
            file_name=f"HES_OD_Performance_Decision_Report_{report_timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if html_text_available:
        st.download_button(
            label="🌐 Download HTML Dashboard (.html)",
            data=html_text_available.encode("utf-8"),
            file_name=f"HES_OD_Performance_Dashboard_Report_{report_timestamp}.html",
            mime="text/html",
        )

    with report_col3:
        if st.button("📁 Save Prepared Reports to /reports"):
            REPORT_DIR.mkdir(parents=True, exist_ok=True)

            saved_items = []

            if excel_bytes_available:
                excel_path = REPORT_DIR / f"HES_OD_Performance_Decision_Report_{report_timestamp}.xlsx"
                with open(excel_path, "wb") as f:
                    f.write(excel_bytes_available)
                saved_items.append(str(excel_path))

            if html_text_available:
                html_path = REPORT_DIR / f"HES_OD_Performance_Dashboard_Report_{report_timestamp}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_text_available)
                saved_items.append(str(html_path))

            if saved_items:
                st.success(
                    "Reports saved successfully:\n\n"
                    + "\n".join([f"- {item}" for item in saved_items])
                )
            else:
                st.warning(
                    "No prepared reports found. Please prepare Excel and/or generate HTML first."
                )


# =========================================================
# DIRECT EXECUTION SUPPORT
# =========================================================
if __name__ == "__main__":
    run()