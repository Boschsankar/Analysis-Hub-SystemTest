import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import datetime

# --------------------------------------------------
# HUB COMPATIBILITY ENTRYPOINT
# --------------------------------------------------

def run():
    """Compatibility entrypoint for the main app registry.

    The dashboard content is intentionally structured as top-level Streamlit code so it
    also works as a standalone script when launched directly with `streamlit run`.
    """
    return


# --------------------------------------------------
# CONFIG
# --------------------------------------------------

st.set_page_config(
    page_title="NMS-HES Healthy Percentage Dashboard",
    layout="wide"
)

st.title("AMI NMS ↔ HES Healthy Percentage Monitoring Dashboard")

st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
        border: 1px solid #dbeafe;
        border-radius: 0.9rem;
        padding: 0.8rem 1rem;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
    }
    div[data-testid="stMetricLabel"] {
        font-weight: 600;
        color: #334155;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0f172a;
    }
    .section-header {
        background: linear-gradient(90deg, #0f172a 0%, #1d4ed8 100%);
        color: white;
        padding: 0.7rem 1rem;
        border-radius: 0.6rem;
        margin-top: 1.2rem;
        margin-bottom: 0.6rem;
        font-weight: 700;
    }
    .info-box {
        border-left: 5px solid #2563eb;
        background: #eff6ff;
        padding: 0.8rem 1rem;
        border-radius: 0.5rem;
        color: #1e3a8a;
        margin-bottom: 0.9rem;
    }
    .field-note {
        border-left: 5px solid #f59e0b;
        background: #fff7ed;
        padding: 0.8rem 1rem;
        border-radius: 0.5rem;
        color: #9a5b00;
        margin-bottom: 1rem;
    }
    .kpi-badge {
        display: inline-block;
        padding: 0.3rem 0.6rem;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.03em;
    }
    .healthy-note { border-left: 5px solid #10b981; background: #ecfdf5; padding: 0.6rem 1rem; border-radius:0.5rem; color:#065f46; margin-bottom:0.75rem; }
    .summary-card { padding: 0.8rem 1rem; border-radius: 0.75rem; text-align:center; }
    .summary-label { font-weight:700; color:#0f172a; }
    .summary-value { font-size:1.6rem; font-weight:800; margin-top:6px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

st.sidebar.header("Healthy Percentage Configuration")

COMM_DELAY_HRS = st.sidebar.number_input(
    "Communication Delay (Hours)",
    value=24,
    min_value=1
)

SYNC_DELAY_HRS = st.sidebar.number_input(
    "HES Sync Delay (Hours)",
    value=24,
    min_value=1
)

DORMANT_DAYS = st.sidebar.number_input(
    "Dormant Threshold (Days)",
    value=7,
    min_value=1
)

# Add short help text for each threshold so users understand impact
st.sidebar.markdown("---")
st.sidebar.info(
    "`Communication Delay (Hours)`: Meters silent longer than this are marked `COMMUNICATION_DELAY` (Amber).\n\n"
    "`HES Sync Delay (Hours)`: Difference between NMS activity and HES last comm; exceeding this marks `HES_SYNC_DELAY` (Amber).\n\n"
    "`Dormant Threshold (Days)`: Meters with no comms longer than this are marked `DORMANT_METER` (Critical) and prioritised for field action."
)

# --------------------------------------------------
# FILE UPLOAD
# --------------------------------------------------

nms_file = st.file_uploader(
    "Upload NMS CSV",
    type=["csv"]
)

hes_files = st.file_uploader(
    "Upload HES Asset Files",
    type=["xlsx"],
    accept_multiple_files=True
)

STATUS_FILTER = st.sidebar.multiselect(
    "NMS Status Filter",
    options=["ACTIVE", "INACTIVE", "OFFLINE"],
    default=["ACTIVE", "INACTIVE", "OFFLINE"],
)

SEVERITY_VIEW = st.sidebar.selectbox(
    "Priority View",
    options=["All", "Critical", "Amber", "Healthy"],
    index=0,
)

# Toggle to show/hide HES-specific columns in tables for concise views
SHOW_HES = st.sidebar.checkbox(
    "Show HES Columns in tables",
    value=False,
    key="show_hes",
    help="Toggle HES-specific columns (HES Status, Last Comm, Power, Sync Gap)",
    on_change=None,
)

# Safe rerun helper: some Streamlit builds don't expose `experimental_rerun` as an attribute.
def _rerun_if_available():
    fn = getattr(st, "experimental_rerun", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass

# If the checkbox was toggled in this run, trigger a rerun via the safe helper.
if st.session_state.get("show_hes", False) != SHOW_HES:
    st.session_state["show_hes"] = SHOW_HES
    _rerun_if_available()

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

# Display current thresholds under the main title for quick context
st.markdown(
    f"<div style='margin-top:0.5rem; font-size:0.95rem; color:#374151;'>"
    f"Thresholds: Communication {COMM_DELAY_HRS}h · HES Sync {SYNC_DELAY_HRS}h · Dormant {DORMANT_DAYS}d"
    f"</div>",
    unsafe_allow_html=True,
)

def safe_datetime(series):
    return pd.to_datetime(
        series,
        errors="coerce",
        dayfirst=True
    )


def normalize_column_name(column_name):
    return (
        str(column_name)
        .replace("&amp;amp;", "&")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


def find_column(df, *candidates):
    normalized_lookup = {
        normalize_column_name(col): col
        for col in df.columns
    }

    for candidate in candidates:
        if candidate in df.columns:
            return candidate

        alias = normalize_column_name(candidate)
        if alias in normalized_lookup:
            return normalized_lookup[alias]

    return None


def severity_rank(sev):
    ranking = {
        "GREEN": 1,
        "AMBER": 2,
        "RED": 3,
        "CRITICAL": 4
    }
    return ranking.get(sev, 0)


def severity_style(severity):
    severity = str(severity).upper()
    palette = {
        "GREEN": "background-color: #dcfce7; color: #166534;",
        "AMBER": "background-color: #fef3c7; color: #92400e;",
        "RED": "background-color: #fee2e2; color: #991b1b;",
        "CRITICAL": "background-color: #fecaca; color: #7f1d1d;",
    }
    return palette.get(severity, "background-color: #f1f5f9; color: #334155;")


def evaluate_kpi(row):

    nms_status = str(row.get("NMS Status", "")).upper()
    hes_status = str(row.get("HES Status", "")).upper()

    power_status = str(
        row.get("Power Status", "")
    ).upper()

    relay_status = str(
        row.get("Relay Status", "")
    ).upper()

    comm_age = row.get(
        "Comm Age Hours",
        np.nan
    )

    sync_gap = row.get(
        "Sync Gap Hours",
        np.nan
    )

    active_commissioned = (
        nms_status == "ACTIVE"
        and hes_status == "COMMISSIONED"
    )

    last_comm = row.get("Last Comm Date & Time")
    is_current_comm = pd.notna(last_comm) and (
        pd.Timestamp.now() - pd.Timestamp(last_comm)
    ).total_seconds() <= (24 * 3600)

    # Missing in HES
    if pd.isna(row.get("HES Status")):
        return (
            "MISSING_IN_HES",
            "RED",
            "Verify onboarding in HES"
        )

    if active_commissioned and is_current_comm:
        return (
            "HEALTHY",
            "GREEN",
            "No action required"
        )

    # Ignore relay status and power status for the healthy active-commissioned path.
    if active_commissioned and relay_status in ("", "CONNECTED"):

        if (
            not pd.isna(sync_gap)
            and sync_gap > SYNC_DELAY_HRS
        ):
            return (
                "HES_SYNC_DELAY",
                "AMBER",
                "Check HES synchronization"
            )

        if (
            not pd.isna(comm_age)
            and comm_age > COMM_DELAY_HRS
        ):
            return (
                "COMMUNICATION_DELAY",
                "AMBER",
                "Check communication path"
            )

        return (
            "HEALTHY",
            "GREEN",
            "No action required"
        )

    # Low-priority power warning: do not escalate for active commissioned meters.
    if power_status == "POWER OFF":
        if nms_status in {"ACTIVE", "INACTIVE"} and hes_status == "COMMISSIONED":
            return (
                "HES_UI_WARNING",
                "AMBER",
                "Review HES UI / power state"
            )

        return (
            "POWER_FAILURE",
            "CRITICAL",
            "Check meter power supply"
        )

    # Relay issue is intentionally ignored in this healthy-percentage logic.

    # ACTIVE Cases
    if nms_status == "ACTIVE":

        if hes_status == "COMMISSIONED":
            if (
                not pd.isna(sync_gap)
                and sync_gap > SYNC_DELAY_HRS
            ):
                return (
                    "HES_SYNC_DELAY",
                    "AMBER",
                    "Check HES synchronization"
                )

            if (
                not pd.isna(comm_age)
                and comm_age > COMM_DELAY_HRS
            ):
                return (
                    "COMMUNICATION_DELAY",
                    "AMBER",
                    "Check communication path"
                )

            return (
                "HEALTHY",
                "GREEN",
                "No action required"
            )

        elif hes_status == "INSTALLED":
            return (
                "NIC_REGISTRATION_PENDING",
                "RED",
                "Verify commissioning"
            )

        elif hes_status == "DE-COMMISSIONED":
            return (
                "INVENTORY_MISMATCH",
                "RED",
                "Verify asset status"
            )

        else:
            return (
                "HES_STATUS_EXCEPTION",
                "AMBER",
                "Review HES state"
            )

    # INACTIVE Cases
    if nms_status == "INACTIVE":

        if hes_status == "COMMISSIONED":
            return (
                "COMMUNICATION_LOSS",
                "RED",
                "Check RF/DCU/Power"
            )

        if hes_status == "DE-COMMISSIONED":
            return (
                "EXPECTED",
                "GREEN",
                "No action"
            )

        return (
            "REVIEW_REQUIRED",
            "AMBER",
            "Verify meter status"
        )

    # OFFLINE Cases
    if nms_status == "OFFLINE":

        if hes_status == "COMMISSIONED":
            return (
                "POWER_LINK_ISSUE",
                "CRITICAL",
                "Check DCU/RF/Power"
            )

        if hes_status == "DE-COMMISSIONED":
            return (
                "EXPECTED",
                "GREEN",
                "No action"
            )

        return (
            "INSTALLATION_ISSUE",
            "RED",
            "Verify installation"
        )

    return (
        "UNKNOWN",
        "AMBER",
        "Manual review"
    )

# --------------------------------------------------
# PROCESS
# --------------------------------------------------

if nms_file and hes_files:

    nms_df = pd.read_csv(nms_file)

    hes_list = []

    for file in hes_files:
        temp = pd.read_excel(file)

        temp["Source File"] = file.name

        hes_list.append(temp)

    hes_df = pd.concat(
        hes_list,
        ignore_index=True
    )

    # Normalize column names and handle HTML-escaped values from Excel exports
    nms_df.columns = [
        normalize_column_name(col)
        for col in nms_df.columns
    ]

    hes_df.columns = [
        normalize_column_name(col)
        for col in hes_df.columns
    ]

    # Debug (optional)
    #st.write("HES Columns:", hes_df.columns.tolist())

    # -----------------------------
    # Standardize
    # -----------------------------

    nms_name_col = find_column(nms_df, "Name", "Meter Name", "Asset ID", "Device ID")
    nms_status_col = find_column(nms_df, "Status", "NMS Status")
    nms_last_activity_col = find_column(
        nms_df,
        "Last activity",
        "Last Activity",
        "Last Active",
        "Last Activity Time"
    )

    if nms_name_col is None:
        raise ValueError("NMS file is missing a device name column.")

    if nms_status_col is not None and nms_status_col != "NMS Status":
        nms_df.rename(columns={nms_status_col: "NMS Status"}, inplace=True)

    if nms_last_activity_col is not None and nms_last_activity_col != "NMS Last Activity":
        nms_df.rename(columns={nms_last_activity_col: "NMS Last Activity"}, inplace=True)

    if nms_name_col != "Name":
        nms_df.rename(columns={nms_name_col: "Name"}, inplace=True)

    nms_df["Name"] = (
        nms_df["Name"]
        .astype(str)
        .str.strip()
    )

    hes_id_col = find_column(hes_df, "Device ID", "Meter ID", "Asset ID", "Name")
    hes_status_col = find_column(hes_df, "Status", "HES Status")
    hes_last_comm_col = find_column(
        hes_df,
        "Last Comm Date & Time",
        "Last Comm Date &amp; Time",
        "Last Comm Date &amp;amp; Time",
        "Last Comm Date",
        "Last Communication Date"
    )
    hes_power_col = find_column(hes_df, "Power Status")
    hes_relay_col = find_column(hes_df, "Relay Status")

    if hes_id_col is None:
        raise ValueError("HES file is missing a device identifier column.")

    if hes_status_col is not None and hes_status_col != "HES Status":
        hes_df.rename(columns={hes_status_col: "HES Status"}, inplace=True)

    if hes_last_comm_col is not None and hes_last_comm_col != "Last Comm Date & Time":
        hes_df.rename(columns={hes_last_comm_col: "Last Comm Date & Time"}, inplace=True)

    if hes_id_col != "Device ID":
        hes_df.rename(columns={hes_id_col: "Device ID"}, inplace=True)

    if hes_power_col is not None and hes_power_col != "Power Status":
        hes_df.rename(columns={hes_power_col: "Power Status"}, inplace=True)

    if hes_relay_col is not None and hes_relay_col != "Relay Status":
        hes_df.rename(columns={hes_relay_col: "Relay Status"}, inplace=True)

    hes_df["Device ID"] = (
        hes_df["Device ID"]
        .astype(str)
        .str.strip()
    )

    # Latest HES record retained
    hes_df = hes_df.drop_duplicates(
        subset=["Device ID"],
        keep="last"
    )

    # -----------------------------
    # Merge
    # -----------------------------

    lookup_cols = [
        "Device ID",
        "HES Status"
    ]

    if "Last Comm Date & Time" in hes_df.columns:
        lookup_cols.append("Last Comm Date & Time")

    if "Power Status" in hes_df.columns:
        lookup_cols.append("Power Status")

    if "Relay Status" in hes_df.columns:
        lookup_cols.append("Relay Status")

    lookup = hes_df[
        lookup_cols
    ].rename(
        columns={
            "Device ID": "Name",
            "HES Status": "HES Status"
        }
    )

    merged = nms_df.merge(
        lookup,
        on="Name",
        how="left"
    )

    if "NMS Status" not in merged.columns and "Status" in merged.columns:
        merged.rename(columns={"Status": "NMS Status"}, inplace=True)

    if "NMS Last Activity" not in merged.columns and "Last activity" in merged.columns:
        merged.rename(columns={"Last activity": "NMS Last Activity"}, inplace=True)

    if "NMS Last Activity" not in merged.columns:
        merged["NMS Last Activity"] = pd.NaT

    # -----------------------------
    # Dates
    # -----------------------------

    merged["NMS Last Activity"] = safe_datetime(
        merged["NMS Last Activity"]
    )

    hes_comm_col = None
    for candidate in [
        "Last Comm Date & Time",
        "Last Comm Date &amp; Time",
        "Last Comm Date &amp;amp; Time"
    ]:
        if candidate in merged.columns:
            hes_comm_col = candidate
            break

    if hes_comm_col is None:
        merged["Last Comm Date & Time"] = pd.NaT
        hes_comm_col = "Last Comm Date & Time"

    merged["Last Comm Date & Time"] = safe_datetime(
        merged[hes_comm_col]
    )

    now = pd.Timestamp.now()

    merged["Comm Age Hours"] = (
        now -
        merged["Last Comm Date & Time"]
    ).dt.total_seconds() / 3600

    merged["Activity Age Hours"] = (
        now -
        merged["NMS Last Activity"]
    ).dt.total_seconds() / 3600

    merged["Sync Gap Hours"] = (
        merged["NMS Last Activity"] -
        merged["Last Comm Date & Time"]
    ).dt.total_seconds() / 3600

    # Dormant Override
    merged["Dormant"] = (
        merged["Comm Age Hours"]
        > (DORMANT_DAYS * 24)
    )

    # -----------------------------
    # KPI ENGINE
    # -----------------------------

    kpis = merged.apply(
        evaluate_kpi,
        axis=1,
        result_type="expand"
    )

    kpis.columns = [
        "KPI Category",
        "Severity",
        "Recommended Action"
    ]

    merged = pd.concat(
        [merged, kpis],
        axis=1
    )

    merged.loc[
        merged["Dormant"],
        "KPI Category"
    ] = "DORMANT_METER"

    merged.loc[
        merged["Dormant"],
        "Severity"
    ] = "CRITICAL"

    merged.loc[
        merged["Dormant"],
        "Recommended Action"
    ] = "Immediate investigation"

    # -----------------------------
    # KPIs
    # -----------------------------

    filtered_df = merged[
        merged["NMS Status"].fillna("").str.upper().isin([x.upper() for x in STATUS_FILTER])
    ].copy()

    if SEVERITY_VIEW != "All":
        if SEVERITY_VIEW == "Critical":
            allowed_severity = ["CRITICAL", "RED"]
        elif SEVERITY_VIEW == "Amber":
            allowed_severity = ["AMBER"]
        else:
            allowed_severity = ["GREEN"]
        filtered_df = filtered_df[
            filtered_df["Severity"].isin(allowed_severity)
        ]

    total = len(filtered_df)

    healthy = int((filtered_df["KPI Category"] == "HEALTHY").sum())
    critical = int((filtered_df["Severity"] == "CRITICAL").sum())
    red = int((filtered_df["Severity"] == "RED").sum())
    amber = int((filtered_df["Severity"] == "AMBER").sum())
    green = int((filtered_df["Severity"] == "GREEN").sum())
    warning = int(filtered_df["Severity"].isin(["AMBER", "RED"]).sum())

    sla = round((healthy / total) * 100, 2) if total else 0

    severity_breakdown = (
        filtered_df["Severity"]
        .value_counts()
        .reindex(["CRITICAL", "RED", "AMBER", "GREEN"], fill_value=0)
    )

    if "selected_status_bucket" not in st.session_state:
        st.session_state.selected_status_bucket = "All"

    bucket_definitions = {
        "All": lambda df: df,
        "Healthy": lambda df: df[df["KPI Category"] == "HEALTHY"].copy(),
        "Critical": lambda df: df[df["Severity"].isin(["CRITICAL", "RED"])].copy(),
        "Amber": lambda df: df[df["Severity"] == "AMBER"].copy(),
        "Green": lambda df: df[df["Severity"] == "GREEN"].copy(),
    }

    bucket_counts = {
        "All": total,
        "Healthy": healthy,
        "Critical": critical + red,
        "Amber": amber,
        "Green": green,
    }

    st.markdown('<div class="section-header">Executive Summary</div>', unsafe_allow_html=True)
    # Contextual threshold info for Executive Summary
    st.markdown(
        f"<div class='info-box'>Thresholds in use: Communication delay = <strong>{COMM_DELAY_HRS}h</strong>; HES sync delay = <strong>{SYNC_DELAY_HRS}h</strong>; Dormant = <strong>{DORMANT_DAYS}d</strong>.\n\n"
        "These thresholds affect how meters are classified into Healthy/Amber/Critical and therefore change the Healthy percentage and alert counts.</div>",
        unsafe_allow_html=True,
    )
    # Colored executive summary cards (click the button to filter)
    color_map = {
        "All": "#e6f0ff",
        "Healthy": "#ecfdf5",
        "Critical": "#fff1f2",
        "Amber": "#fffbeb",
        "SLA": "#eef2ff",
    }

    summary_cols = st.columns(5)
    items = [("Total", "All"), ("Healthy", "Healthy"), ("Critical", "Critical"), ("Amber", "Amber"), ("Healthy percentage", "SLA")]
    for idx, (label, key) in enumerate(items):
        with summary_cols[idx]:
            bg = color_map.get(key, "#f1f5f9")
            if key == "SLA":
                value = f"{sla:.2f}%"
            else:
                value = bucket_counts.get(key, 0)

            st.markdown(
                f"""
                <div class='summary-card' style='background:{bg};'>
                    <div class='summary-label'>{label}</div>
                    <div class='summary-value'>{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(f"View {label}", key=f"bucket_{key}", use_container_width=True):
                st.session_state.selected_status_bucket = key

    # Stakeholder-friendly note explaining the Healthy percentage (highlighted)
    st.markdown(
        "<div class='healthy-note'>Healthy percentage = fraction of meters eligible for monitoring (active & commissioned with recent communications).</div>",
        unsafe_allow_html=True,
    )

    # Definitions for stakeholders and field technicians
    with st.expander("What does 'Healthy' and 'Critical' mean?"):
        st.write(
            "**Healthy:** Meter is Active in NMS, Commissioned in HES, and has recent communication within configured thresholds. Eligible for monitoring and considered operational."
        )
        st.write(
            "**Critical:** Severe issues affecting meter availability (power loss, prolonged communication failure, or Dormant override). Requires immediate field action to restore service."
        )
        st.write(
            "The Healthy percentage is the proportion of meters currently eligible for monitoring — useful for stakeholders tracking fleet health and for field technicians prioritising work." 
        )

    st.markdown('<div class="info-box">Quick read: review active commissioned meters first; focus on communication drift and HES sync gaps before escalating power or relay warnings.</div>', unsafe_allow_html=True)

    selected_bucket = st.session_state.selected_status_bucket
    display_df = bucket_definitions[selected_bucket](filtered_df)

    if selected_bucket == "All":
        st.caption(f"Showing all {len(display_df)} meters")
    else:
        st.caption(f"Showing {len(display_df)} {selected_bucket.lower()} records")

    col_left, col_right = st.columns([1.4, 1])
    with col_left:
        st.markdown('<div class="section-header">Priority heatmap</div>', unsafe_allow_html=True)
        st.bar_chart(severity_breakdown)
    with col_right:
        st.markdown('<div class="section-header">Field action focus</div>', unsafe_allow_html=True)
        action_focus = filtered_df[filtered_df["Severity"].isin(["CRITICAL", "RED", "AMBER"])].copy()
        if action_focus.empty:
            st.info("No immediate action required across the current fleet view.")
        else:
            action_focus = action_focus[["Name", "KPI Category", "Severity", "Recommended Action", "Last Comm Date & Time"]].head(8)
            for _, row in action_focus.iterrows():
                st.markdown(
                    f"<div class='field-note'><strong>{row['Name']}</strong><br><span class='kpi-badge' style='{severity_style(row['Severity'])}'>{row['Severity']}</span> · {row['KPI Category']}<br>{row['Last Comm Date & Time']}<br>{row['Recommended Action']}</div>",
                    unsafe_allow_html=True,
                )

    # -----------------------------
    # Alert Tables
    # -----------------------------

    st.markdown('<div class="section-header">Critical Alerts</div>', unsafe_allow_html=True)
    st.caption(f"Critical and red alerts: {len(filtered_df[filtered_df['Severity'].isin(['CRITICAL', 'RED'])])}")
    st.markdown(
        f"<div class='info-box'>Why a meter appears here: Dormant override (>{DORMANT_DAYS} days) sets Critical severity; power failures and long communication-loss escalate to Critical. Use these counts to prioritise field dispatch.</div>",
        unsafe_allow_html=True,
    )

    critical_df = filtered_df[filtered_df["Severity"].isin(["CRITICAL", "RED"])].copy()

    # Helper to hide HES-specific columns when requested
    HES_COLUMNS = {"HES Status", "Last Comm Date & Time", "Power Status", "Sync Gap Hours", "Relay Status"}
    def maybe_filter(cols):
        if SHOW_HES:
            return cols
        return [c for c in cols if c not in HES_COLUMNS]

    if not critical_df.empty:
        critical_display_cols = maybe_filter([
            "Name",
            "NMS Status",
            "HES Status",
            "Last Comm Date & Time",
            "Power Status",
            "Sync Gap Hours",
            "Severity",
            "KPI Category",
            "Recommended Action"
        ])
        critical_display = critical_df[critical_display_cols]
        st.dataframe(
            critical_display.style.map(
                lambda v: severity_style(v) if isinstance(v, str) and v.upper() in {"CRITICAL", "RED", "AMBER", "GREEN"} else "",
                subset=["Severity"]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No critical or red alerts are currently active.")

    st.markdown('<div class="section-header">Operational Detail Table</div>', unsafe_allow_html=True)
    st.caption(f"Operational records: {len(display_df)}")
    st.markdown(
        f"<div class='info-box'>Operational table shows current records filtered by status view. Toggle 'Show HES Columns in tables' in the sidebar to see/hide HES columns for concise views. Export contains full data regardless of this toggle.</div>",
        unsafe_allow_html=True,
    )
    operational_display_cols = maybe_filter([
        "Name",
        "NMS Status",
        "HES Status",
        "Last Comm Date & Time",
        "Power Status",
        "Sync Gap Hours",
        "Severity",
        "KPI Category",
        "Recommended Action"
    ])
    operational_df = display_df[operational_display_cols].copy()

    st.dataframe(
        operational_df.style.map(
            lambda v: severity_style(v) if isinstance(v, str) and v.upper() in {"CRITICAL", "RED", "AMBER", "GREEN"} else "",
            subset=["Severity", "KPI Category"]
        ),
        use_container_width=True,
        hide_index=True,
    )

    # -----------------------------
    # Executive Summary
    # -----------------------------

    summary = pd.DataFrame(
        {
            "Metric": [
                "Total Meters",
                "Healthy",
                "Critical",
                "Warning",
                "Healthy percentage"
            ],
            "Value": [
                total,
                healthy,
                critical,
                warning,
                sla
            ]
        }
    )

    # -----------------------------
    # Unmatched Reports
    # -----------------------------

    unmatched_nms = merged[
        merged["HES Status"]
        .isna()
    ]

    unmatched_hes = hes_df[
        ~hes_df["Device ID"]
        .isin(nms_df["Name"])
    ]

    # -----------------------------
    # Export
    # -----------------------------

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        merged.to_excel(
            writer,
            sheet_name="Merged_Data",
            index=False
        )

        summary.to_excel(
            writer,
            sheet_name="Executive_Summary",
            index=False
        )

        critical_df.to_excel(
            writer,
            sheet_name="Critical_Alerts",
            index=False
        )

        unmatched_nms.to_excel(
            writer,
            sheet_name="Unmatched_NMS",
            index=False
        )

        unmatched_hes.to_excel(
            writer,
            sheet_name="Unmatched_HES",
            index=False
        )
        # Also build an HTML version of the executive summary + tables for clearer viewing
        try:
            # Simple CSS to make the HTML report readable
            report_css = """
            <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; color:#0f172a; }
            h1 { color:#0f172a }
            .section { margin:18px 0; }
            .summary { border-collapse: collapse; width: 100%; }
            .summary th, .summary td { border: 1px solid #e5e7eb; padding: 8px; text-align: left; }
            .table { border-collapse: collapse; width: 100%; }
            .table th, .table td { border: 1px solid #e5e7eb; padding: 6px; text-align: left; }
            .healthy-note { background:#ecfdf5; padding:8px; border-left:4px solid:#10b981; margin-bottom:12px; }
            </style>
            """

            html_parts = []
            html_parts.append("<html><head><meta charset='utf-8' /><title>NMS-HES Healthy Percentage Report</title>")
            html_parts.append(report_css)
            html_parts.append("</head><body>")
            html_parts.append(f"<h1>AMI NMS ↔ HES Healthy Percentage Report</h1>")
            html_parts.append(f"<div class='healthy-note'>Thresholds: Communication {COMM_DELAY_HRS}h · HES Sync {SYNC_DELAY_HRS}h · Dormant {DORMANT_DAYS}d</div>")

            # Executive summary
            html_parts.append("<div class='section'><h2>Executive Summary</h2>")
            html_parts.append(summary.to_html(index=False, classes='summary', border=0, justify='left'))
            html_parts.append("</div>")

            # Critical alerts
            html_parts.append("<div class='section'><h2>Critical Alerts</h2>")
            if not critical_df.empty:
                html_parts.append(critical_display.to_html(index=False, classes='table', border=0, justify='left'))
            else:
                html_parts.append("<p>No critical or red alerts are currently active.</p>")
            html_parts.append("</div>")

            # Operational table (current view)
            html_parts.append("<div class='section'><h2>Operational Detail</h2>")
            html_parts.append(operational_df.to_html(index=False, classes='table', border=0, justify='left'))
            html_parts.append("</div>")

            # Unmatched reports summary
            html_parts.append("<div class='section'><h2>Unmatched Records Summary</h2>")
            html_parts.append(f"<p>Unmatched NMS: {len(unmatched_nms)} · Unmatched HES: {len(unmatched_hes)}</p>")
            html_parts.append("</div>")

            html_parts.append("</body></html>")

            html_report = "\n".join(html_parts)
        except Exception:
            html_report = "<html><body><p>Unable to generate HTML report.</p></body></html>"

        # Download buttons: Excel (existing) and HTML (new)
        st.download_button(
            "Download Healthy Percentage Report (XLSX)",
            output.getvalue(),
            file_name="NMS_HES_Healthy_Percentage_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.download_button(
            "Download Healthy Percentage Report (HTML)",
            html_report.encode("utf-8"),
            file_name="NMS_HES_Healthy_Percentage_Report.html",
            mime="text/html"
        )
    st.caption("Export note: the downloaded report includes the full merged dataset and executive summary. Thresholds used are included in the Executive_Summary sheet.")