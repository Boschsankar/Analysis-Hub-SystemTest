# _pages/daily_data_analysis.py
"""Daily SLA analysis tool for smart meter data with widget layouts and inline email chart delivery."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import io
import os
import logging
import zipfile
import re
from datetime import datetime
from typing import List, Tuple, Optional

# Optional imports
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import seaborn as sns
except ImportError:
    sns = None

# Cross-platform utilities
from utils.platform_utils import EMAIL_SERVICE
from utils.error_handler import ErrorHandler, handle_errors

logger = logging.getLogger(__name__)

SUPPORTED_PROFILE_EXTENSIONS = (".xlsx", ".xls", ".csv", ".txt")
MAX_ZIP_MEMBER_BYTES = 200 * 1024 * 1024


# -----------------------
# Helpers (pure functions / IO helpers)
# -----------------------

def get_excel_files(uploads: List[io.BytesIO]) -> List[Tuple[str, bytes]]:
    """Return supported profile file payloads from direct uploads and zip archives."""
    profile_files: List[Tuple[str, bytes]] = []
    for upload in uploads or []:
        name = getattr(upload, "name", None) or ""
        try:
            if name.lower().endswith(".zip"):
                upload.seek(0)
                with zipfile.ZipFile(upload) as zf:
                    for info in zf.infolist():
                        file_name = info.filename
                        base_name = os.path.basename(file_name)
                        if not base_name or base_name.startswith(("~$", ".")):
                            continue
                        if not file_name.lower().endswith(SUPPORTED_PROFILE_EXTENSIONS):
                            continue
                        if info.file_size > MAX_ZIP_MEMBER_BYTES:
                            logger.warning("Skipping %s from %s because it is too large", file_name, name)
                            continue
                        with zf.open(info) as f:
                            profile_files.append((base_name, f.read()))
            elif name.lower().endswith(SUPPORTED_PROFILE_EXTENSIONS):
                upload.seek(0)
                profile_files.append((os.path.basename(name), upload.read()))
        except Exception as exc:
            logger.warning("Skipping uploaded file %s: %s", name, exc)
            continue
    return profile_files

def normalize_columns(columns: pd.Index) -> pd.Index:
    return (
        pd.Index(columns).map(str).str.strip()
        .str.lower()
        .str.replace(r"[^0-9a-z]+", "_", regex=True)
        .str.strip("_")
    )

def normalize_meter_ids(values: pd.Series) -> pd.Series:
    """Normalize meter IDs from Excel/CSV without changing meaningful text IDs."""
    return (
        values.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
        .str.upper()
        .replace({"NAN": "", "NONE": "", "NAT": ""})
    )

def _decode_ascii_hex(hex_value: str) -> str:
    try:
        raw = bytes.fromhex(hex_value)
        decoded = raw.decode("ascii", errors="ignore").strip()
        return decoded if decoded and all(32 <= ord(ch) < 127 for ch in decoded) else ""
    except Exception:
        return ""

def _looks_like_meter_id(value: str) -> bool:
    cleaned = str(value).strip().upper()
    if not cleaned or cleaned in {"NONE", "NAN", "NAT"}:
        return False
    if cleaned.startswith(("BIDR", "DELTA", "LOADPROFILE", "BLOCKLOAD")):
        return False
    return bool(re.fullmatch(r"[A-Z0-9_-]{4,32}", cleaned) and re.search(r"\d", cleaned))

def _parse_dlms_datetime_hex(hex_value: str) -> Optional[Tuple[datetime, bool]]:
    """Parse a 12-byte DLMS octet-string datetime."""
    if len(hex_value) < 24:
        return None
    try:
        data = bytes.fromhex(hex_value[:24])
        year = int.from_bytes(data[0:2], "big")
        month, day, hour, minute, second = data[2], data[3], data[5], data[6], data[7]
        if 0xFF in (month, day, hour, minute, second):
            return None
        return datetime(year, month, day, hour, minute, second), data[4] == 0xFF
    except Exception:
        return None

def _read_dlms_text_profile(content: bytes, file_name: str, profile_type: str) -> pd.DataFrame:
    """Extract meter_id and timestamps from DLMS/XML-like text profile dumps."""
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        return pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

    serial_match = re.search(r"Serial\s+number\s*:\s*([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    serial_meter_id = serial_match.group(1).strip() if serial_match else ""
    octet_values = re.findall(r"<OctetString\s+Value\s*=\s*['\"]([0-9A-Fa-f]+)['\"]", text, flags=re.IGNORECASE)
    datetime_values = re.findall(r"<DateTime\s+Value\s*=\s*['\"]([0-9A-Fa-f]+)['\"]", text, flags=re.IGNORECASE)

    decoded_ids = []
    row_timestamps = []
    all_timestamps = []
    for value in octet_values + datetime_values:
        decoded = _decode_ascii_hex(value)
        if decoded and _looks_like_meter_id(decoded):
            decoded_ids.append(decoded)

        parsed_ts = _parse_dlms_datetime_hex(value)
        if parsed_ts is not None:
            timestamp, is_row_timestamp = parsed_ts
            all_timestamps.append(timestamp)
            if is_row_timestamp:
                row_timestamps.append(timestamp)

    stem = os.path.splitext(os.path.basename(file_name))[0]
    stem_candidates = [token.strip() for token in re.split(r"[_\s-]+", stem) if token.strip()]
    text_candidates = re.findall(r"\b[A-Za-z]{1,8}\d{4,16}\b", text)
    plain_id_candidates = [candidate for candidate in text_candidates if _looks_like_meter_id(candidate)]
    
    stem_meter_id = ""
    for candidate in stem_candidates:
        if candidate.lower() not in {"deltaloadprofile", "loadprofile", "blockload", "block", "single", "three", "phase"} and _looks_like_meter_id(candidate):
            stem_meter_id = candidate
            break

    meter_id = stem_meter_id or (plain_id_candidates[0] if plain_id_candidates else "") or (decoded_ids[0] if decoded_ids else serial_meter_id)
    if not meter_id:
        meter_id = stem.split("_")[0] if stem else "UNKNOWN"

    timestamps = row_timestamps or all_timestamps
    if not timestamps:
        return pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

    return pd.DataFrame(
        {
            "meter_id": normalize_meter_ids(pd.Series([meter_id] * len(timestamps))),
            "timestamp": pd.to_datetime(timestamps),
            "profile_type": profile_type,
        }
    )

def _find_timestamp_columns(columns: pd.Index) -> List[str]:
    timestamp_aliases = [
        "meter_date_and_time", "meter_date_time", "meter_date__time", "meter_datetime",
        "meter_timestamp", "rtc_date_and_time", "rtc_date_time", "rtc_datetime",
        "hes_received_time", "hes_received_timestamp", "date_time", "datetime",
        "timestamp", "profile_time", "profile_timestamp",
    ]
    for col in timestamp_aliases:
        if col in columns: return [col]
    for col in columns:
        if any(token in col for token in ("datetime", "timestamp")) or ("date" in col and "time" in col):
            return [col]
    date_cols = [col for col in columns if "date" in col]
    time_cols = [col for col in columns if "time" in col]
    if date_cols and time_cols:
        return [date_cols[0], time_cols[0]]
    for col in columns:
        if "date" in col or "time" in col: return [col]
    return []

def _required_original_columns(original_columns: pd.Index) -> Optional[List[str]]:
    normalized = normalize_columns(original_columns)
    normalized_to_original = dict(zip(normalized, original_columns))
    meter_col = _find_meter_column(normalized)
    timestamp_cols = _find_timestamp_columns(normalized)
    if meter_col is None or not timestamp_cols:
        return None
    required = [normalized_to_original[meter_col]]
    required.extend(normalized_to_original[col] for col in timestamp_cols if col in normalized_to_original)
    return list(dict.fromkeys(required))

def _read_profile_file(content: bytes, file_name: str) -> pd.DataFrame:
    suffix = os.path.splitext(file_name.lower())[1]
    readers = ("excel", "csv") if suffix in (".xlsx", ".xls") else ("csv", "excel")

    last_error = None
    for reader in readers:
        try:
            buffer = io.BytesIO(content)
            if reader == "csv":
                header = pd.read_csv(buffer, sep=None, engine="python", dtype=str, nrows=0)
                required_cols = _required_original_columns(header.columns)
                buffer.seek(0)
                return pd.read_csv(buffer, sep=None, engine="python", dtype=str, usecols=required_cols)

            header = pd.read_excel(buffer, dtype=str, nrows=0)
            required_cols = _required_original_columns(header.columns)
            buffer.seek(0)
            return pd.read_excel(buffer, dtype=str, usecols=required_cols)
        except Exception as e:
            last_error = e
    raise last_error or ValueError("Unable to read file")

def _find_meter_column(columns: pd.Index) -> Optional[str]:
    aliases = {
        "device_id", "deviceid", "device_serial_number", "meterid", "meter_id",
        "meter_no", "meter_number", "meter_serial_no", "meter_serial_number",
        "meter_sr_no", "meter", "msn", "mtr_id", "serial_no", "serial_number",
    }
    for col in columns:
        if col in aliases: return col
    for col in columns:
        if "meter" in col and any(token in col for token in ("id", "no", "number", "serial", "sr")):
            return col
    return None

def _find_timestamp_series(df: pd.DataFrame) -> Optional[pd.Series]:
    timestamp_aliases = [
        "meter_date_and_time", "meter_date_time", "meter_date__time", "meter_datetime",
        "meter_timestamp", "rtc_date_and_time", "rtc_date_time", "rtc_datetime",
        "hes_received_time", "hes_received_timestamp", "date_time", "datetime",
        "timestamp", "profile_time", "profile_timestamp",
    ]
    for col in timestamp_aliases:
        if col in df.columns: return df[col]
    for col in df.columns:
        if any(token in col for token in ("datetime", "timestamp")) or ("date" in col and "time" in col):
            return df[col]
    
    date_cols = [col for col in df.columns if "date" in col]
    time_cols = [col for col in df.columns if "time" in col]
    if date_cols and time_cols:
        return df[date_cols[0]].astype(str).str.strip() + " " + df[time_cols[0]].astype(str).str.strip()
    for col in df.columns:
        if "date" in col or "time" in col: return df[col]
    return None

@st.cache_data(show_spinner=False)
def _read_profile_cached(file_payloads: Tuple[Tuple[str, bytes], ...], profile_type: str) -> Tuple[pd.DataFrame, str]:
    return _read_profile_uncached(list(file_payloads), profile_type)

def read_profile(files: List[Tuple[str, bytes]], profile_type: str) -> pd.DataFrame:
    df_out, invalid_msg = _read_profile_cached(tuple(files or []), profile_type)
    if invalid_msg:
        df_out._invalid_files = invalid_msg  # type: ignore[attr-defined]
    return df_out.copy()

def _read_profile_uncached(files: List[Tuple[str, bytes]], profile_type: str) -> Tuple[pd.DataFrame, str]:
    dfs = []
    invalid_files = []

    for file_name, content in files or []:
        try:
            if not content:
                invalid_files.append((file_name, "Empty file"))
                continue
            df = _read_profile_file(content, file_name)

            df.columns = normalize_columns(df.columns)
            meter_col = _find_meter_column(df.columns)
            timestamp_values = _find_timestamp_series(df)

            missing = []
            if meter_col is None: missing.append("meter id column")
            if timestamp_values is None: missing.append("timestamp/date-time column")
            if missing:
                dlms_df = _read_dlms_text_profile(content, file_name, profile_type)
                if not dlms_df.empty:
                    dfs.append(dlms_df[["meter_id", "timestamp", "profile_type"]])
                    continue
                invalid_files.append((file_name, f"Missing {', '.join(missing)}. Columns found: {list(df.columns)}"))
                continue

            df = df.rename(columns={meter_col: "meter_id"})
            df["meter_id"] = normalize_meter_ids(df["meter_id"])
            df = df[df["meter_id"] != ""].copy()
            df["timestamp"] = pd.to_datetime(timestamp_values, errors="coerce", dayfirst=True)
            df = df.dropna(subset=["timestamp"])
            if df.empty:
                dlms_df = _read_dlms_text_profile(content, file_name, profile_type)
                if not dlms_df.empty:
                    dfs.append(dlms_df[["meter_id", "timestamp", "profile_type"]])
                    continue
                invalid_files.append((file_name, "No parseable meter IDs or timestamps found"))
                continue
            df["profile_type"] = profile_type
            dfs.append(df[["meter_id", "timestamp", "profile_type"]])
        except Exception as e:
            dlms_df = _read_dlms_text_profile(content, file_name, profile_type)
            if not dlms_df.empty:
                dfs.append(dlms_df[["meter_id", "timestamp", "profile_type"]])
                continue
            invalid_files.append((file_name, str(e)))
            continue

    df_out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
    return df_out, "\n".join([f"- {n}: {m}" for n, m in invalid_files]) if invalid_files else ""

@st.cache_data(show_spinner=False)
def _read_meter_list_cached(file_name: str, content: bytes) -> pd.DataFrame:
    suffix = os.path.splitext(file_name.lower())[1]
    if suffix in (".csv", ".txt"):
        return pd.read_csv(io.BytesIO(content), sep=None, engine="python", dtype=str)
    return pd.read_excel(io.BytesIO(content), dtype=str)

def get_excel_writer(buffer: io.BytesIO):
    try:
        return pd.ExcelWriter(buffer, engine="xlsxwriter")
    except Exception:
        return pd.ExcelWriter(buffer, engine="openpyxl")

def _save_png_from_plt(fig, path: str):
    try:
        fig.savefig(path, bbox_inches="tight")
    except Exception:
        pass

def _clean_label(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", " ", str(value)).strip().upper()
    return re.sub(r"\s+", " ", value)

def _safe_filename_part(value: str) -> str:
    value = _clean_label(value).replace(" ", "_")
    return value or "SMART_METER"

def _infer_report_context(meter_list: pd.DataFrame, meter_list_name: str) -> Tuple[str, str, str]:
    """Build location-aware report title, subject prefix, and file prefix."""
    source_text = _clean_label(os.path.splitext(os.path.basename(meter_list_name))[0])
    context_cols = [
        "location", "location_name", "site", "site_name", "project", "project_name",
        "area", "region", "circle", "division", "town", "city", "utility", "cluster",
    ]
    for col in context_cols:
        if col in meter_list.columns:
            values = [_clean_label(v) for v in meter_list[col].dropna().astype(str).unique()[:3]]
            source_text = " ".join([source_text] + [v for v in values if v])

    tokens = set(source_text.split())
    primary = "KOR" if "KOR" in tokens else ""
    secondary = "ADU" if "ADU" in tokens else ""

    if primary and secondary:
        title = f"{primary} SLA Performance for {secondary}"
        subject_prefix = f"{primary} {secondary}"
        file_prefix = f"{primary}_{secondary}"
    elif primary or secondary:
        scope = primary or secondary
        title = f"{scope} SLA Performance"
        subject_prefix = scope
        file_prefix = scope
    else:
        generic_tokens = {
            "ACTUAL", "METER", "METERS", "LIST", "MASTER", "FILE", "DATA", "DAILY",
            "SMART", "REPORT", "FULL", "EXPORT", "PROFILE", "PROFILES", "SLA",
            "PERFORMANCE", "DASHBOARD", "DASH", "BOARD", "CSV", "XLSX", "XLS",
        }
        meaningful_tokens = [token for token in source_text.split() if token not in generic_tokens]
        if not meaningful_tokens and "OEM" in meter_list.columns:
            meaningful_tokens = [
                _clean_label(value)
                for value in meter_list["OEM"].dropna().astype(str).unique()[:4]
                if _clean_label(value) and _clean_label(value) != "UNKNOWN"
            ]
        scope = " ".join(meaningful_tokens[:5]).strip()
        if scope:
            title = f"{scope} SLA Performance"
            subject_prefix = scope
            file_prefix = scope.replace(" ", "_")
        else:
            title = "Smart Meter Daily SLA Performance"
            subject_prefix = "Smart Meter"
            file_prefix = "Smart_Meter"

    return title, subject_prefix, file_prefix

def _format_percent(value: float) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"

def _coerce_expected_count(value):
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return int(value) if not np.isnan(value) else None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "na", "null"}:
            return None
        match = re.search(r"-?\d+", text)
        if match:
            return int(match.group(0))
    return None


def _resolve_expected_samples(row):
    profile_type = str(row.get("profile_type", "") or "").strip()
    profile_type_key = profile_type.lower()

    profile_candidates = {
        "block": [
            "block_expected_samples", "block_expected", "expected_samples_block", "expected_block",
            "block_profile_expected", "expected_count_block", "expected_records_block",
        ],
        "instant": [
            "instant_expected_samples", "instant_expected", "expected_samples_instant", "expected_instant",
            "instant_profile_expected", "expected_count_instant", "expected_records_instant",
        ],
        "daily": [
            "daily_expected_samples", "daily_expected", "expected_samples_daily", "expected_daily",
            "daily_profile_expected", "expected_count_daily", "expected_records_daily",
        ],
        "billing": [
            "billing_expected_samples", "billing_expected", "expected_samples_billing", "expected_billing",
            "billing_profile_expected", "expected_count_billing", "expected_records_billing",
        ],
    }
    generic_candidates = [
        "expected_samples", "expected_sample_count", "expected_count", "expected_records",
        "profile_expected_samples", "sla_expected_samples", "sla_expected_count", "expected_profile_count",
    ]

    candidate_keys = profile_candidates.get(profile_type_key, []) + generic_candidates
    for candidate in candidate_keys:
        if candidate in row:
            value = _coerce_expected_count(row[candidate])
            if value is not None:
                return value

    for key, value in row.items():
        if key is None:
            continue
        normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
        if "expected" not in normalized_key and "sla" not in normalized_key:
            continue
        if profile_type_key and profile_type_key not in normalized_key:
            if any(token in normalized_key for token in ("block", "instant", "daily", "billing")):
                continue
        parsed_value = _coerce_expected_count(value)
        if parsed_value is not None:
            return parsed_value

    if profile_type == "Instant":
        return 48
    if profile_type in ("Daily", "Billing"):
        return 1
    if profile_type == "Block":
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


def _build_insights(
    report_title: str,
    total_meters: int,
    reporting_meters: int,
    non_reporting: int,
    oem_kpi: pd.DataFrame,
    profile_kpi: pd.DataFrame,
    phase_chart_data: pd.DataFrame,
) -> List[str]:
    reporting_pct = (reporting_meters / total_meters * 100) if total_meters else 0
    insights = [
        f"{report_title}: {reporting_meters} of {total_meters} baseline meters reported at least one profile ({reporting_pct:.1f}%).",
    ]
    if non_reporting:
        insights.append(f"{non_reporting} meter(s) are non-reporting and need field or HES follow-up.")
    else:
        insights.append("All baseline meters reported at least one profile.")

    if not profile_kpi.empty:
        weakest = profile_kpi.sort_values("avg_achieved").iloc[0]
        insights.append(
            f"Weakest profile by average SLA achievement: {weakest['profile_type']} at {float(weakest['avg_achieved']):.1f}%."
        )
    if not oem_kpi.empty:
        lowest_oem = oem_kpi.sort_values("Reporting %").iloc[0]
        insights.append(
            f"Lowest OEM communication rate: {lowest_oem['OEM']} at {float(lowest_oem['Reporting %']):.1f}%."
        )
    phase_rows = phase_chart_data[phase_chart_data["Profile"].astype(str) != "Total Meters"].copy()
    if not phase_rows.empty:
        phase_rows["Percent"] = pd.to_numeric(phase_rows["Percent"], errors="coerce").fillna(0)
        weakest_phase = phase_rows.sort_values("Percent").iloc[0]
        insights.append(
            f"Lowest OEM-wise profile segment: {weakest_phase['OEM_Phase_Drill']} - {weakest_phase['Profile']} at {weakest_phase['Percent']:.1f}% full achievement."
        )
    return insights

def send_email_report(
    to_email: str,
    subject: str,
    full_report_bytes: bytes,
    html_report_str: str,
    full_report_name: str = "SmartMeter_Daily_SLA_Report.xlsx",
    attachments_dict: Optional[dict] = None,
    use_outlook: bool = False,
) -> Tuple[bool, str]:
    attachments = []
    if full_report_bytes:
        attachments.append((full_report_name, full_report_bytes))
    if attachments_dict:
        for name, data in attachments_dict.items():
            attachments.append((name, data))
                    
    success, msg = EMAIL_SERVICE.send_email(
        to_email=to_email,
        subject=subject,
        html_body=html_report_str,
        attachments=attachments,
        use_outlook=use_outlook,
    )
    return success, msg


# -----------------------
# Main UI Run Loop
# -----------------------

def run():
    st.header("Daily SLA Analysis")
    st.markdown("Upload profile trace segments and master data references to audit reporting efficiency scores.")

    col1, col2 = st.columns(2)
    with col1:
        block_uploads = st.file_uploader("Upload Block Profiles", type=["xlsx", "xls", "csv", "txt", "zip"], accept_multiple_files=True)
        instant_uploads = st.file_uploader("Upload Instant Profiles", type=["xlsx", "xls", "csv", "txt", "zip"], accept_multiple_files=True)
    with col2:
        daily_uploads = st.file_uploader("Upload Daily Profiles", type=["xlsx", "xls", "csv", "txt", "zip"], accept_multiple_files=True)
        billing_uploads = st.file_uploader("Upload Billing Profiles", type=["xlsx", "xls", "csv", "txt", "zip"], accept_multiple_files=True)
        meter_list_file = st.file_uploader("Upload Actual Meter List (.xlsx)", type=["xlsx"])

    if not any([block_uploads, instant_uploads, daily_uploads, billing_uploads, meter_list_file]):
        st.info("Provide parameter logs and configuration registers to compute analytics.")
        return

    with st.spinner("Processing references..."):
        block_files = get_excel_files(block_uploads) if block_uploads else []
        instant_files = get_excel_files(instant_uploads) if instant_uploads else []
        daily_files = get_excel_files(daily_uploads) if daily_uploads else []
        billing_files = get_excel_files(billing_uploads) if billing_uploads else []

    meter_list = None
    if meter_list_file:
        try:
            meter_list_file.seek(0)
            meter_list_name = getattr(meter_list_file, "name", "meter_list.xlsx")
            meter_list = _read_meter_list_cached(meter_list_name, meter_list_file.read()).copy()
        except Exception as e:
            st.error(f"Failed to resolve configuration reference sheet: {e}")
            return

    if meter_list is None:
        st.error("Actual reference meter checklist configuration file missing.")
        return
    else:
        meter_list.columns = normalize_columns(meter_list.columns)
        
        # Normalize OEM Attributes
        if "oem" in meter_list.columns: meter_list.rename(columns={"oem": "OEM"}, inplace=True)
        elif "manufacturer" in meter_list.columns: meter_list.rename(columns={"manufacturer": "OEM"}, inplace=True)
        elif "make" in meter_list.columns: meter_list.rename(columns={"make": "OEM"}, inplace=True)
        else: meter_list["OEM"] = "Unknown"
        meter_list["OEM"] = meter_list["OEM"].astype(str).str.strip().str.upper()

        # Phase Detection
        phase_col_found = next((c for c in ["phase", "meter_phase", "type", "meter_type", "category", "config"] if c in meter_list.columns), None)
        if phase_col_found:
            def _parse_phase_value(val: str) -> str:
                clean_val = str(val).upper().strip()
                if "3P" in clean_val or "3-PHASE" in clean_val or "THREE" in clean_val or "3" in clean_val:
                    return "3P"
                return "1P"
            meter_list["Raw_Phase"] = meter_list[phase_col_found].apply(_parse_phase_value)
        else:
            meter_list["Raw_Phase"] = "1P"

        meter_list["OEM_Phase_Drill"] = meter_list["OEM"].astype(str).str.strip().str.upper()
        preferred_drills = ["AEW", "HPL"]
        other_drills = sorted([v for v in meter_list["OEM_Phase_Drill"].dropna().unique() if v not in preferred_drills])
        unique_drills_sorted = [v for v in preferred_drills if v in set(meter_list["OEM_Phase_Drill"])] + other_drills
        meter_list["OEM_Phase_Drill"] = pd.Categorical(
            meter_list["OEM_Phase_Drill"], 
            categories=unique_drills_sorted, 
            ordered=True
        )

        capture_col_found = next((c for c in ["profile_capture_period", "capture_period", "period", "interval", "block_period"] if c in meter_list.columns), None)
        if capture_col_found: meter_list.rename(columns={capture_col_found: "capture_period"}, inplace=True)
        else:
            st.error("No valid integration window definitions discovered.")
            return

        meter_col = _find_meter_column(meter_list.columns)
        if meter_col and meter_col != "meter_id": meter_list.rename(columns={meter_col: "meter_id"}, inplace=True)
        meter_list["meter_id"] = normalize_meter_ids(meter_list["meter_id"])
        meter_list = meter_list[meter_list["meter_id"] != ""].copy()

    report_title, subject_prefix, file_prefix = _infer_report_context(meter_list, meter_list_name)
    report_date_token = datetime.now().strftime("%d-%b-%Y")

    with st.spinner("Extracting profile matrices..."):
        block_df = read_profile(block_files, "Block") if block_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        instant_df = read_profile(instant_files, "Instant") if instant_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        daily_df = read_profile(daily_files, "Daily") if daily_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
        billing_df = read_profile(billing_files, "Billing") if billing_files else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])

    profiles = pd.concat([block_df, instant_df, daily_df, billing_df], ignore_index=True) if not (block_df.empty and instant_df.empty and daily_df.empty and billing_df.empty) else pd.DataFrame(columns=["meter_id", "timestamp", "profile_type"])
    if profiles.empty:
        st.error("No parseable profiles discovered.")
        return

    profiles["timestamp"] = pd.to_datetime(profiles["timestamp"], errors="coerce", dayfirst=True)
    profiles = profiles.dropna(subset=["timestamp"])
    profiles["meter_id"] = normalize_meter_ids(profiles["meter_id"])
    profiles = profiles[profiles["meter_id"] != ""].copy()

    reporting_date = profiles["timestamp"].max().strftime("%d-%b-%Y")
    st.markdown(f"### {report_title}")
    st.markdown(f"### 📅 Reporting Date: **{reporting_date}**")

    total_meters = meter_list["meter_id"].nunique()
    matched_ids = set(profiles["meter_id"]).intersection(set(meter_list["meter_id"]))
    reporting_meters = len(matched_ids)
    non_reporting = total_meters - reporting_meters

    st.html(
        f"""
        <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 200px; padding: 1rem; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; border-left: 5px solid #0d6efd; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="font-size: 0.85rem; color: #6c757d; font-weight: bold; text-transform: uppercase; font-family: sans-serif;">Total Baseline Meters</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: #212529; margin-top: 0.25rem; font-family: sans-serif;">{total_meters}</div>
            </div>
            <div style="flex: 1; min-width: 200px; padding: 1rem; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; border-left: 5px solid #198754; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="font-size: 0.85rem; color: #6c757d; font-weight: bold; text-transform: uppercase; font-family: sans-serif;">Reporting Unique Count</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: #212529; margin-top: 0.25rem; font-family: sans-serif;">{reporting_meters}</div>
            </div>
            <div style="flex: 1; min-width: 200px; padding: 1rem; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; border-left: 5px solid #dc3545; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="font-size: 0.85rem; color: #6c757d; font-weight: bold; text-transform: uppercase; font-family: sans-serif;">Non-Reporting Faults</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: #212529; margin-top: 0.25rem; font-family: sans-serif;">{non_reporting}</div>
            </div>
        </div>
        """
    )

    meter_summary_raw = profiles.groupby(["meter_id", "profile_type"]).agg(actual_samples=("timestamp", "count")).reset_index()
    required_profiles = ["Block", "Instant", "Daily", "Billing"]
    
    full_matrix = (
        meter_list[["meter_id", "OEM", "capture_period", "Raw_Phase", "OEM_Phase_Drill"]]
        .assign(key=1).merge(pd.DataFrame({"profile_type": required_profiles, "key": 1}), on="key").drop("key", axis=1)
    )

    meter_summary = full_matrix.merge(meter_summary_raw, on=["meter_id", "profile_type"], how="left")
    meter_summary["actual_samples"] = meter_summary["actual_samples"].fillna(0)

    reference_columns = [c for c in meter_list.columns if re.search(r"(expected|sla)", str(c), flags=re.IGNORECASE)]
    if reference_columns:
        meter_summary = meter_summary.merge(
            meter_list[["meter_id", *reference_columns]].drop_duplicates("meter_id"),
            on="meter_id",
            how="left",
        )

    meter_summary["expected_samples"] = meter_summary.apply(_resolve_expected_samples, axis=1)
    meter_summary["achieved_percent"] = np.where(
        (meter_summary["actual_samples"] > 0) & (meter_summary["expected_samples"].notna()),
        (meter_summary["actual_samples"] / meter_summary["expected_samples"]) * 100,
        0
    )

    meter_level = meter_summary.groupby("meter_id").agg(
        total_actual=("actual_samples", "sum"),
        total_expected=("expected_samples", "sum"),
        profiles_reporting=("actual_samples", lambda x: (x > 0).sum())
    ).reset_index()
    meter_level["overall_percent"] = np.where(meter_level["total_expected"] > 0, (meter_level["total_actual"] / meter_level["total_expected"]) * 100, 0)

    profile_kpi = meter_summary.groupby("profile_type").agg(
        total_meters=("meter_id", "nunique"),
        reporting=("actual_samples", lambda x: (x > 0).sum()),
        non_reporting=("actual_samples", lambda x: (x == 0).sum()),
        avg_achieved=("achieved_percent", "mean"),
        full_achieved=("achieved_percent", lambda x: (x >= 100).sum()),
    ).reset_index()
    profile_kpi["Full Achievement %"] = np.where(
        profile_kpi["total_meters"] > 0,
        (profile_kpi["full_achieved"] / profile_kpi["total_meters"] * 100).round(1),
        0,
    )

    # Communication Status Table
    st.subheader("🏭 Communication status - OEM wise")
    oem_kpi = meter_list.merge(
        meter_level[["meter_id", "profiles_reporting"]], on="meter_id", how="left"
    ).groupby("OEM").agg(
        total_meters=("meter_id", "nunique"),
        reporting=("profiles_reporting", lambda x: (x > 0).sum()),
        non_reporting=("profiles_reporting", lambda x: (x == 0).sum())
    ).reset_index()
    oem_kpi["Reporting %"] = (oem_kpi["reporting"] / oem_kpi["total_meters"]) * 100
    oem_kpi["Non-Reporting %"] = (oem_kpi["non_reporting"] / oem_kpi["total_meters"]) * 100
    st.dataframe(oem_kpi, use_container_width=True)

    st.subheader("Profile-wise SLA Summary")
    st.dataframe(profile_kpi, use_container_width=True)

    # SLA Performance Graph Title
    st.subheader("📊 SLA Profile Performance Visual breakdown")
    
    phase_profile_kpi = meter_summary.groupby(["OEM_Phase_Drill", "profile_type"], observed=False).agg(
        full_achieved=("achieved_percent", lambda x: (x >= 100).sum())
    ).reset_index()

    phase_total_counts = meter_list.groupby("OEM_Phase_Drill", observed=False)["meter_id"].nunique().reset_index(name="total_meters")
    total_phase_bars = phase_total_counts.rename(columns={"total_meters": "Meters"}).assign(Profile="Total Meters")
    phase_bars = phase_profile_kpi.rename(columns={"profile_type": "Profile", "full_achieved": "Meters"})

    phase_chart_data = pd.concat([total_phase_bars[["OEM_Phase_Drill", "Profile", "Meters"]], phase_bars[["OEM_Phase_Drill", "Profile", "Meters"]]], ignore_index=True)
    phase_chart_data = phase_chart_data.merge(phase_total_counts, on="OEM_Phase_Drill", how="left")
    phase_chart_data["Percent"] = np.where(phase_chart_data["Profile"] == "Total Meters", np.nan, (phase_chart_data["Meters"] / phase_chart_data["total_meters"] * 100).round(1))
    
    profile_order = ["Total Meters", "Daily", "Block", "Instant", "Billing"]
    phase_chart_data["Profile"] = pd.Categorical(phase_chart_data["Profile"], categories=profile_order, ordered=True)
    phase_chart_data = phase_chart_data.sort_values(by=["OEM_Phase_Drill", "Profile"])

    dashboard_insights = _build_insights(report_title, total_meters, reporting_meters, non_reporting, oem_kpi, profile_kpi, phase_chart_data)
    with st.expander("Stakeholder insights", expanded=True):
        for insight in dashboard_insights:
            st.write(f"- {insight}")

    if plt is not None and sns is not None:
        fig2, ax2 = plt.subplots(figsize=(8.0, 4.2), dpi=130)
        sns.barplot(data=phase_chart_data, x="OEM_Phase_Drill", y="Meters", hue="Profile", hue_order=profile_order, palette="Accent", ax=ax2)
        ax2.set_title(f"{report_title} - OEM-wise SLA Profile Performance", fontsize=9, fontweight="bold")
        
        ax2.set_xlabel("OEM wise", fontsize=7.5)
        ax2.set_ylabel("Meters Volume Count", fontsize=7.5)
        ax2.tick_params(labelsize=7)
        
        phase_labels = [tick.get_text() for tick in ax2.get_xticklabels()]
        for profile_name, container in zip(profile_order, ax2.containers):
            if profile_name == "Total Meters":
                labels = [f"{int(bar.get_height())}" if bar.get_height() > 0 else "" for bar in container]
                ax2.bar_label(container, labels=labels, fontsize=6.5, padding=1)
                continue
            for idx, bar in enumerate(container):
                height = bar.get_height()
                if height <= 0 or idx >= len(phase_labels): continue
                row = phase_chart_data[(phase_chart_data["OEM_Phase_Drill"].astype(str) == str(phase_labels[idx])) & (phase_chart_data["Profile"].astype(str) == profile_name)]
                if row.empty: continue
                ax2.text(bar.get_x() + bar.get_width() / 2, height + (max(phase_chart_data["Meters"])*0.01), f"{int(height)}\n({row['Percent'].iloc[0]:.0f}%)", ha="center", va="bottom", fontsize=6, color="black")
        
        ax2.legend(title="Profiles Type", ncols=5, fontsize=6.5, title_fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, -0.18))
        plt.tight_layout()
        st.pyplot(fig2)
        _save_png_from_plt(fig2, "phase_profile_chart.png")
        plt.close(fig2)

    # Combined Table view
    st.subheader("📋 Meter-wise Performance (Combined)")
    pivot = meter_summary.pivot_table(index="meter_id", columns="profile_type", values=["actual_samples", "expected_samples", "achieved_percent"], aggfunc="first")
    if not pivot.empty: pivot.columns = [f"{metric}_{profile}" for metric, profile in pivot.columns]
    meter_combined = meter_list.merge(meter_level, on="meter_id", how="left").merge(pivot, on="meter_id", how="left")
    
    display_cols = [
        "meter_id", "OEM", "Raw_Phase", "OEM_Phase_Drill", "capture_period",
        "actual_samples_Block", "achieved_percent_Block", "actual_samples_Instant", "achieved_percent_Instant",
        "actual_samples_Daily", "achieved_percent_Daily", "actual_samples_Billing", "achieved_percent_Billing",
        "total_actual", "overall_percent", "profiles_reporting"
    ]
    meter_combined_display = meter_combined[[c for c in display_cols if c in meter_combined.columns]].sort_values("overall_percent") if not meter_combined.empty else pd.DataFrame()
    if not meter_combined_display.empty:
        meter_combined_display = meter_combined_display.rename(columns={"OEM_Phase_Drill": "OEM wise"})
    st.dataframe(meter_combined_display, use_container_width=True)

    # Missing Registers & Small Form Factor Graphs
    st.subheader("❌ Missing Meters Register")
    missing_ids = meter_level[meter_level["profiles_reporting"] == 0]["meter_id"] if "profiles_reporting" in meter_level.columns else pd.Series(dtype=object)
    missing_details = meter_summary[meter_summary["meter_id"].isin(missing_ids)] if not missing_ids.empty else pd.DataFrame()
    missing_list_df = (
        meter_list[meter_list["meter_id"].isin(missing_ids)][["meter_id", "OEM", "Raw_Phase", "capture_period"]]
        .drop_duplicates()
        .sort_values("OEM")
        if not missing_ids.empty
        else pd.DataFrame(columns=["meter_id", "OEM", "Raw_Phase", "capture_period"])
    )
    
    if missing_ids.empty:
        st.success("🎉 All configured baseline tracking points successfully reported profiling data.")
    else:
        st.error(f"⚠️ {missing_ids.nunique()} meters failed to post records.")
        
        st.dataframe(missing_list_df, use_container_width=True)
        
        missing_by_oem = missing_details.groupby("OEM")["meter_id"].nunique().reset_index(name="missing_count")
        missing_by_oem = missing_by_oem.sort_values(by=["OEM"])

        if not missing_by_oem.empty and plt is not None and sns is not None:
            fig, ax = plt.subplots(figsize=(1.9, 1.35), dpi=140)
            sns.barplot(data=missing_by_oem, x="OEM", y="missing_count", color="salmon", width=0.28, ax=ax)
            for container in ax.containers:
                ax.bar_label(container, labels=[f"{int(v.get_height())}" if v.get_height() > 0 else "" for v in container], fontsize=5.5, padding=1)
            ax.set_title("Missing by OEM", fontsize=6.5, fontweight="bold")
            ax.set_xlabel("OEM", fontsize=5.5)
            ax.set_ylabel("Count", fontsize=5.5)
            ax.tick_params(labelsize=5)
            fig.subplots_adjust(left=0.24, right=0.96, top=0.78, bottom=0.28)
            st.pyplot(fig, use_container_width=False)
            _save_png_from_plt(fig, "missing_oem_chart.png")
            plt.close(fig)

    # Mail Dispatches
    st.subheader("✉️ Automated Email Distribution")
    
    email_mode = st.radio("Email Protocol Strategy:", ["Network Standard SMTP Service", "Local Windows Outlook Desktop Instance"], index=0, horizontal=True)
    use_outlook_flag = (email_mode == "Local Windows Outlook Desktop Instance")

    with st.form("email_form"):
        to_email = st.text_input("Recipient Email Address:", value="", placeholder="engineer@domain.com")
        send_now = st.form_submit_button("Send SLA Reports")
        if send_now:
            if not to_email:
                st.error("Please enter a recipient email address.")
            else:
                full_report_name = f"{_safe_filename_part(file_prefix)}_Daily_SLA_Report_{report_date_token}.xlsx"
                missing_report_name = f"{_safe_filename_part(file_prefix)}_Missing_Meters_{report_date_token}.xlsx"
                phase_chart_name = f"{_safe_filename_part(file_prefix)}_OEM_Wise_SLA_Profile_Performance_{report_date_token}.png"
                missing_chart_name = f"{_safe_filename_part(file_prefix)}_Missing_Meters_By_OEM_{report_date_token}.png"
                try:
                    output = io.BytesIO()
                    with get_excel_writer(output) as writer:
                        meter_summary.to_excel(writer, index=False, sheet_name="Meter Summary")
                        meter_level.to_excel(writer, index=False, sheet_name="Meter Level Summary")
                        oem_kpi.to_excel(writer, index=False, sheet_name="OEM Communication")
                        profile_kpi.to_excel(writer, index=False, sheet_name="Profile SLA")
                        phase_chart_data.rename(columns={"OEM_Phase_Drill": "OEM wise"}).to_excel(writer, index=False, sheet_name="OEM SLA Summary")
                        if not meter_combined_display.empty:
                            meter_combined_display.to_excel(writer, index=False, sheet_name="Meter Combined Performance")
                    full_bytes = output.getvalue()
                except Exception:
                    full_bytes = b""

                try:
                    missing_output = io.BytesIO()
                    with get_excel_writer(missing_output) as writer:
                        if not missing_list_df.empty:
                            missing_list_df.to_excel(writer, index=False, sheet_name="Missing Meter Register")
                            missing_details.to_excel(writer, index=False, sheet_name="Missing Profile Detail")
                        else:
                            pd.DataFrame({"Status": ["No missing meters"], "Report": [report_title]}).to_excel(writer, index=False, sheet_name="Missing Meter Register")
                    missing_bytes = missing_output.getvalue()
                except Exception:
                    missing_bytes = b""

                insights = _build_insights(report_title, total_meters, reporting_meters, non_reporting, oem_kpi, profile_kpi, phase_chart_data)
                reporting_pct = (reporting_meters / total_meters * 100) if total_meters else 0
                oem_mail = oem_kpi.copy()
                oem_mail["Reporting %"] = oem_mail["Reporting %"].map(_format_percent)
                oem_mail["Non-Reporting %"] = oem_mail["Non-Reporting %"].map(_format_percent)
                profile_mail = profile_kpi.copy()
                profile_mail["avg_achieved"] = profile_mail["avg_achieved"].map(_format_percent)
                profile_mail["Full Achievement %"] = profile_mail["Full Achievement %"].map(_format_percent)
                phase_mail = phase_chart_data[phase_chart_data["Profile"].astype(str) != "Total Meters"].copy()
                phase_mail["Percent"] = phase_mail["Percent"].map(_format_percent)
                table_style = 'style="width:100%; border-collapse:collapse; text-align:center; font-family:Arial; font-size:12px;"'
                oem_kpi_html = oem_mail.to_html(index=False, justify='center', border=1).replace('class="dataframe"', table_style)
                profile_kpi_html = profile_mail.to_html(index=False, justify='center', border=1).replace('class="dataframe"', table_style)
                phase_mail = phase_mail.rename(columns={"OEM_Phase_Drill": "OEM wise"})
                phase_kpi_html = phase_mail[["OEM wise", "Profile", "Meters", "Percent"]].to_html(index=False, justify='center', border=1).replace('class="dataframe"', table_style)
                insights_html = "".join(f"<li>{item}</li>" for item in insights)
                missing_chart_html = (
                    f'<p><img src="cid:{missing_chart_name}" alt="Missing Meters Summary Breakdown" style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;"></p>'
                    if not missing_list_df.empty and os.path.exists("missing_oem_chart.png")
                    else ""
                )

                html_report = f"""
                <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <h3 style="color: #0d6efd;">{report_title}</h3>
                    <p style="margin-top:0; color:#555;">Daily smart meter communications SLA dashboard for stakeholder review.</p>
                    
                    <div style="display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;">
                        <div style="flex: 1; min-width: 180px; padding: 12px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; border-left: 5px solid #0d6efd;">
                            <b style="font-size: 11px; color: #6c757d; text-transform: uppercase;">Total Baseline Meters</b><br>
                            <span style="font-size: 22px; font-weight: bold; color: #212529;">{total_meters}</span>
                        </div>
                        <div style="flex: 1; min-width: 180px; padding: 12px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; border-left: 5px solid #198754;">
                            <b style="font-size: 11px; color: #6c757d; text-transform: uppercase;">Reporting Unique Count</b><br>
                            <span style="font-size: 22px; font-weight: bold; color: #212529;">{reporting_meters}</span><br>
                            <span style="font-size: 12px; color: #6c757d;">{reporting_pct:.1f}% communication</span>
                        </div>
                        <div style="flex: 1; min-width: 180px; padding: 12px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; border-left: 5px solid #dc3545;">
                            <b style="font-size: 11px; color: #6c757d; text-transform: uppercase;">Non-Reporting Faults</b><br>
                            <span style="font-size: 22px; font-weight: bold; color: #212529;">{non_reporting}</span>
                        </div>
                    </div>

                    <p><b>Reporting date:</b> {reporting_date}<br><b>Report generated:</b> {datetime.now().strftime("%d-%b-%Y %H:%M")}</p>

                    <h4>Management Insights</h4>
                    <ul>{insights_html}</ul>
                    
                    <h4>🏭 Communication Status - OEM Wise Matrix</h4>
                    <div style="margin-bottom: 20px;">{oem_kpi_html}</div>

                    <h4>📊 Profile Performance Visual Chart</h4>
                    <h4>Profile-wise SLA Summary</h4>
                    <div style="margin-bottom: 20px;">{profile_kpi_html}</div>

                    <h4>OEM-wise SLA Profile Performance</h4>
                    <div style="margin-bottom: 20px;">{phase_kpi_html}</div>
                    <p><img src="cid:{phase_chart_name}" alt="OEM-wise SLA Profile Performance" style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;"></p>

                    <h4>❌ Missing Meters Breakdown View</h4>
                    <p>{"No missing meters were identified." if missing_list_df.empty else f"{len(missing_list_df)} missing meter(s) are attached in the missing meter register."}</p>
                    {missing_chart_html}

                    <br>
                    <p style="font-size: 12px; color: #777;">Attachments include the full SLA workbook and the missing meter register with meaningful report names.</p>
                </body>
                </html>
                """
                
                attachments_map = {}
                if os.path.exists("phase_profile_chart.png"):
                    with open("phase_profile_chart.png", "rb") as f:
                        attachments_map[phase_chart_name] = f.read()
                if not missing_list_df.empty and os.path.exists("missing_oem_chart.png"):
                    with open("missing_oem_chart.png", "rb") as f:
                        attachments_map[missing_chart_name] = f.read()
                if missing_bytes:
                    attachments_map[missing_report_name] = missing_bytes

                with st.spinner("Processing dispatch mail queue..."):
                    subject = f"{subject_prefix} Daily SLA Dashboard - {reporting_date}"
                    ok, msg = send_email_report(
                        to_email,
                        subject,
                        full_bytes,
                        html_report,
                        full_report_name=full_report_name,
                        attachments_dict=attachments_map,
                        use_outlook=use_outlook_flag,
                    )
                    if ok:
                        st.success("SLA report workbook successfully transmitted!")
                    else:
                        st.error(f"Failed to post email messages: {msg}")

    # Local Excel Exports Link
    st.subheader("📥 Export Workbook Sheets")
    try:
        output = io.BytesIO()
        with get_excel_writer(output) as writer:
            meter_summary.to_excel(writer, index=False, sheet_name="Meter Summary")
            meter_level.to_excel(writer, index=False, sheet_name="Meter Level Summary")
            oem_kpi.to_excel(writer, index=False, sheet_name="OEM Communication")
            profile_kpi.to_excel(writer, index=False, sheet_name="Profile SLA")
            phase_chart_data.rename(columns={"OEM_Phase_Drill": "OEM wise"}).to_excel(writer, index=False, sheet_name="OEM SLA Summary")
            missing_list_df.to_excel(writer, index=False, sheet_name="Missing Meter Register")
            if not meter_combined_display.empty:
                meter_combined_display.to_excel(writer, index=False, sheet_name="Meter Combined Performance")
        
        st.download_button(
            label="📥 Download Full Report (Excel)",
            data=output.getvalue(),
            file_name=f"{_safe_filename_part(file_prefix)}_Daily_SLA_Report_{report_date_token}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="full_report_download"
        )
    except Exception as e:
        st.warning(f"Could not build local download context stream: {e}")

if __name__ == "__main__":
    run()
