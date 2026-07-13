# _pages/weekly_data_analysis.py
"""Weekly SLA analysis tool for smart meter data."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import io
import os
import base64
import tempfile
import logging
from datetime import datetime
from typing import List, Tuple, Optional

# Optional imports
try:
    import altair as alt
except ImportError:
    alt = None

try:
    import seaborn as sns
except ImportError:
    sns = None

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

# Cross-platform utilities
from utils.platform_utils import EMAIL_SERVICE
from utils.error_handler import ErrorHandler, handle_errors

logger = logging.getLogger(__name__)

# -----------------------
# Helpers (pure functions / IO helpers)
# -----------------------

def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
    finally:
        try:
            buf.close()
        except Exception:
            pass

def read_profile(files: List[io.BytesIO], profile_type: str) -> pd.DataFrame:
    """Read uploaded xlsx/csv files and return DataFrame with meter_id, timestamp, profile_type."""
    dfs = []
    for f in files or []:
        try:
            df = pd.read_excel(f)
        except Exception:
            try:
                f.seek(0)
                df = pd.read_csv(f)
            except Exception as e:
                continue
        df.columns = df.columns.str.strip().str.lower()
        # Normalize common names
        if "meter id" in df.columns:
            df.rename(columns={"meter id": "meter_id"}, inplace=True)
        if "meter" in df.columns and "meter_id" not in df.columns:
            df.rename(columns={"meter": "meter_id"}, inplace=True)
        # timestamp detection
        ts_col = next((c for c in df.columns if "time" in c or "date" in c or "timestamp" in c), None)
        if ts_col:
            df["timestamp"] = pd.to_datetime(df[ts_col], errors="coerce", dayfirst=True)
        else:
            df["timestamp"] = pd.NaT
        df["profile_type"] = profile_type.capitalize()
        if "meter_id" in df.columns:
            df["meter_id"] = df["meter_id"].astype(str).str.strip()
            dfs.append(df[["meter_id", "timestamp", "profile_type"]])
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

def expected_samples(profile_type: str, capture_period: int = None) -> int:
    if profile_type.lower() == "instant":
        return 3
    if profile_type.lower() == "daily":
        return 1
    if profile_type.lower() == "billing":
        return 1
    if profile_type.lower() == "block":
        try:
            cp = int(capture_period)
        except Exception:
            cp = 15
        return {15: 96, 30: 48, 60: 24}.get(cp, 96)
    return None

def get_excel_writer(buffer: io.BytesIO):
    try:
        return pd.ExcelWriter(buffer, engine="xlsxwriter")
    except Exception:
        return pd.ExcelWriter(buffer, engine="openpyxl")

def send_email_report(
    email_to: str,
    full_report_bytes: bytes,
    missing_report_bytes: bytes,
    html_report: str,
) -> Tuple[bool, str]:
    """
    Send a report email with attachments. Returns (success, message).
    Cross-platform compatible with fallback support.
    
    This function does not call Streamlit UI functions and is safe to call from run() when user requests.
    """
    # Prepare attachments
    attachments = [
        ("SLA_Week_Performance.xlsx", full_report_bytes),
        ("Missing_Meters_Weekly.xlsx", missing_report_bytes),
    ]
    
    # Send email with automatic fallback
    success, msg = EMAIL_SERVICE.send_email(
        to_email=email_to,
        subject="SLA Week Performance",
        html_body=html_report,
        attachments=attachments,
        use_outlook=True,
    )
    
    return success, msg

# -----------------------
# Main UI entrypoint
# -----------------------

def run():
    """
    Weekly SLA dashboard entrypoint. All Streamlit UI must be inside this function.
    """
    st.header("Weekly SLA : Upload 7 days profiles sheet and check the weekly performance")
    st.markdown("Upload 7-day profile files and the meter list. The dashboard computes day-wise SLA, trends, and OEM comparisons.")

    # Uploaders
    col1, col2 = st.columns(2)
    with col1:
        block_files = st.file_uploader("Upload Block Profile Files (xlsx)", type=["xlsx"], accept_multiple_files=True)
        daily_files = st.file_uploader("Upload Daily Profile Files (xlsx)", type=["xlsx"], accept_multiple_files=True)
    with col2:
        instant_files = st.file_uploader("Upload Instant Profile Files (xlsx)", type=["xlsx"], accept_multiple_files=True)
        billing_files = st.file_uploader("Upload Billing Profile Files (xlsx)", type=["xlsx"], accept_multiple_files=True)
        meter_list_file = st.file_uploader("Upload Meter List (.xlsx)", type=["xlsx"])

    # Basic header info
    report_date = datetime.now().strftime("%d-%b-%Y")
    reporting_period = "No Data Uploaded"
    st.title("📊 Smart Meter Day-wise SLA Dashboard")
    st.caption(f"Report Date: {report_date}")

    if not meter_list_file and not any([block_files, daily_files, instant_files, billing_files]):
        st.info("Upload the meter list and at least one set of profile files to begin.")
        return

    # Read meter list
    meter_list = None
    if meter_list_file:
        try:
            meter_list = pd.read_excel(meter_list_file)
            meter_list.columns = meter_list.columns.str.strip().str.lower()
            # normalize
            if "meter id" in meter_list.columns:
                meter_list.rename(columns={"meter id": "meter_id"}, inplace=True)
            if "oem" in meter_list.columns:
                meter_list.rename(columns={"oem": "OEM"}, inplace=True)
            if "profile_capture_period" in meter_list.columns:
                meter_list.rename(columns={"profile_capture_period": "capture_period"}, inplace=True)
            if "meter_id" not in meter_list.columns:
                st.error("Meter list must contain a meter_id column.")
                return
            meter_list["meter_id"] = meter_list["meter_id"].astype(str).str.strip()
        except Exception as e:
            st.error(f"Failed to read meter list: {e}")
            return

    # Read profiles
    with st.spinner("Reading profile files..."):
        block_df = read_profile(block_files, "Block") if block_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        daily_df = read_profile(daily_files, "Daily") if daily_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        instant_df = read_profile(instant_files, "Instant") if instant_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        billing_df = read_profile(billing_files, "Billing") if billing_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

    profiles = pd.concat([block_df, daily_df, instant_df, billing_df], ignore_index=True) if not (block_df.empty and daily_df.empty and instant_df.empty and billing_df.empty) else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

    if profiles.empty:
        st.error("No valid profile data found in uploaded files.")
        return

    # Ensure timestamps valid
    profiles["timestamp"] = pd.to_datetime(profiles["timestamp"], errors="coerce", dayfirst=True)
    profiles = profiles.dropna(subset=["timestamp"])
    if profiles.empty:
        st.error("No valid timestamps found in profiles.")
        return

    # Reporting period
    min_date = profiles["timestamp"].min().date()
    max_date = profiles["timestamp"].max().date()
    reporting_period = f"{min_date.strftime('%d-%b')} to {max_date.strftime('%d-%b')}"
    st.subheader(f"Reporting Period: {reporting_period}")

    # Merge with meter list if available
    merged = meter_list.merge(profiles, on="meter_id", how="left") if meter_list is not None else profiles.copy()
    merged["date"] = merged["timestamp"].dt.date

    # Per-meter daily aggregation
    per_meter = merged.groupby(["OEM", "date", "profile_type", "meter_id", "capture_period"], dropna=False).agg(
        actual_records=("timestamp", "count")
    ).reset_index()

    # Compute expected and SLA
    per_meter["expected"] = per_meter.apply(lambda r: expected_samples(r["profile_type"], r.get("capture_period", None)), axis=1)
    per_meter["sla_met"] = (per_meter["actual_records"] >= per_meter["expected"]).astype(int)
    per_meter["achieved_percent"] = np.where(per_meter["expected"] > 0, per_meter["actual_records"] / per_meter["expected"] * 100, 0)

    # Compliance summary
    compliance_summary = per_meter.groupby(["OEM", "date", "profile_type"], dropna=False).agg(
        meters_achieved=("sla_met", "sum")
    ).reset_index()

    total_meters = merged.groupby(["OEM", "date"])["meter_id"].nunique().reset_index(name="Total Meters")

    st.header("📊 Day-wise SLA Compliance Summary")
    st.dataframe(compliance_summary, use_container_width=True)

    st.header("📊 Meter-wise Daily SLA Performance (All Profiles)")
    st.dataframe(per_meter, use_container_width=True)

    # OEM raw counts charts
    st.header("📊 OEM-wise SLA Performance (Raw Counts Only)")
    palette_raw = {
        "Total Meters": "#6EC1F2",
        "Block": "#F29AC2",
        "Daily": "#F7D774",
        "Instant": "#8EE3A6",
        "Billing": "#CFA0F5"
    }
    profile_order = ["Total Meters", "Block", "Daily", "Instant", "Billing"]
    chart_images = {}

    for oem in compliance_summary["OEM"].dropna().unique():
        st.subheader(f"OEM: {oem}")
        oem_data = compliance_summary[compliance_summary["OEM"] == oem]
        if oem_data.empty:
            continue

        comparison_pivot = oem_data.pivot(index="date", columns="profile_type", values="meters_achieved").fillna(0)
        # merge total meters
        tm = total_meters[total_meters["OEM"] == oem][["date", "Total Meters"]]
        if not tm.empty:
            comparison_pivot = comparison_pivot.merge(tm, left_index=True, right_on="date", how="left").set_index("date")
        else:
            comparison_pivot["Total Meters"] = 0

        for col in profile_order:
            if col not in comparison_pivot.columns:
                comparison_pivot[col] = 0

        chart_data = comparison_pivot.reset_index()
        melted = chart_data.melt(id_vars="date", value_vars=profile_order, var_name="Profile", value_name="Meters")

        fig, ax = plt.subplots(figsize=(12, 5))
        sns.barplot(data=melted, x="date", y="Meters", hue="Profile", hue_order=profile_order, palette=palette_raw, ax=ax)
        ax.set_title(f"Raw SLA Counts – {oem}")
        ax.set_xlabel("Date")
        ax.set_ylabel("Meters Achieved 100%")
        plt.xticks(rotation=0)
        plt.tight_layout()
        st.pyplot(fig)
        chart_images[oem] = fig_to_base64(fig)
        plt.close(fig)

    # 7-day trend
    st.header("📈 7-Day Trend of Achieved Meters (Profile-wise)")
    trend_data = compliance_summary.groupby(["date", "profile_type"])["meters_achieved"].sum().reset_index()
    if not trend_data.empty:
        trend_chart = alt.Chart(trend_data).mark_line(point=True, interpolate='monotone').encode(
            x="yearmonthdate(date):T",
            y="meters_achieved:Q",
            color="profile_type:N",
            tooltip=["date:T", "profile_type:N", "meters_achieved:Q"]
        ).properties(height=320)
        st.altair_chart(trend_chart, use_container_width=True)

    # OEM heatmap
    st.header("🏆 OEM Comparison View (Profile-wise SLA %)")
    oem_comparison = compliance_summary.merge(total_meters, on=["OEM", "date"], how="left")
    oem_comparison["sla_percent"] = np.where(oem_comparison["Total Meters"] > 0, oem_comparison["meters_achieved"] / oem_comparison["Total Meters"] * 100, 0)
    oem_profile_avg = oem_comparison.groupby(["OEM", "profile_type"])["sla_percent"].mean().reset_index()
    if not oem_profile_avg.empty:
        heatmap = alt.Chart(oem_profile_avg).mark_rect().encode(
            x="profile_type:N",
            y="OEM:N",
            color="sla_percent:Q",
            tooltip=["OEM:N", "profile_type:N", "sla_percent:Q"]
        ).properties(height=300)
        st.altair_chart(heatmap, use_container_width=True)

    # Downloads
    st.header("📥 Download Report Data")
    missing_details = merged[merged["timestamp"].isna()][["meter_id", "OEM"]].drop_duplicates() if not merged.empty else pd.DataFrame()
    missing_output = io.BytesIO()
    with get_excel_writer(missing_output) as writer:
        missing_details.to_excel(writer, index=False, sheet_name="Missing Meters")
        meta = pd.DataFrame({"Field": ["Reporting Period", "Report Date"], "Value": [reporting_period, report_date]})
        meta.to_excel(writer, index=False, sheet_name="Report Info")
    st.download_button(
        label="📥 Download Missing Meters Only (Excel)",
        data=missing_output.getvalue(),
        file_name=f"Missing_Meters_{report_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Full report
    output = io.BytesIO()
    with get_excel_writer(output) as writer:
        compliance_summary.to_excel(writer, index=False, sheet_name="SLA Summary")
        oem_profile_avg.to_excel(writer, index=False, sheet_name="OEM SLA")
        trend_data.to_excel(writer, index=False, sheet_name="Trend Data")
        merged.to_excel(writer, index=False, sheet_name="Raw Data")
        meta = pd.DataFrame({"Field": ["Reporting Period", "Report Date"], "Value": [reporting_period, report_date]})
        meta.to_excel(writer, index=False, sheet_name="Report Info")
    st.download_button(
        label="📥 Download Full Report (Excel)",
        data=output.getvalue(),
        file_name=f"SmartMeter_Report_{report_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # HTML report
    st.subheader("📄 Download HTML Report")
    html_report = f"<html><body><h1>Smart Meter SLA Dashboard Report</h1><p><b>Reporting Period:</b> {reporting_period}<br><b>Report Date:</b> {report_date}</p>"
    for oem, img in chart_images.items():
        html_report += f"<h2>OEM-wise SLA Performance – {oem}</h2><img src='data:image/png;base64,{img}'/>"
    html_report += "<h2>SLA Summary</h2>" + compliance_summary.to_html(index=False)
    html_report += "<h2>OEM SLA Summary</h2>" + oem_profile_avg.to_html(index=False)
    html_report += "<h2>Missing Meters</h2>" + (missing_details.to_html(index=False) if not missing_details.empty else "<p>No missing meters.</p>")
    html_report += "</body></html>"

    st.download_button(
        label="📄 Download HTML Report",
        data=html_report.encode("utf-8"),
        file_name=f"SLA_Report_{report_date}.html",
        mime="text/html"
    )

    # Email send UI
    st.subheader("📧 Email Reports")
    email_to = st.text_input("Enter recipient email address")
    if st.button("Send Reports via Email"):
        if not email_to:
            st.error("Please enter a recipient email address.")
        else:
            with st.spinner("Sending email..."):
                try:
                    ok, msg = send_email_report(email_to, output.getvalue(), missing_output.getvalue(), html_report)
                    if ok:
                        st.success(f"Reports sent successfully! {msg}")
                    else:
                        st.error(f"Failed to send email: {msg}")
                except Exception as e:
                    st.error(f"Failed to send email: {e}")
                    logger.error(f"Email send failed: {e}")

if __name__ == "__main__":
    run()
