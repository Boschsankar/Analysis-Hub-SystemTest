import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
from datetime import timedelta


from utils.common import file_upload_widget, kpi_widgets, chart_summary


# -------------------------
# Helpers
# -------------------------
def parse_battery(value):
    result = {}
    if pd.isna(value):
        return result
    for key in ["SoCBattery", "apuVtg", "apuCur", "apuTemp"]:
        match = re.search(rf"{key}:\s*([\d\.]+)", str(value))
        if match:
            result[key] = float(match.group(1))
    return result


def format_duration(td: timedelta):
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    else:
        return f"{hours}h {minutes}m {seconds}s"


def colored_metric(label, value, color):
    st.markdown(
        f"""
        <div style="background-color:{color};padding:10px;border-radius:8px;text-align:center">
            <h4 style="margin:0">{label}</h4>
            <p style="margin:0;font-size:20px;font-weight:bold">{value}</p>
        </div>
        """,
        unsafe_allow_html=True
    )


def normalize_phase_value(v):
    if pd.isna(v):
        return None
    s = str(v).strip().lower()
    if s in {"normal", "ok", "on", "1", "true", "available", "running"}:
        return "normal"
    if s in {"loss", "off", "0", "false", "not available", "na", "n/a", "-", "none"}:
        return "loss"
    try:
        num = float(s)
        return "normal" if num != 0 else "loss"
    except Exception:
        return None


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points on earth (in kilometers).
    Coordinates in decimal degrees (lat, lon).
    """
    from math import radians, sin, cos, sqrt, atan2
    R = 6371  # Earth radius in km

    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return pd.NA

    try:
        lat1_rad = radians(float(lat1))
        lon1_rad = radians(float(lon1))
        lat2_rad = radians(float(lat2))
        lon2_rad = radians(float(lon2))

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c
        return distance
    except:
        return pd.NA


#run


# -------------------------
# App start
# -------------------------
def run():
    st.header("GW Data Analysis : SoC and Lat/Long insights")

    st.title("🔋 Gateway Data Analysis Dashboard")

    uploaded_file = st.file_uploader("Upload Gateway Data Excel", type=["xlsx"])
    if uploaded_file is None:
        st.info(
            "Upload an Excel file with columns: Updated Date, Supply Src, Battery. Optional: Gateway Id and phase columns (phaseR/phaseY/phaseB).")
        st.stop()

    # -------------------------
    # Load and preprocess data
    # -------------------------
    try:
        df = pd.read_excel(uploaded_file)
    except ValueError as e:
        st.error(f"Unable to read uploaded file: {e}")
        st.stop()
    df.columns = df.columns.str.strip()

    # Gateway Id detection
    gateway_col = None
    for c in df.columns:
        if 'gateway' in c.lower().replace(" ", "") or 'Gateway Id' in c.lower():
            gateway_col = c
            break
    if gateway_col is None:
        gateway_col = df.columns[0]
    gateway_id_value = df[gateway_col].iloc[0] if gateway_col else "(missing in file)"

    # Reported Date detection
    reported_date_col = None
    for candidate in df.columns:
        if candidate.lower().replace(" ", "") in {"reporteddate", "reported_date", "reported"}:
            reported_date_col = candidate
            break
    date_display_format = "%d-%m-%y %H:%M:%S"

    if reported_date_col is None and 'Updated Date' in df.columns:
        reported_date_col = 'Updated Date'

    if reported_date_col:
        df[reported_date_col] = pd.to_datetime(df[reported_date_col], dayfirst=True, errors='coerce')
    if 'Updated Date' not in df.columns and reported_date_col:
        df['Updated Date'] = df[reported_date_col]
    else:
        df['Updated Date'] = pd.to_datetime(df['Updated Date'], dayfirst=True, errors='coerce')

    df['Updated Date Display'] = df['Updated Date'].dt.strftime(date_display_format)

    # Normalize Supply Src
    df['Supply Src'] = df['Supply Src'].astype(str).str.strip().str.lower()
    df['Supply Src'] = df['Supply Src'].replace({
        'main': 'mains', 'ac': 'mains', 'ac mains': 'mains',
        'battery ': 'battery', 'bat': 'battery', 'batt': 'battery', 'battery mode': 'battery'
    })

    # Parse Battery column
    if 'Battery' in df.columns:
        parsed = df['Battery'].apply(parse_battery)
        battery_df_expanded = pd.DataFrame(parsed.tolist())
        df = pd.concat([df, battery_df_expanded], axis=1)
    else:
        df['Battery'] = pd.NA
        for c in ["SoCBattery", "apuVtg", "apuCur", "apuTemp"]:
            if c not in df.columns:
                df[c] = pd.NA

    df = df.sort_values(by="Updated Date").reset_index(drop=True)

    # -------------------------
    # Parse combined phase text in column 'Mains Status' into separate phase columns
    # -------------------------
    phase_source_col = None
    for c in df.columns:
        if c.lower().replace(" ", "") in {"mainsstatus", "mains_status", "mainsstatuscol", "mainsstatuscolumn"}:
            phase_source_col = c
            break


    def extract_phase_values(text):
        # returns dict with keys phaseR, phaseY, phaseB when found
        res = {"phaseR": pd.NA, "phaseY": pd.NA, "phaseB": pd.NA}
        if pd.isna(text):
            return res
        s = str(text)
        # common patterns: "phaseR: loss, phaseY: loss, phaseB: normal"
        for key in ["phaseR", "phaseY", "phaseB"]:
            m = re.search(rf"{key}\s*[:=]\s*([A-Za-z0-9\-_ ]+)", s, flags=re.IGNORECASE)
            if m:
                res[key] = m.group(1).strip()
        # fallback: sometimes values are like "R:loss Y:loss B:normal"
        if all(pd.isna(v) for v in res.values()):
            m_all = re.findall(r"([RrYyBb])\s*[:=]\s*([A-Za-z0-9\-_ ]+)", s)
            for k, v in m_all:
                kmap = {"r": "phaseR", "R": "phaseR", "y": "phaseY", "Y": "phaseY", "b": "phaseB", "B": "phaseB"}
                if k in kmap:
                    res[kmap[k]] = v.strip()
        return res


    # If a combined column exists, expand it into separate columns
    if phase_source_col:
        parsed_phases = df[phase_source_col].apply(extract_phase_values)
        phases_expanded = pd.DataFrame(parsed_phases.tolist(), index=df.index)
        # Only add columns that don't already exist
        for col in ["phaseR", "phaseY", "phaseB"]:
            if col not in df.columns:
                df[col] = phases_expanded[col]

    # -------------------------
    # Detect phase columns robustly
    # -------------------------
    phase_cols = []
    for name in ['phaseR', 'phaseY', 'phaseB']:
        for col in df.columns:
            if col.lower().replace(" ", "").replace("_", "") == name.lower():
                phase_cols.append(col)

    # -------------------------
    # Detect DCU LatLong columns
    # -------------------------
    lat_long_col = None
    for c in df.columns:
        if 'dculatlong' in c.lower().replace(" ", "").replace("_", ""):
            lat_long_col = c
            break

    # Parse lat/long if found (format: JSON-like or comma/semicolon-separated)
    lat_col = None
    lon_col = None


    def parse_latlong_value(value):
        if pd.isna(value):
            return (pd.NA, pd.NA)
        s = str(value)

        # JSON-like object with latitude and longtitude/longitude keys
        lat_match = re.search(r'"latitude"\s*:\s*([+-]?\d+\.?\d*)', s, flags=re.IGNORECASE)
        lon_match = re.search(r'"longtitude"\s*:\s*([+-]?\d+\.?\d*)', s, flags=re.IGNORECASE)
        if lon_match is None:
            lon_match = re.search(r'"longitude"\s*:\s*([+-]?\d+\.?\d*)', s, flags=re.IGNORECASE)
        if lat_match is not None and lon_match is not None:
            return (float(lat_match.group(1)), float(lon_match.group(1)))

        # Generic lat,lon or lat;lon patterns
        coord_match = re.search(r'([+-]?\d+\.?\d*)[ ,;]+([+-]?\d+\.?\d*)', s)
        if coord_match is not None:
            return (float(coord_match.group(1)), float(coord_match.group(2)))

        return (pd.NA, pd.NA)


    if lat_long_col:
        coords = df[lat_long_col].apply(parse_latlong_value)
        df['Latitude'] = coords.apply(lambda x: x[0])
        df['Longitude'] = coords.apply(lambda x: x[1])
        if df['Latitude'].notna().any() and df['Longitude'].notna().any():
            lat_col = 'Latitude'
            lon_col = 'Longitude'

    # Fallback: detect separate lat/lon columns
    if lat_col is None:
        for c in df.columns:
            if 'latitude' in c.lower().replace(" ", "") or c.lower().replace(" ", "") == 'lat':
                lat_col = c
                break
        for c in df.columns:
            if 'longtitude' in c.lower().replace(" ", "") or 'longitude' in c.lower().replace(" ", "") or c.lower().replace(
                    " ", "") == 'lon':
                lon_col = c
                break

    # -------------------------
    # Detect cycles
    # -------------------------
    cycles = []
    current_cycle = None
    for i in range(len(df)):
        src = df['Supply Src'].iloc[i]
        ts = df['Updated Date'].iloc[i]
        if src == 'battery' and current_cycle is None:
            current_cycle = {'start': ts}
        elif src == 'mains' and current_cycle is not None:
            if ts > current_cycle['start']:
                current_cycle['end'] = ts
                cycles.append(current_cycle)
            current_cycle = None

    if not cycles:
        st.warning("No battery→mains cycles detected in the uploaded data.")
        st.stop()

    options = [f"Cycle {i + 1}: {c['start'].strftime(date_display_format)} → {c['end'].strftime(date_display_format)}" for
               i, c in enumerate(cycles)]
    choice = st.selectbox("Select Battery Cycle to Analyze", options)
    selected_cycle = cycles[options.index(choice)]

    # Analysis mode selector
    analysis_mode = st.radio("📊 Select Analysis Type", ["🔋 SoC Analysis", "📍 Lat/Long Accuracy Analysis"], horizontal=True)

    if analysis_mode == "📍 Lat/Long Accuracy Analysis":
        if lat_col is None or lon_col is None:
            st.warning("⚠️ No Latitude/Longitude data found in the uploaded file.")
            st.stop()

    battery_segment = df[(df['Updated Date'] >= selected_cycle['start']) & (df['Updated Date'] <= selected_cycle['end']) & (
            df['Supply Src'] == 'battery')].copy()

    if analysis_mode == "🔋 SoC Analysis":
        battery_start = battery_segment['Updated Date'].min()
        battery_end = battery_segment['Updated Date'].max()
        mains_start = df[(df['Updated Date'] > battery_end) & (df['Supply Src'] == 'mains')]['Updated Date'].min()
        mains_segment = df[(df['Updated Date'] >= mains_start) & (
                df['Supply Src'] == 'mains')] if mains_start is not pd.NaT else pd.DataFrame()
        backup_duration = battery_end - battery_start if pd.notna(battery_end) and pd.notna(battery_start) else timedelta(0)

        cycle_df = df[(df['Updated Date'] >= battery_start) & (
                df['Updated Date'] <= (mains_start if pd.notna(mains_start) else battery_end))].copy()
        cycle_df['Updated Date Display'] = cycle_df['Updated Date'].dt.strftime(date_display_format)

        # -------------------------
        # Metrics & Health Insight
        # -------------------------
        soc_start = float(battery_segment['SoCBattery'].iloc[0]) if not battery_segment.empty and pd.notna(
            battery_segment['SoCBattery'].iloc[0]) else 0.0
        soc_end = float(battery_segment['SoCBattery'].iloc[-1]) if not battery_segment.empty and pd.notna(
            battery_segment['SoCBattery'].iloc[-1]) else 0.0
        soc_drop = soc_start - soc_end
        soc_drop_rate = soc_drop / backup_duration.total_seconds() * 3600 if backup_duration.total_seconds() > 0 else 0.0
        soc_recovery = (float(mains_segment['SoCBattery'].iloc[0]) - soc_end) if (
                not mains_segment.empty and pd.notna(mains_segment['SoCBattery'].iloc[0])) else 0.0

        status_color = "#d4edda"
        status = "🟢 Healthy"
        if (cycle_df['SoCBattery'].notna() & (cycle_df['SoCBattery'] <= 6)).any():
            status = "🔴 Critical (SoC ≤ 6%)"
            status_color = "#ffcccc"
        elif (cycle_df['SoCBattery'].notna() & (cycle_df['SoCBattery'] <= 10)).any():
            status = "🟡 Warning (SoC ≤ 10%)"
            status_color = "#fff3cd"
        elif soc_drop > 80 or soc_recovery < 20:
            status = "🔴 Critical"
            status_color = "#ffcccc"
        elif soc_drop > 50 or soc_recovery < 40:
            status = "🟡 Warning"
            status_color = "#fff3cd"

        # -------------------------
        # Dashboard Header Info
        # -------------------------
        header_gateway = f"🛰️ Gateway Id ({gateway_col}): {gateway_id_value}"
        reported_date_value = df[reported_date_col].dropna().iloc[0] if reported_date_col and not df[
            reported_date_col].dropna().empty else "(missing)"
        if isinstance(reported_date_value, pd.Timestamp):
            reported_date_value = reported_date_value.strftime(date_display_format)
        header_reported = f"📅 Reported Date: {reported_date_value}"

        st.markdown(
            f"""
            <div style="background-color:#f0f0f0;padding:12px;border-radius:8px;margin-bottom:15px">
                <h3 style="margin:0">{header_gateway}</h3>
                <h4 style="margin:0">{header_reported}</h4>
            </div>
            """,
            unsafe_allow_html=True
        )

        # -------------------------
        # Key Metrics & Health Insight
        # -------------------------
        st.markdown("## Key Metrics & Cycle Details")
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            colored_metric("Backup Duration", format_duration(backup_duration), "#e6f7ff")
        with k2:
            colored_metric("SoC Drop (%)", f"{soc_drop:.2f}", "#ffe6e6" if soc_drop > 80 else "#e6f7ff")
        with k3:
            colored_metric("Drop Rate (%/hr)", f"{soc_drop_rate:.2f}", "#e6f7ff")
        with k4:
            colored_metric("Recovery (%)", f"{soc_recovery:.2f}", "#e6f7ff")

        cd1, cd2 = st.columns([3, 1])
        with cd1:
            st.write(
                f"**First Battery Time:** {battery_start.strftime(date_display_format) if pd.notna(battery_start) else '(missing)'}")
            st.write(
                f"**Last Battery Time:** {battery_end.strftime(date_display_format) if pd.notna(battery_end) else '(missing)'}")
            st.write(
                f"**First Mains Time:** {mains_start.strftime(date_display_format) if pd.notna(mains_start) else '(missing)'}")
            st.write(
                f"**SoC Recovery:** {soc_recovery:.2f}% (from {soc_end:.2f}% → {mains_segment['SoCBattery'].iloc[0] if not mains_segment.empty else 0:.2f}%)")
        with cd2:
            st.markdown("### Health Insight")
            st.markdown(
                f"""
                <div style="background-color:{status_color};padding:12px;border-radius:8px">
                    <h4 style="margin:0">{status}</h4>
                    <p>SoC end: <strong>{soc_end:.2f}%</strong></p>
                    <p>Lowest detected: <strong>{cycle_df['SoCBattery'].min():.2f}%</strong></p>
                </div>
                """,
                unsafe_allow_html=True
            )

        # -------------------------
        # SoC Timeline chart
        # -------------------------
        st.markdown("## State of Charge (SoC) Trend")
        fig_soc = px.line(cycle_df, x="Updated Date", y="SoCBattery", title="State of Charge (%)")
        fig_soc.update_layout(xaxis=dict(tickformat=date_display_format, tickangle=-45))

        # Markers for ≤10%
        low_points = cycle_df[cycle_df['SoCBattery'].notna() & (cycle_df['SoCBattery'] <= 10)]
        if not low_points.empty:
            fig_soc.add_trace(go.Scatter(
                x=low_points['Updated Date'],
                y=low_points['SoCBattery'],
                mode='markers+text',
                marker=dict(color='#ff7f7f', size=10, line=dict(color='white', width=1)),
                text=[f"{v:.1f}%" for v in low_points['SoCBattery']],
                textposition="bottom center",
                name="SoC ≤ 10%"
            ))

        # Mark ~6% line
        if cycle_df['SoCBattery'].notna().any():
            nearest_idx = (cycle_df['SoCBattery'] - 6).abs().idxmin()
            six_dt = cycle_df.loc[nearest_idx, 'Updated Date']
            six_val = cycle_df.loc[nearest_idx, 'SoCBattery']
            fig_soc.add_shape(type="line", x0=six_dt, x1=six_dt, xref="x", y0=0, y1=1, yref="paper",
                              line=dict(color="red", width=2, dash="dash"))
            fig_soc.add_annotation(x=six_dt, y=1.02, xref="x", yref="paper",
                                   text=f"SoC ≈ {six_val:.1f}%", showarrow=False,
                                   bgcolor="rgba(255,200,200,0.9)", bordercolor="red")

        st.plotly_chart(fig_soc, use_container_width=True)

        # -------------------------
        # Parameter Trends grid (create fig objects so we can export them)
        # -------------------------
        st.markdown("## Parameter Trends")
        pcol1, pcol2 = st.columns(2)

        fig_voltage = px.line(cycle_df, x="Updated Date", y="apuVtg", title="Battery Voltage (mV)")
        fig_current = px.line(cycle_df, x="Updated Date", y="apuCur", title="Battery Current (mA)")
        fig_soc_dup = px.line(cycle_df, x="Updated Date", y="SoCBattery", title="State of Charge (%)")
        fig_temp = px.line(cycle_df, x="Updated Date", y="apuTemp", title="Battery Temperature (°C)")
        for fig in (fig_voltage, fig_current, fig_soc_dup, fig_temp):
            fig.update_layout(xaxis=dict(tickformat=date_display_format, tickangle=-45))

        with pcol1:
            st.plotly_chart(fig_voltage, use_container_width=True)
            st.plotly_chart(fig_current, use_container_width=True)

        with pcol2:
            st.plotly_chart(fig_soc_dup, use_container_width=True)
            st.plotly_chart(fig_temp, use_container_width=True)

        # -------------------------
        # Supply Source vs Mains Status Verification
        # -------------------------
        st.markdown("## Supply Source vs Mains Status Verification")


        def get_verification_status(r):
            if not phase_cols:
                return (False, "no phase columns detected")
            src = str(r.get("Supply Src")).strip().lower()
            if src == "mains":
                for p in phase_cols:
                    norm = normalize_phase_value(r.get(p))
                    if norm != "normal":
                        return (False, f"{p} != normal ({r.get(p)})")
                return (True, "all normal")
            if src == "battery":
                for p in phase_cols:
                    norm = normalize_phase_value(r.get(p))
                    if norm != "loss":
                        return (False, f"{p} != loss ({r.get(p)})")
                return (True, "all loss")
            return (False, "unknown supply src")


        ver_results = cycle_df.apply(get_verification_status, axis=1)
        cycle_df[["Verification", "VerificationReason"]] = pd.DataFrame(ver_results.tolist(), index=cycle_df.index)

        # Build hover text safely
        hover_texts = []
        for _, row in cycle_df.iterrows():
            src = str(row['Supply Src']).strip().lower()
            phase_info = []
            for p in phase_cols:
                phase_info.append(f"{p}={row.get(p)}")
            hover_texts.append(f"Src={src}, " + ", ".join(phase_info))

        fig_verify = go.Figure()


        # Color logic: battery (light green if pass, red if fail), mains (dark green if pass, red if fail)
        def get_dot_color(row):
            if row["Supply Src"] == "battery":
                return "#90ee90" if row["Verification"] else "#ff4d4d"  # light green or red
            elif row["Supply Src"] == "mains":
                return "#006400" if row["Verification"] else "#ff4d4d"  # dark green or red
            else:
                return "gray"


        dot_colors = cycle_df.apply(get_dot_color, axis=1)
        status_symbols = ["circle" if v else "x" for v in cycle_df["Verification"]]
        fig_verify.add_trace(go.Scatter(
            x=cycle_df["Updated Date"],
            y=cycle_df["Verification"].astype(int),
            mode="markers",
            marker=dict(
                color=dot_colors,
                size=10,
                symbol=status_symbols,
                line=dict(color='black', width=1)
            ),
            text=hover_texts,
            hoverinfo="text",
            name="Verification"
        ))

        fig_verify.add_shape(type="line", x0=battery_start, x1=battery_start, xref="x", y0=0, y1=1, yref="paper",
                             line=dict(color="orange", width=2, dash="dot"))
        fig_verify.add_annotation(x=battery_start, y=0.5, xref="x", yref="paper",
                                  text="Battery start", showarrow=True, arrowhead=3, ax=0, ay=-40,
                                  arrowcolor="orange", bgcolor="white")

        fig_verify.update_layout(
            title="Verification of Supply Source vs Mains Status",
            yaxis=dict(title="Status", tickvals=[0, 1], ticktext=["Fail", "Pass"]),
            xaxis_title="Timestamp",
            xaxis=dict(tickformat=date_display_format, tickangle=-45)
        )

        st.plotly_chart(fig_verify, use_container_width=True)
        # --
        # -------------------------
        # Strict verification with human-readable reason
        # -------------------------

        pass_count = cycle_df["Verification"].sum()
        fail_count = len(cycle_df) - pass_count
        st.markdown(f"**Verification summary:** {pass_count} passed, {fail_count} failed")

        failed = cycle_df[cycle_df["Verification"] == False]
        if not failed.empty:
            st.markdown("### ❌ Failed verification rows and reasons")
            st.dataframe(failed[["Updated Date Display", "Supply Src"] + phase_cols + ["VerificationReason"]])
        else:
            st.markdown("### ✅ No verification failures in selected cycle")

        show_tables = st.checkbox("Show raw cycle tables", value=True)
        if show_tables:
            st.markdown("### Phase verification details")
            if phase_cols:
                for p in phase_cols:
                    cycle_df[p + "_norm"] = cycle_df[p].apply(normalize_phase_value)
                st.dataframe(cycle_df[["Updated Date Display", "Supply Src"] + [p + "_norm" for p in phase_cols] + [
                    "Verification", "VerificationReason"]].head(50))
            else:
                st.write("No phase columns found to display verification details.")

        # -------------------------
        # Final Summary Report
        # -------------------------
        st.markdown("## Final Summary Report")
        st.markdown(f"""
    - 🕒 **First Battery Time:** {battery_start}
    - 🕒 **Last Battery Time:** {battery_end}
    - ⏱️ **Backup Duration:** {format_duration(backup_duration)}
    - 🕒 **First Mains Time (Recovery):** {mains_start}
    - 🔋 **SoC Drop:** {soc_drop:.2f}% (Rate: {soc_drop_rate:.2f}%/hr)
    - ♻️ **SoC Recovery:** {soc_recovery:.2f}% (from {soc_end:.2f}% → {mains_segment['SoCBattery'].iloc[0] if not mains_segment.empty else 0:.2f}%)
    - 🩺 **Health Status:** {status}
    - 🛰️  **Gateway Id ({gateway_col}):** {gateway_id_value}
    - 📅 **Reported Date:** {reported_date_col if reported_date_col else '(not found)'}
    """)
    # -------------------------
    # Export / Download: CSVs and single self-contained HTML report
    # -------------------------
    else:
        # Lat/Long Accuracy Analysis
        st.markdown("## 📍 Latitude/Longitude Accuracy Analysis")

        # Get data for selected cycle (battery segment only for lat/long analysis)
        battery_segment = df[
            (df['Updated Date'] >= selected_cycle['start']) & (df['Updated Date'] <= selected_cycle['end']) & (
                    df['Supply Src'] == 'battery')].copy()
        battery_segment['Updated Date Display'] = battery_segment['Updated Date'].dt.strftime(date_display_format)

        if battery_segment.empty:
            st.warning("No battery segment data for the selected cycle.")
            st.stop()

        # Reference Coordinate Input
        st.markdown("### Reference Coordinates")
        col1, col2 = st.columns(2)
        with col1:
            ref_lat = st.number_input("Reference Latitude", value=0.0, format="%.6f")
        with col2:
            ref_lon = st.number_input("Reference Longitude", value=0.0, format="%.6f")

        # Check if lat/long data is available in battery segment
        if lat_col not in battery_segment.columns or lon_col not in battery_segment.columns:
            st.error("Latitude/Longitude columns not available in data.")
            st.stop()

        battery_segment[lat_col] = pd.to_numeric(battery_segment[lat_col], errors='coerce')
        battery_segment[lon_col] = pd.to_numeric(battery_segment[lon_col], errors='coerce')
        valid_points = battery_segment.dropna(subset=[lat_col, lon_col]).copy()
        valid_points = valid_points.reset_index(drop=True)
        valid_points.insert(0, 'SN', valid_points.index + 1)
        st.info(f"Detected lat/lon columns: {lat_col}, {lon_col}. Analyzed samples: {len(valid_points)}")
        if len(valid_points) == 0:
            st.warning("No valid latitude/longitude rows could be parsed. Check the uploaded DCU LatLong format.")
            st.stop()

        # Calculate haversine distance for each valid point and convert to meters
        valid_points['Distance (m)'] = valid_points.apply(
            lambda row: haversine_distance(row[lat_col], row[lon_col], ref_lat, ref_lon) * 1000,
            axis=1
        )
        valid_points['Ref Latitude'] = ref_lat
        valid_points['Ref Longitude'] = ref_lon
        valid_distances = valid_points['Distance (m)'].dropna()

        # Top report summary widgets
        if reported_date_col and not df[reported_date_col].dropna().empty:
            reported_date_value = df[reported_date_col].dropna().iloc[0]
            if isinstance(reported_date_value, pd.Timestamp):
                reported_date_value = reported_date_value.strftime(date_display_format)
        else:
            reported_date_value = '(missing)'

        report_col1, report_col2 = st.columns(2)
        with report_col1:
            st.markdown(
                f"<div style='background:#e8f5e9;padding:12px;border-radius:8px'>"
                f"<strong>Gateway Id</strong><br>{gateway_id_value}<br>"
                f"<small>Identifies the source gateway for this cycle.</small>"
                f"</div>",
                unsafe_allow_html=True
            )
        with report_col2:
            st.markdown(
                f"<div style='background:#e3f2fd;padding:12px;border-radius:8px'>"
                f"<strong>Reported Date</strong><br>{reported_date_value}<br>"
                f"<small>Date value extracted from the report metadata.</small>"
                f"</div>",
                unsafe_allow_html=True
            )

        # Display statistics
        st.markdown("### Distance Statistics")
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        with stat_col1:
            st.markdown(
                "<div style='background:#f0f7f0;padding:16px;border-radius:10px;'>"
                "<strong>Samples Analyzed</strong><br><span style='font-size:22px;'>" + str(len(valid_points)) + "</span>"
                                                                                                                 "<div style='margin-top:8px;color:#555;font-size:12px;'>Valid lat/lon rows used for accuracy metrics.</div>"
                                                                                                                 "</div>",
                unsafe_allow_html=True
            )
        with stat_col2:
            st.markdown(
                "<div style='background:#e8f5e9;padding:16px;border-radius:10px;'>"
                "<strong>Min Error (m)</strong><br><span style='font-size:22px;'>" + (
                    f"{valid_distances.min():.2f}" if len(valid_distances) > 0 else "N/A") + "</span>"
                                                                                             "<div style='margin-top:8px;color:#555;font-size:12px;'>Best match to the reference point.</div>"
                                                                                             "</div>",
                unsafe_allow_html=True
            )
        with stat_col3:
            st.markdown(
                "<div style='background:#fff8e1;padding:16px;border-radius:10px;'>"
                "<strong>Max Error (m)</strong><br><span style='font-size:22px;'>" + (
                    f"{valid_distances.max():.2f}" if len(valid_distances) > 0 else "N/A") + "</span>"
                                                                                             "<div style='margin-top:8px;color:#555;font-size:12px;'>Worst offset from the reference point.</div>"
                                                                                             "</div>",
                unsafe_allow_html=True
            )
        with stat_col4:
            st.markdown(
                "<div style='background:#fbe9e7;padding:16px;border-radius:10px;'>"
                "<strong>Std Dev (m)</strong><br><span style='font-size:22px;'>" + (
                    f"{valid_distances.std():.2f}" if len(valid_distances) > 0 else "N/A") + "</span>"
                                                                                             "<div style='margin-top:8px;color:#555;font-size:12px;'>Spread of distance errors around the mean.</div>"
                                                                                             "</div>",
                unsafe_allow_html=True
            )

        # Accuracy distribution pie chart
        st.markdown("### Accuracy Distribution")


        def accuracy_bucket(m):
            if pd.isna(m):
                return "Unknown"
            m = float(m)
            if m <= 5:
                return "≤ 5 m"
            if m <= 10:
                return "5-10 m"
            if m <= 20:
                return "10-20 m"
            return "> 20 m"


        valid_points['Accuracy Bucket'] = valid_points['Distance (m)'].apply(accuracy_bucket)
        bucket_colors = {
            '≤ 5 m': '#2ca02c',
            '5-10 m': '#90ee90',
            '10-20 m': '#ffcc00',
            '> 20 m': '#ff4d4d',
            'Unknown': 'gray'
        }
        valid_points['Bucket Color'] = valid_points['Accuracy Bucket'].map(bucket_colors)
        accuracy_ranges = ["≤ 5 m", "5-10 m", "10-20 m", "> 20 m"]
        accuracy_counts = valid_points['Accuracy Bucket'].value_counts().reindex(accuracy_ranges,
                                                                                 fill_value=0).reset_index()
        accuracy_counts.columns = ['Accuracy Range', 'Count']

        fig_pie = px.pie(
            accuracy_counts,
            names='Accuracy Range',
            values='Count',
            title='Accuracy Distribution',
            hole=0.4,
            category_orders={'Accuracy Range': accuracy_ranges},
            color='Accuracy Range',
            color_discrete_map=bucket_colors
        )
        fig_pie.update_traces(
            textposition='inside',
            textinfo='percent+label',
            marker=dict(colors=['#2ca02c', '#90ee90', '#ffcc00', '#ff4d4d']),
            hovertemplate='%{label}: %{value} samples (%{percent})<extra></extra>'
        )

        # Add descriptive insight below the pie chart
        bucket_insights = {
            '≤ 5 m': 'Expected accuracy, excellent alignment to reference.',
            '5-10 m': 'Good accuracy, within acceptable range.',
            '10-20 m': 'Moderate accuracy, review alignment and GPS source.',
            '> 20 m': 'Poor accuracy, investigate mapping or data source.'
        }
        insight_text = "\n".join([f"**{label}:** {bucket_insights[label]}" for label in accuracy_ranges])
        st.plotly_chart(fig_pie, use_container_width=True)
        st.markdown(f"<div style='background:#f8f9fa;padding:12px;border-radius:8px;margin-top:-12px;line-height:1.5;'>" \
                    f"<strong>Accuracy insights</strong><br>{insight_text}</div>", unsafe_allow_html=True)

        # Interactive category selector for detailed samples
        selected_bucket = st.selectbox("Inspect category details", accuracy_ranges, index=0)
        selected_samples = valid_points[valid_points['Accuracy Bucket'] == selected_bucket]
        st.markdown(f"### Sample details for {selected_bucket} ({len(selected_samples)} rows)")
        display_cols = ["SN", "Updated Date Display", lat_col, lon_col, "Distance (m)"]
        extra_cols = ["Supply Src"] if "Supply Src" in selected_samples.columns else []
        if "SoCBattery" in selected_samples.columns:
            extra_cols.append("SoCBattery")
        if selected_samples.empty:
            st.write("No samples in this selected accuracy bucket.")
        else:
            st.dataframe(selected_samples[display_cols + extra_cols].head(100))

        # Distance trend plots separated by category for readability
        st.markdown("### Distance Trend Over Time")
        st.markdown("Showing separate trends for latitude, longitude, and distance error.")

        lat_fig = px.line(
            valid_points,
            x="Updated Date",
            y=[lat_col, "Ref Latitude"],
            labels={lat_col: "Actual Latitude", "Ref Latitude": "Reference Latitude", "Updated Date": "Timestamp"},
            title="Latitude Trend"
        )
        lat_fig.update_traces(mode='lines+markers')
        lat_fig.update_layout(xaxis=dict(tickformat=date_display_format, tickangle=-45))

        lon_fig = px.line(
            valid_points,
            x="Updated Date",
            y=[lon_col, "Ref Longitude"],
            labels={lon_col: "Actual Longitude", "Ref Longitude": "Reference Longitude", "Updated Date": "Timestamp"},
            title="Longitude Trend"
        )
        lon_fig.update_traces(mode='lines+markers')
        lon_fig.update_layout(xaxis=dict(tickformat=date_display_format, tickangle=-45))

        error_fig = go.Figure()
        error_fig.add_trace(go.Scatter(
            x=valid_points["Updated Date"],
            y=valid_points["Distance (m)"],
            mode='lines+markers',
            name="Distance Error",
            line=dict(color='rgba(100,100,100,0.3)', width=2),
            marker=dict(
                color=valid_points['Bucket Color'],
                size=8,
                line=dict(color='white', width=1)
            ),
            hovertemplate='Time: %{x}<br>Distance Error: %{y:.2f} m<br>Bucket: %{customdata[0]}<extra></extra>',
            customdata=valid_points[['Accuracy Bucket']].values
        ))
        error_fig.update_layout(
            title="Distance Error Trend (colored by accuracy bucket)",
            xaxis=dict(tickformat=date_display_format, tickangle=-45, title="Timestamp"),
            yaxis=dict(title="Error (m)"),
            margin=dict(t=80, b=100)
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(lat_fig, use_container_width=True)
        with col_b:
            st.plotly_chart(lon_fig, use_container_width=True)

        st.plotly_chart(error_fig, use_container_width=True)

        # Color legend and insights
        st.markdown(
            "<div style='background:#f8f9fa;padding:14px;border-radius:8px;margin-top:10px;'>"
            "<strong>Color Legend & Insights:</strong><br>"
            "<span style='display:inline-block;width:16px;height:16px;background:#2ca02c;border-radius:50%;margin-right:8px;vertical-align:middle;'></span><strong>≤ 5 m (Green):</strong> Expected accuracy, excellent alignment.<br>"
            "<span style='display:inline-block;width:16px;height:16px;background:#90ee90;border-radius:50%;margin-right:8px;vertical-align:middle;'></span><strong>5-10 m (Light Green):</strong> Good accuracy, within acceptable range.<br>"
            "<span style='display:inline-block;width:16px;height:16px;background:#ffcc00;border-radius:50%;margin-right:8px;vertical-align:middle;'></span><strong>10-20 m (Yellow):</strong> Moderate accuracy, review alignment and GPS source.<br>"
            "<span style='display:inline-block;width:16px;height:16px;background:#ff4d4d;border-radius:50%;margin-right:8px;vertical-align:middle;'></span><strong>> 20 m (Red):</strong> Poor accuracy, investigate mapping or data source."
            "</div>",
            unsafe_allow_html=True
        )

        # Download lat/long analysis data
        st.markdown("### 📥 Download Lat/Long Analysis Data")
        extra_cols = ["Supply Src"] if "Supply Src" in valid_points.columns else []
        if "SoCBattery" in valid_points.columns:
            extra_cols.append("SoCBattery")
        csv_latlong = valid_points[display_cols + extra_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Lat/Long Analysis CSV",
            data=csv_latlong,
            file_name="latlong_accuracy_analysis.csv",
            mime="text/csv"
        )

    # -------------------------
    # Export / Download: CSVs and single self-contained HTML report
    # -------------------------
    if analysis_mode == "🔋 SoC Analysis":
        st.markdown("## 📥 Export Report")

        # Summary dataframe (structured)
        summary_data = {
            "First Battery Time": [battery_start],
            "Last Battery Time": [battery_end],
            "Backup Duration": [format_duration(backup_duration)],
            "First Mains Time (Recovery)": [mains_start],
            "SoC Drop (%)": [f"{soc_drop:.2f}"],
            "Drop Rate (%/hr)": [f"{soc_drop_rate:.2f}"],
            "SoC Recovery (%)": [f"{soc_recovery:.2f}"],
            "Health Status": [status],
            "Gateway Id": [gateway_id_value],
            "Reported Date": [reported_date_col if reported_date_col else '(not found)']
        }
        summary_df = pd.DataFrame(summary_data)

        # CSV bytes for summary and full cycle data
        csv_summary = summary_df.to_csv(index=False).encode("utf-8")
        csv_cycle = cycle_df.to_csv(index=False).encode("utf-8")

        # Download buttons for CSVs
        col_dl1, col_dl2, col_dl3 = st.columns([1, 1, 2])
        with col_dl1:
            st.download_button(
                label="📥 Download Summary CSV",
                data=csv_summary,
                file_name="battery_soc_summary.csv",
                mime="text/csv"
            )
        with col_dl2:
            st.download_button(
                label="📥 Download Full Cycle CSV",
                data=csv_cycle,
                file_name="battery_soc_cycle_data.csv",
                mime="text/csv"
            )

        # Build HTML report (embed figures and key text)
        # Use plotly.io.to_html to serialize each figure (include_plotlyjs='cdn' to avoid huge payload)
        import plotly.io as pio

        html_parts = []

        # Header / metadata
        html_parts.append(f"<h1>🔋 Battery SoC Analysis Dashboard</h1>")
        html_parts.append(f"<h3>🛰️ Gateway Id: {gateway_id_value}</h3>")
        html_parts.append(f"<h4>📅 Reported Date Column: {reported_date_col if reported_date_col else '(not found)'}</h4>")

        # Key metrics section
        html_parts.append("<h2>Key Metrics</h2>")
        html_parts.append("<ul>")
        html_parts.append(f"<li><strong>Backup Duration:</strong> {format_duration(backup_duration)}</li>")
        html_parts.append(f"<li><strong>SoC Drop (%):</strong> {soc_drop:.2f}</li>")
        html_parts.append(f"<li><strong>Drop Rate (%/hr):</strong> {soc_drop_rate:.2f}</li>")
        html_parts.append(f"<li><strong>SoC Recovery (%):</strong> {soc_recovery:.2f}</li>")
        html_parts.append(f"<li><strong>Health Status:</strong> {status}</li>")
        html_parts.append("</ul>")

        # SoC figure
        html_parts.append("<h2>State of Charge (SoC) Trend</h2>")
        html_parts.append(pio.to_html(fig_soc, full_html=False, include_plotlyjs='cdn'))
        # Parameter figures
        html_parts.append("<h2>Parameter Trends</h2>")
        html_parts.append("<h3>Battery Voltage (mV)</h3>")
        html_parts.append(pio.to_html(fig_voltage, full_html=False, include_plotlyjs=False))
        html_parts.append("<h3>Battery Current (mA)</h3>")
        html_parts.append(pio.to_html(fig_current, full_html=False, include_plotlyjs=False))
        html_parts.append("<h3>State of Charge (%)</h3>")
        html_parts.append(pio.to_html(fig_soc_dup, full_html=False, include_plotlyjs=False))
        html_parts.append("<h3>Battery Temperature (°C)</h3>")
        html_parts.append(pio.to_html(fig_temp, full_html=False, include_plotlyjs=False))

        # Verification figure
        html_parts.append("<h2>Supply Source vs Mains Status Verification</h2>")
        html_parts.append(pio.to_html(fig_verify, full_html=False, include_plotlyjs=False))

        # Final summary table (HTML)
        html_parts.append("<h2>Final Summary Report</h2>")
        html_parts.append(summary_df.to_html(index=False, classes='summary-table'))

        # Optional: include full cycle_df as CSV attachment text block (or link)
        html_parts.append("<h2>Full Cycle Data (CSV)</h2>")
        html_parts.append("<pre>" + cycle_df.to_csv(index=False)[:10000].replace("<", "&lt;").replace(">",
                                                                                                      "&gt;") + "\n... (truncated) </pre>")

        # Combine into a full HTML document
        html_body = "\n".join(html_parts)
        full_html = f"""<!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>Battery SoC Dashboard Report</title>
      <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
      <style>
        body{{font-family:Arial,Helvetica,sans-serif;margin:20px;color:#243447}}
        .summary-table {{border-collapse:collapse;width:100%}}
        .summary-table th, .summary-table td {{border:1px solid #e6eef3;padding:8px;text-align:left}}
      </style>
    </head>
    <body>
    {html_body}
    </body>
    </html>
    """

        # Provide HTML download button
        html_bytes = full_html.encode("utf-8")
        with col_dl3:
            st.download_button(
                label="📥 Download Full HTML Report",
                data=html_bytes,
                file_name="battery_soc_dashboard.html",
                mime="text/html"
            )

        # -------------------------
        # Verification Checklist
        # -------------------------
        st.markdown("## ✅ Verification Checklist")
        st.markdown("""
    - ✔️ Backup time verified
    - ✔️ SoC parameters trend verified
    - ✔️ Supply source vs mains status verified
    """)


if __name__ == "__main__":
    run()
