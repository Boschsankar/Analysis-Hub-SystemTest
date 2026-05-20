# _pages/daily_data_analysis.py
import streamlit as st
import altair as alt
import pandas as pd
import numpy as np
import io
import os
import pythoncom
import win32com.client as win32
import matplotlib.pyplot as plt
import base64
import seaborn as sns
import zipfile
from typing import List, Tuple

# -----------------------
# Helpers (pure functions / IO helpers)
# -----------------------

def get_excel_files(uploads: List[io.BytesIO]) -> List[io.BytesIO]:
    """Accepts a list of uploaded files (Streamlit UploadedFile or BytesIO) and returns a list of BytesIO xlsx/csv files."""
    excel_files = []
    for upload in uploads or []:
        name = getattr(upload, "name", None) or ""
        try:
            if name.lower().endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(upload.read())) as zf:
                    for file_name in zf.namelist():
                        if file_name.lower().endswith((".xlsx", ".csv")):
                            with zf.open(file_name) as f:
                                excel_files.append(io.BytesIO(f.read()))
            elif name.lower().endswith((".xlsx", ".csv")):
                # Streamlit UploadedFile is file-like; keep as-is
                excel_files.append(upload)
        except Exception:
            # skip problematic uploads
            continue
    return excel_files

def normalize_columns(columns: pd.Index) -> pd.Index:
    return (
        columns.str.strip()
        .str.lower()
        .str.replace(r"[^0-9a-z]+", "_", regex=True)
    )

def read_profile(files: List[io.BytesIO], profile_type: str) -> pd.DataFrame:
    """
    Read a list of excel/csv files and return a DataFrame with columns:
    meter_id, timestamp, profile_type
    """
    dfs = []
    invalid_files = []

    rename_map = {
        "device_id": "meter_id",
        "meterid": "meter_id",
        "meter_id": "meter_id",
        "meter_no": "meter_id",
        "meter_number": "meter_id",
        "mtr_id": "meter_id",
        "meter": "meter_id",
        "meter_date_and_time": "timestamp",
        "meter_date_time": "timestamp",
        "meter_date__time": "timestamp",
        "meter_date": "timestamp",
        "meter_time": "timestamp",
        "hes_received_time": "timestamp",
        "hes_received_timestamp": "timestamp",
        "date_time": "timestamp",
        "datetime": "timestamp",
        "timestamp": "timestamp",
    }

    for f in files or []:
        file_name = getattr(f, "name", None) or "uploaded_file"
        try:
            # handle BytesIO vs UploadedFile
            if hasattr(f, "read") and not isinstance(f, (str, bytes)):
                # Streamlit UploadedFile or BytesIO
                try:
                    df = pd.read_excel(f)
                except Exception:
                    try:
                        f.seek(0)
                        df = pd.read_csv(f)
                    except Exception as e:
                        invalid_files.append((file_name, str(e)))
                        continue
            else:
                invalid_files.append((file_name, "Unsupported file object"))
                continue

            df.columns = normalize_columns(df.columns)
            df.rename(columns=rename_map, inplace=True)

            if "meter_id" not in df.columns or "timestamp" not in df.columns:
                invalid_files.append((file_name, list(df.columns)))
                continue

            df["meter_id"] = df["meter_id"].astype(str).str.strip()
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", dayfirst=True)
            df = df.dropna(subset=["timestamp"])
            df["profile_type"] = profile_type
            dfs.append(df[["meter_id", "timestamp", "profile_type"]])
        except Exception as e:
            invalid_files.append((file_name, str(e)))
            continue

    if invalid_files:
        # Return warning via exception or empty DataFrame; caller will show warnings
        # We'll attach a small attribute to the returned DataFrame for diagnostics
        msg = "\n".join([f"- {n}: {m}" for n, m in invalid_files])
        # create a DataFrame and attach diagnostics
        df_out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        df_out._invalid_files = msg  # type: ignore
        return df_out

    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

def get_excel_writer(buffer: io.BytesIO):
    """Return a pandas ExcelWriter using available engine."""
    try:
        return pd.ExcelWriter(buffer, engine="xlsxwriter")
    except Exception:
        return pd.ExcelWriter(buffer, engine="openpyxl")

def _save_png_from_plt(fig, path: str):
    try:
        fig.savefig(path, bbox_inches="tight")
    except Exception:
        pass

def send_outlook_report(
    to_email: str,
    full_report_bytes: bytes,
    missing_report_bytes: bytes,
    html_report_str: str,
    attachments_paths: List[str] = None
) -> Tuple[bool, str]:
    """
    Send an Outlook email with attachments. Returns (success, message).
    This function does not call Streamlit UI functions.
    """
    try:
        pythoncom.CoInitialize()
        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.To = to_email
        mail.Subject = "Smart Meter Daily Report"
        mail.HTMLBody = html_report_str

        # Save temporary files and attach
        tmp_full = os.path.abspath("SmartMeter_Report.xlsx")
        tmp_missing = os.path.abspath("Missing_Meters.xlsx")
        with open(tmp_full, "wb") as f:
            f.write(full_report_bytes)
        with open(tmp_missing, "wb") as f:
            f.write(missing_report_bytes)

        mail.Attachments.Add(tmp_full)
        mail.Attachments.Add(tmp_missing)

        for p in attachments_paths or []:
            if os.path.exists(p):
                mail.Attachments.Add(os.path.abspath(p))

        mail.Send()
        pythoncom.CoUninitialize()
        return True, "Email sent"
    except Exception as e:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        return False, str(e)

# -----------------------
# Main UI entrypoint
# -----------------------

def run():
    """
    Safe entrypoint for daily data analysis. All Streamlit UI must be inside this function.
    """
    st.header("Daily SLA : Upload the profile files and check the SLA for 24hours")
    st.markdown("Upload Block / Instant / Daily / Billing profile files (xlsx or zip of xlsx). Also upload the actual meter list (.xlsx).")

    # Uploaders
    col1, col2 = st.columns(2)
    with col1:
        block_uploads = st.file_uploader("Upload Block Profile Files or Zips", type=["xlsx", "zip"], accept_multiple_files=True)
        instant_uploads = st.file_uploader("Upload Instant Profile Files or Zips", type=["xlsx", "zip"], accept_multiple_files=True)
    with col2:
        daily_uploads = st.file_uploader("Upload Daily Profile Files or Zips", type=["xlsx", "zip"], accept_multiple_files=True)
        billing_uploads = st.file_uploader("Upload Billing Profile Files or Zips", type=["xlsx", "zip"], accept_multiple_files=True)
        meter_list_file = st.file_uploader("Upload Actual Meter List (.xlsx)", type=["xlsx"])

    # Nothing uploaded yet
    if not any([block_uploads, instant_uploads, daily_uploads, billing_uploads, meter_list_file]):
        st.info("Upload profile files and the meter list to begin daily analysis.")
        return

    # Extract excel files from uploads (zip handling)
    with st.spinner("Processing uploaded files..."):
        block_files = get_excel_files(block_uploads) if block_uploads else []
        instant_files = get_excel_files(instant_uploads) if instant_uploads else []
        daily_files = get_excel_files(daily_uploads) if daily_uploads else []
        billing_files = get_excel_files(billing_uploads) if billing_uploads else []

    # Read meter list
    meter_list = None
    if meter_list_file:
        try:
            meter_list = pd.read_excel(meter_list_file)
            meter_list.columns = meter_list.columns.str.strip().str.lower()
        except Exception as e:
            st.error(f"Failed to read meter list: {e}")
            return

    # Validate meter list capture period
    if meter_list is None:
        st.warning("Meter list not provided. Some analyses require the meter list.")
    else:
        possible_capture_cols = [
            "profile_capture_period",
            "profile capture period",
            "capture_period",
            "capture period",
            "period",
            "interval",
            "block_period"
        ]
        capture_col_found = None
        for col in possible_capture_cols:
            if col in meter_list.columns:
                capture_col_found = col
                break

        if capture_col_found:
            meter_list.rename(columns={capture_col_found: "capture_period"}, inplace=True)
        else:
            st.error("❌ ERROR: No capture period column found in meter list.")
            return

        # Normalize meter id and OEM
        if "meter id" in meter_list.columns:
            meter_list.rename(columns={"meter id": "meter_id"}, inplace=True)
        if "oem" in meter_list.columns:
            meter_list.rename(columns={"oem": "OEM"}, inplace=True)

        if "meter_id" not in meter_list.columns:
            st.error("Meter list must contain a meter_id column.")
            return

        meter_list["meter_id"] = meter_list["meter_id"].astype(str).str.strip()

    # Read profiles
    with st.spinner("Reading profile files..."):
        block_df = read_profile(block_files, "Block").reset_index(drop=True) if block_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        instant_df = read_profile(instant_files, "Instant").reset_index(drop=True) if instant_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        daily_df = read_profile(daily_files, "Daily").reset_index(drop=True) if daily_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        billing_df = read_profile(billing_files, "Billing").reset_index(drop=True) if billing_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

    # Collect invalid file warnings if any
    invalid_msgs = []
    for df in (block_df, instant_df, daily_df, billing_df):
        if hasattr(df, "_invalid_files"):
            invalid_msgs.append(getattr(df, "_invalid_files"))

    if invalid_msgs:
        st.warning("Some uploaded profile files were skipped or had issues:\n" + "\n".join(invalid_msgs))

    # Combine profiles
    profiles = pd.concat([block_df, instant_df, daily_df, billing_df], ignore_index=True) if not (block_df.empty and instant_df.empty and daily_df.empty and billing_df.empty) else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

    if profiles.empty:
        st.error("No valid profile data found in uploaded files.")
        return

    # Ensure timestamp column is datetime
    profiles["timestamp"] = pd.to_datetime(profiles["timestamp"], errors="coerce", dayfirst=True)
    profiles = profiles.dropna(subset=["timestamp"])
    if profiles.empty:
        st.error("No valid timestamps found in profiles.")
        return

    # Reporting date and KPIs
    reporting_date = profiles["timestamp"].max().strftime("%d-%b-%Y")
    st.markdown(f"### 📅 Reporting Date: **{reporting_date}**")

    total_meters = meter_list["meter_id"].nunique() if meter_list is not None else profiles["meter_id"].nunique()
    reporting_meters = profiles["meter_id"].nunique()
    non_reporting = total_meters - reporting_meters if meter_list is not None else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Meters", total_meters)
    c2.metric("Reporting Meters", reporting_meters)
    c3.metric("Non-Reporting", non_reporting)

    # Capture period split-up
    if meter_list is not None:
        capture_summary = meter_list.groupby("capture_period")["meter_id"].nunique().reset_index()
        capture_summary.rename(columns={"meter_id": "Total Meters"}, inplace=True)
        st.subheader("⏱️ Capture Period Split-up")
        st.dataframe(capture_summary, use_container_width=True)

        # Pie chart
        fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
        ax.pie(
            capture_summary["Total Meters"],
            labels=capture_summary["capture_period"],
            autopct="%1.1f%%",
            startangle=140,
            colors=sns.color_palette("pastel"),
            textprops={"fontsize": 8}
        )
        ax.set_title("Capture Period Split-up", fontsize=10)
        plt.tight_layout()
        st.pyplot(fig)

    # Merge with meter list if available
    merged = meter_list.merge(profiles, on="meter_id", how="left") if meter_list is not None else profiles.copy()

    # Profile-level summary (raw)
    meter_summary_raw = (
        merged.groupby(["meter_id", "OEM", "profile_type"])
        .agg(actual_samples=("timestamp", "count"))
        .reset_index()
    )

    # Ensure all meters have required profiles
    required_profiles = ["Block", "Instant", "Daily", "Billing"]
    if meter_list is not None:
        full_matrix = (
            meter_list[["meter_id", "OEM", "capture_period"]]
            .assign(key=1)
            .merge(pd.DataFrame({"profile_type": required_profiles, "key": 1}), on="key")
            .drop("key", axis=1)
        )
    else:
        # If no meter list, build from observed meters
        observed_meters = pd.DataFrame({"meter_id": profiles["meter_id"].unique()})
        full_matrix = observed_meters.assign(key=1).merge(pd.DataFrame({"profile_type": required_profiles, "key": 1}), on="key").drop("key", axis=1)
        full_matrix["OEM"] = np.nan
        full_matrix["capture_period"] = np.nan

    meter_summary = full_matrix.merge(
        meter_summary_raw,
        on=["meter_id", "OEM", "profile_type"],
        how="left"
    )
    meter_summary["actual_samples"] = meter_summary["actual_samples"].fillna(0)

    # Expected samples logic
    def expected_samples(row):
        if row["profile_type"] == "Instant":
            return 3
        if row["profile_type"] == "Daily":
            return 1
        if row["profile_type"] == "Billing":
            return 1
        if row["profile_type"] == "Block":
            try:
                cp = int(row.get("capture_period", 0))
            except Exception:
                cp = 0
            if cp == 15:
                return 96
            if cp == 30:
                return 48
            if cp == 60:
                return 24
        return None

    meter_summary["expected_samples"] = meter_summary.apply(expected_samples, axis=1)

    # Achieved %
    meter_summary["achieved_percent"] = np.where(
        (meter_summary["actual_samples"] > 0) & (meter_summary["expected_samples"].notna()),
        (meter_summary["actual_samples"] / meter_summary["expected_samples"]) * 100,
        0
    )

    # Meter-level aggregation
    meter_level = meter_summary.groupby("meter_id").agg(
        total_actual=("actual_samples", "sum"),
        total_expected=("expected_samples", "sum"),
        profiles_reporting=("actual_samples", lambda x: (x > 0).sum())
    ).reset_index()

    meter_level["is_reporting"] = meter_level["profiles_reporting"] == 4
    meter_level["overall_percent"] = np.where(
        meter_level["total_expected"] > 0,
        (meter_level["total_actual"] / meter_level["total_expected"]) * 100,
        0
    )

    reporting_meters = meter_level[meter_level["profiles_reporting"] > 0].shape[0]
    non_reporting_meters = total_meters - reporting_meters if total_meters else 0

    full_achieved_count = meter_level[meter_level["overall_percent"] == 100].shape[0]
    summary_percent = (full_achieved_count / total_meters) * 100 if total_meters > 0 else 0

    # KPI cards (simple)
    st.header("📊 Communication status")
    c1, c2 = st.columns(2)
    c1.markdown(f"**Communicating Meters**\n\n**{reporting_meters}**")
    c2.markdown(f"**Non-Communicating Meters**\n\n**{non_reporting_meters}**")

    # OEM Performance Summary
    st.header("🏭 Communication status - OEM wise")
    oem_kpi = meter_list.merge(
        meter_level[["meter_id", "profiles_reporting"]],
        on="meter_id",
        how="left"
    ).groupby("OEM").agg(
        total_meters=("meter_id", "nunique"),
        reporting=("profiles_reporting", lambda x: (x > 0).sum()),
        non_reporting=("profiles_reporting", lambda x: (x == 0).sum())
    ).reset_index()
    oem_kpi["Reporting %"] = (oem_kpi["reporting"] / oem_kpi["total_meters"]) * 100
    oem_kpi["Non-Reporting %"] = (oem_kpi["non_reporting"] / oem_kpi["total_meters"]) * 100
    st.dataframe(oem_kpi, use_container_width=True)

    # Profile-wise KPI Summary
    st.header("📌 SLA Performance - Profile-wise")
    profile_kpi = meter_summary.groupby("profile_type").agg(
        total_meters=("meter_id", "nunique"),
        reporting=("actual_samples", lambda x: (x > 0).sum()),
        non_reporting=("actual_samples", lambda x: (x == 0).sum()),
        avg_achieved=("achieved_percent", "mean"),
        full_achieved=("achieved_percent", lambda x: (x == 100).sum())
    ).reset_index()
    profile_kpi["%_full_achieved"] = (profile_kpi["full_achieved"] / profile_kpi["total_meters"]) * 100
    st.dataframe(profile_kpi, use_container_width=True)

    # OEM-wise profile performance chart (100% achieved)
    st.header("📌 OEM-wise 100% Achieved Meters by Profile")
    profile_oem_kpi = meter_summary.groupby(["OEM", "profile_type"]).agg(
        full_achieved=("achieved_percent", lambda x: (x == 100).sum())
    ).reset_index()

    meter_level_with_oem = meter_level.merge(meter_list[["meter_id", "OEM"]], on="meter_id", how="left")
    oem_total_counts = meter_list.groupby("OEM")["meter_id"].nunique().reset_index(name="total_meters")
    full_achieved_totals = meter_level_with_oem.groupby("OEM")["overall_percent"].apply(lambda x: (x == 100).sum()).reset_index(name="full_achieved")
    oem_totals = oem_total_counts.merge(full_achieved_totals, on="OEM")
    oem_totals["profile_type"] = "Total"
    profile_oem_kpi = pd.concat([profile_oem_kpi, oem_totals], ignore_index=True)

    comparison_pivot = profile_oem_kpi.pivot(index="OEM", columns="profile_type", values="full_achieved").fillna(0)
    profile_order = ["Total", "Daily", "Block", "Instant", "Billing"]
    melted = comparison_pivot.reset_index().melt(id_vars="OEM", value_vars=profile_order, var_name="Profile", value_name="Meters")
    melted = melted.merge(oem_totals[["OEM", "total_meters"]], on="OEM")
    melted["Percent"] = (melted["Meters"] / melted["total_meters"] * 100).round(1)

    plt.figure(figsize=(10, 5))
    ax = sns.barplot(data=melted, x="OEM", y="Meters", hue="Profile", hue_order=profile_order, palette="Set2")
    for container in ax.containers:
        ax.bar_label(container, labels=[f"{int(v.get_height())}" if v.get_height() > 0 else "" for v in container], fontsize=8, padding=2)
    plt.title("OEM-wise 100% Achieved Meters by Profile")
    plt.tight_layout()
    st.pyplot(plt)

    # Meter-wise Performance (combined)
    st.header("📋 Meter-wise Performance (Combined)")
    pivot = meter_summary.pivot_table(
        index="meter_id",
        columns="profile_type",
        values=["actual_samples", "expected_samples", "achieved_percent"],
        aggfunc="first"
    )
    if not pivot.empty:
        pivot.columns = [f"{metric}_{profile}" for metric, profile in pivot.columns]
    meter_combined = meter_list.merge(meter_level, on="meter_id", how="left")
    meter_combined = meter_combined.merge(pivot, on="meter_id", how="left")
    display_cols = [
        "meter_id", "OEM", "capture_period",
        "actual_samples_Block", "expected_samples_Block", "achieved_percent_Block",
        "actual_samples_Instant", "expected_samples_Instant", "achieved_percent_Instant",
        "actual_samples_Daily", "expected_samples_Daily", "achieved_percent_Daily",
        "actual_samples_Billing", "expected_samples_Billing", "achieved_percent_Billing",
        "total_actual", "total_expected", "overall_percent",
        "profiles_reporting", "is_reporting"
    ]
    meter_combined_display = meter_combined[[c for c in display_cols if c in meter_combined.columns]].sort_values("overall_percent") if not meter_combined.empty else pd.DataFrame()
    st.dataframe(meter_combined_display, use_container_width=True)

    # Missing meters
    st.header("❌ Missing Meters")
    missing_ids = meter_level[meter_level["profiles_reporting"] == 0]["meter_id"] if "profiles_reporting" in meter_level.columns else pd.Series(dtype=object)
    missing_details = meter_summary[meter_summary["meter_id"].isin(missing_ids)] if not missing_ids.empty else pd.DataFrame()
    if missing_details.empty:
        st.success("🎉 No missing meters — all meters received at least one profile.")
    else:
        st.error(f"⚠️ {missing_ids.nunique()} meters did not report any profile.")
        st.subheader("Missing Meter Details (Table)")
        missing_table = missing_details.copy()
        missing_table["Status"] = "Missing (No Profiles Received)"
        cols = ["Status"] + [c for c in missing_table.columns if c != "Status"]
        missing_table = missing_table[cols]
        st.dataframe(missing_table, use_container_width=True)

        # Missing meters by OEM chart
        st.header("📊 Missing Meters by OEM")
        missing_by_oem = missing_details.groupby("OEM")["meter_id"].nunique().reset_index(name="missing_count")
        if not missing_by_oem.empty:
            plt.figure(figsize=(10, 5))
            ax = sns.barplot(data=missing_by_oem, x="OEM", y="missing_count", palette="Reds")
            for container in ax.containers:
                ax.bar_label(container, labels=[f"{int(v.get_height())}" if v.get_height() > 0 else "" for v in container], fontsize=8, padding=2)
            plt.title("Missing Meters by OEM")
            plt.tight_layout()
            st.pyplot(plt)
        else:
            st.info("No missing meters to chart.")

    # Build full report Excel
    st.header("📥 Download Complete Report")
    try:
        output = io.BytesIO()
        with get_excel_writer(output) as writer:
            meter_summary.to_excel(writer, index=False, sheet_name="Meter Summary")
            meter_level.to_excel(writer, index=False, sheet_name="Meter Level Summary")
            oem_kpi.to_excel(writer, index=False, sheet_name="OEM Communication Status")
            if 'capture_summary' in locals():
                capture_summary.to_excel(writer, index=False, sheet_name="Capture Period Split-up")
            profile_kpi.to_excel(writer, index=False, sheet_name="Profile SLA Performance")
            profile_oem_kpi.to_excel(writer, index=False, sheet_name="OEM Profile SLA Performance")
            if not meter_combined_display.empty:
                meter_combined_display.to_excel(writer, index=False, sheet_name="Meter Combined Performance")
            merged.to_excel(writer, index=False, sheet_name="Raw Data")
        st.download_button(
            label="📥 Download Full Report (Excel)",
            data=output.getvalue(),
            file_name="SmartMeter_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="full_report_download"
        )
    except Exception as e:
        st.warning(f"Download not available: {e}")

    # Missing meters report
    try:
        missing_output = io.BytesIO()
        with get_excel_writer(missing_output) as writer:
            if not missing_details.empty:
                missing_table.to_excel(writer, index=False, sheet_name="Missing Meters")
            else:
                pd.DataFrame({"Status": ["No missing meters"]}).to_excel(writer, index=False, sheet_name="Missing Meters")
        st.download_button(
            label="📥 Download Missing Meters Report (Excel)",
            data=missing_output.getvalue(),
            file_name="Missing_Meters.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="missing_report_download"
        )
    except Exception as e:
        st.warning(f"Missing report download not available: {e}")

    # Build HTML dashboard report (string)
    html_report = "<html><head><meta charset='utf-8'><style>body{font-family:Arial,sans-serif;margin:20px;}th,td{border:1px solid #ddd;padding:6px;font-size:12px;}th{background:#f2f2f2;}</style></head><body>"
    html_report += "<h1>Smart Meter Dashboard Report</h1>"
    html_report += "<h2>Overall KPIs</h2>"
    html_report += f"<p>Total Meters: <b>{total_meters}</b><br>Communicating Meters: <b>{reporting_meters}</b><br>Non-Communicating Meters: <b>{non_reporting_meters}</b><br>100% Achieved Meters: <b>{full_achieved_count}</b><br>% of 100% Achieved: <b>{summary_percent:.2f}%</b></p>"
    html_report += "<h2>OEM Performance Summary</h2>"
    html_report += oem_kpi.to_html(index=False, border=0)
    html_report += "<h2>Profile-wise KPI Summary</h2>"
    html_report += profile_kpi.to_html(index=False, border=0)
    html_report += "<h2>Meter-wise Performance (Combined)</h2>"
    if not meter_combined_display.empty:
        html_report += meter_combined_display.to_html(index=False, border=0)
    if not missing_details.empty:
        html_report += "<h2>Missing Meter Details</h2>"
        html_report += missing_table.to_html(index=False, border=0)
    else:
        html_report += "<h2>Missing Meter Details</h2><p>No missing meters.</p>"
    html_report += "</body></html>"

    # Email sending UI (call send_outlook_report on demand)
    st.markdown("### 📧 Email Reports")
    with st.form(key="email_form"):
        to_email = st.text_input("Send report to (email):", value="", placeholder="recipient@example.com")
        send_now = st.form_submit_button("Send Reports via Outlook")
        if send_now:
            if not to_email:
                st.error("Please enter a recipient email address.")
            else:
                # Prepare bytes for attachments
                try:
                    full_bytes = output.getvalue()
                except Exception:
                    full_bytes = b""
                try:
                    missing_bytes = missing_output.getvalue()
                except Exception:
                    missing_bytes = b""
                # Save small charts to temp files to attach (optional)
                attachments = []
                # Example: capture_period_chart.png and missing_oem_chart.png may have been saved earlier by plotting code
                for fname in ["capture_period_chart.png", "missing_oem_chart.png", "oem_profile_chart.png"]:
                    if os.path.exists(fname):
                        attachments.append(os.path.abspath(fname))

                with st.spinner("Sending email via Outlook..."):
                    ok, msg = send_outlook_report(to_email, full_bytes, missing_bytes, html_report, attachments)
                    if ok:
                        st.success("Reports sent successfully via Outlook!")
                    else:
                        st.error(f"Failed to send email: {msg}")

if __name__ == "__main__":
    run()
