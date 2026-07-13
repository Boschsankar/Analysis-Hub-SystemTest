import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import pandas as pd
import re
import io
import math

# ==============================================================================
# EXACT REGISTRY SCHEMA MAPS
# Formulated explicitly using the provided 1P and 3P data models.
# ==============================================================================
METER_PROFILE_SCHEMAS = {
    "7": {
        "profile_name": "Standard 1-Phase Block Load Profile",
        "fields": [
            {"key": "RTC Timestamp", "type": "datetime", "scale": 1},
            {"key": "Average Voltage", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Import", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Import", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Export", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Export", "type": "numeric", "scale": 100.0},
            {"key": "Average Current", "type": "numeric", "scale": 1000.0}
        ]
    },
    "9": {
        "profile_name": "AEW 1-Phase Block Load Profile",
        "fields": [
            {"key": "RTC Timestamp", "type": "datetime", "scale": 1},
            {"key": "Average Voltage", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Import", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Import", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Export", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Export", "type": "numeric", "scale": 100.0},
            {"key": "Average Current", "type": "numeric", "scale": 1000.0},
            {"key": "Meter Health Indicator", "type": "numeric", "scale": 1.0},
            {"key": "Average Signal strength (RSSI)", "type": "numeric", "scale": 1.0}
        ]
    },
    "13": {
        "profile_name": "AEW 3-Phase Block Load Profile",
        "fields": [
            {"key": "RTC Timestamp", "type": "datetime", "scale": 1},
            {"key": "Average Current - IR", "type": "numeric", "scale": 1000.0},
            {"key": "Average Current - IY", "type": "numeric", "scale": 1000.0},
            {"key": "Average Current - IB", "type": "numeric", "scale": 1000.0},
            {"key": "Average Voltage - VRN", "type": "numeric", "scale": 100.0},
            {"key": "Average Voltage - VYN", "type": "numeric", "scale": 100.0},
            {"key": "Average Voltage - VBN", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Import", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Import", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Export", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Export", "type": "numeric", "scale": 100.0},
            {"key": "Meter Health Indicator", "type": "numeric", "scale": 1.0},
            {"key": "Average Signal strength (RSSI)", "type": "numeric", "scale": 1.0}
        ]
    },
    "15": {
        "profile_name": "Standard 3-Phase Block Load Profile",
        "fields": [
            {"key": "RTC Timestamp", "type": "datetime", "scale": 1},
            {"key": "Average Current - IR", "type": "numeric", "scale": 1000.0},
            {"key": "Average Current - IY", "type": "numeric", "scale": 1000.0},
            {"key": "Average Current - IB", "type": "numeric", "scale": 1000.0},
            {"key": "Average Voltage - VRN", "type": "numeric", "scale": 100.0},
            {"key": "Average Voltage - VYN", "type": "numeric", "scale": 100.0},
            {"key": "Average Voltage - VBN", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Import/Forwarded", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kWh Export", "type": "numeric", "scale": 100.0},
            {"key": "Block energy. kvarh-Q1\\Lag", "type": "numeric", "scale": 100.0},
            {"key": "Block energy. kvarh-Q2\\Lead", "type": "numeric", "scale": 100.0},
            {"key": "Block energy. kvarh-Q3\\Lag", "type": "numeric", "scale": 100.0},
            {"key": "Block energy. kvarh-Q4\\Lead", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Import/Forwarded", "type": "numeric", "scale": 100.0},
            {"key": "Block Energy - kVAh Export", "type": "numeric", "scale": 100.0}
        ]
    }
}

FIELD_LABEL_ALIASES = {
    "rtc": "RTC Timestamp",
    "rtc timestamp": "RTC Timestamp",
    "0.0.1.0.0.255": "RTC Timestamp",
    "average voltage": "Average Voltage",
    "1.0.12.27.0.255": "Average Voltage",
    "average current": "Average Current",
    "1.0.11.27.0.255": "Average Current",
    "current,ir": "Average Current - IR",
    "current, iy": "Average Current - IR",
    "1.0.31.27.0.255": "Average Current - IR",
    "current,iy": "Average Current - IY",
    "current, iy": "Average Current - IY",
    "1.0.51.27.0.255": "Average Current - IY",
    "current,ib": "Average Current - IB",
    "current, ib": "Average Current - IB",
    "1.0.71.27.0.255": "Average Current - IB",
    "voltage,vrn": "Average Voltage - VRN",
    "voltage, vrn": "Average Voltage - VRN",
    "1.0.32.27.0.255": "Average Voltage - VRN",
    "voltage,vyn": "Average Voltage - VYN",
    "voltage, vyn": "Average Voltage - VYN",
    "1.0.52.27.0.255": "Average Voltage - VYN",
    "voltage,vbn": "Average Voltage - VBN",
    "voltage, vbn": "Average Voltage - VBN",
    "1.0.72.27.0.255": "Average Voltage - VBN",
    "block energy - kwh import": "Block Energy - kWh Import",
    "block energy wh-(import)": "Block Energy - kWh Import",
    "energy - wh import": "Block Energy - kWh Import",
    "1.0.1.29.0.255": "Block Energy - kWh Import",
    "block energy - kvah import": "Block Energy - kVAh Import",
    "block energy vah-(import)": "Block Energy - kVAh Import",
    "energy - vah import": "Block Energy - kVAh Import",
    "1.0.9.29.0.255": "Block Energy - kVAh Import",
    "block energy - kwh export": "Block Energy - kWh Export",
    "block energy wh-export": "Block Energy - kWh Export",
    "energy - wh export": "Block Energy - kWh Export",
    "1.0.2.29.0.255": "Block Energy - kWh Export",
    "block energy - kvah export": "Block Energy - kVAh Export",
    "block energy vah-export": "Block Energy - kVAh Export",
    "energy - vah export": "Block Energy - kVAh Export",
    "1.0.10.29.0.255": "Block Energy - kVAh Export",
    "block energy - kwh import/forwarded": "Block Energy - kWh Import/Forwarded",
    "block energy - kvah import/forwarded": "Block Energy - kVAh Import/Forwarded",
    "metering current": "Average Current",
    "meter health indicator": "Meter Health Indicator",
    "0.96.10.1.255": "Meter Health Indicator",
    "average signal strength (rssi)": "Average Signal strength (RSSI)",
    "average signal strength": "Average Signal strength (RSSI)",
    "0.1.96.12.5.255": "Average Signal strength (RSSI)"
}

def canonicalize_field_label(raw_label):
    if not raw_label:
        return raw_label
    normalized = re.sub(r'[^a-z0-9,.\-() ]+', '', raw_label.lower()).strip()
    return FIELD_LABEL_ALIASES.get(normalized, raw_label.strip())


def infer_profile_name(field_entries, base_profile_name):
    aliases = [canonicalize_field_label(entry['comment']) for entry in field_entries if entry['comment']]
    if any('average current - ir' in alias or 'current,ir' in alias for alias in aliases):
        return 'AEW Standard 3-Phase Block Load Profile'
    if any('block energy - kwh import/forwarded' in alias for alias in aliases):
        return 'HPL 1P Elite Block Load Profile'
    if any('metering current' in alias for alias in aliases):
        return 'HP RF100 1P Block Load Profile'
    if any('meter health indicator' in alias for alias in aliases):
        return base_profile_name + ' with Meter Health Metadata'
    return base_profile_name


def decode_dlms_timestamp(octet_str):
    """
    Decodes standard DLMS 12-byte hex string (e.g., '07EA0601FF0E0F00FF014AFF')
    into a human-readable date-time format.
    """
    try:
        octet_str = octet_str.replace(" ", "")
        year = int(octet_str[0:4], 16)
        month = int(octet_str[4:6], 16)
        day = int(octet_str[6:8], 16)
        # Skip index 8:10 (day of week or wildcard handling)
        hour = int(octet_str[10:12], 16)
        minute = int(octet_str[12:14], 16)
        second = int(octet_str[14:16], 16)
        return datetime(year, month, day, hour, minute, second).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return "N/A"


def calculate_expected_current(active_load, voltage, is_3p):
    """Estimate expected current from active load and actual voltage."""
    if active_load <= 0:
        return 0.0
    if voltage and isinstance(voltage, (int, float)) and voltage > 0:
        if is_3p:
            return active_load / (math.sqrt(3) * voltage)
        return active_load / voltage
    return (active_load / 3.0) / 240.0 if is_3p else active_load / 240.0


def current_formula_summary(is_3p):
    if is_3p:
        return "I_expected = P / (√3 × V)"
    return "I_expected = P / V"


def get_readable_asset_id(field_entries, system_title):
    asset_id = system_title
    if field_entries:
        first_entry = field_entries[0]
        if first_entry['comment']:
            candidate = first_entry['comment'].strip()
            if len(candidate) >= 3:
                asset_id = candidate
        else:
            try:
                decoded = bytes.fromhex(first_entry['raw']).decode('ascii')
                if decoded.isprintable() and decoded:
                    asset_id = decoded
            except Exception:
                pass
    return asset_id


def format_metric_value(field, value):
    if isinstance(value, float):
        if "Current" in field:
            return f"{value:.3f}"
        if "Voltage" in field:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def prepare_plot_data(parsed_records):
    rows = []
    for r in parsed_records:
        row = {
            "Record": r["Sample_Index"],
            "Profile_Type": r["Profile_Type"]
        }
        row.update(r["Metrics"])
        rows.append(row)
    return pd.DataFrame(rows)


def build_html_report(parsed_records, diagnostics_by_record, reviewer_notes, chart_html=None):
    html = [
        "<html><head><meta charset='utf-8'/><title>Meter Validation Report</title>",
        "<style>body{font-family:Arial,sans-serif;margin:24px;}h1,h2,h3{color:#0b3d91;}table{border-collapse:collapse;width:100%;margin-bottom:24px;}td,th{border:1px solid #ddd;padding:8px;}th{background:#f4f6fb;text-align:left;} .pass{color:green;}.fail{color:red;}.warn{color:orange;}</style>",
        "</head><body>",
        f"<h1>Meter Validation Report</h1>",
        f"<p><strong>Summary:</strong> {reviewer_notes}</p>",
        "<h2>Pass / Fail Criteria</h2>",
        section_pass_fail_criteria()
    ]

    for r in parsed_records:
        html.append(f"<h2>{r['Sample_Index']} — {r['Profile_Type']}</h2>")
        html.append(f"<p><strong>Asset:</strong> {r.get('Asset_ID', r['System_Title'])}</p>")
        metrics_df = pd.DataFrame([{
            'Field': field,
            'Value': format_metric_value(field, value)
        } for field, value in r['Metrics'].items()])
        html.append(metrics_df.to_html(index=False, escape=False))

        combined_df = build_combined_field_validation_table([r], {r['Sample_Index']: diagnostics_by_record.get(r['Sample_Index'], {})})
        html.append(f"<h3>Combined Field Mapping and Validation</h3>{combined_df.to_html(index=False, escape=False)}")

    if chart_html:
        html.append("<h2>Trend Charts</h2>")
        html.append(chart_html)

    html.append("</body></html>")
    return ''.join(html)


def build_combined_field_validation_table(parsed_records, diagnostics_by_record):
    rows = []
    for r in parsed_records:
        diagnostics = diagnostics_by_record.get(r['Sample_Index'], {})
        for field_meta in r['FieldMeta']:
            field_key = field_meta['FieldKey']
            diagnostic = diagnostics.get(field_key, ('', ''))
            rows.append({
                'Record': r['Sample_Index'],
                'Asset': r.get('Asset_ID', r['System_Title']),
                'Profile Type': r['Profile_Type'],
                'Captured Object': field_key,
                'Standard Field': field_meta.get('SchemaField', ''),
                'Object Reference': field_meta.get('ObjectReference', ''),
                'Raw Hex Value': field_meta['RawValue'],
                'Interpreted Value': format_metric_value(field_key, r['Metrics'].get(field_key, '')),
                'Validation Status': diagnostic[0],
                'Validation Detail': diagnostic[1]
            })
    return pd.DataFrame(rows)


def section_pass_fail_criteria():
    return (
        "<ul>"
        "<li><strong>Voltage:</strong> PASS if 210 V ≤ V ≤ 260 V.</li>"
        "<li><strong>Current:</strong> PASS if actual current is within ±15% of expected current.</li>"
        "<li><strong>Current formula:</strong> " + current_formula_summary(False) + " for 1P and " + current_formula_summary(True) + " for 3P.</li>"
        "<li><strong>Energy:</strong> PASS if block energy values are non-negative and not flat while load is active.</li>"
        "</ul>"
    )


def summary_insights(parsed_records, diagnostics_by_record):
    total_records = len(parsed_records)
    pass_count = sum(1 for record in diagnostics_by_record.values() for flag, _ in record.values() if flag == 'PASS')
    fail_count = sum(1 for record in diagnostics_by_record.values() for flag, _ in record.values() if flag == 'FAIL')
    warn_count = sum(1 for record in diagnostics_by_record.values() for flag, _ in record.values() if flag == 'WARN')
    return (
        f"Processed {total_records} record(s). Validation summary: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL. "
        "Review the diagnostic table for field-specific details and formula references."
    )


def parse_dlms_xml_stream(raw_text):
    """
    Parses structural XML wrapper notifications, isolating the data matrices
    and mapping parameters dynamically based on the tag quantity and nested array content.
    """
    def select_data_block(block_text):
        structures = re.findall(r'<Structure\s+Qty="0?(\d+)".*?>(.*?)</Structure>', block_text, re.DOTALL)
        if not structures:
            return None, None

        best_structure = None
        best_field_count = -1
        for qty_text, content in structures:
            field_tags = re.findall(r'<(?:OctetString|UInt16|UInt32|Integer16|Integer32|DateTime)\s+Value="', content)
            field_count = len(field_tags)   
            if field_count > best_field_count:
                best_field_count = field_count
                best_structure = (int(qty_text), content)

        return best_structure if best_structure is not None else (None, None)

    def extract_fields_from_structure(structure_text):
        field_pattern = re.compile(
            r'(?:#\s*(?P<comment>[^\n]+)\s*\n\s*)?'
            r'<(?P<tag>OctetString|UInt16|UInt32|Integer16|Integer32|DateTime)\s+Value="(?P<value>[0-9A-Fa-f]*)"',
            re.DOTALL
        )

        fields = []
        for match in field_pattern.finditer(structure_text):
            comment = match.group('comment') or ''
            fields.append({
                'tag': match.group('tag'),
                'raw': match.group('value'),
                'comment': comment.strip()
            })
        return fields

    def build_schema_for_fields(field_entries, asset_id=None):
        count = len(field_entries)
        if str(count) in METER_PROFILE_SCHEMAS:
            schema = METER_PROFILE_SCHEMAS[str(count)].copy()
            if count == 7 and asset_id and asset_id.upper().startswith('HPLHL'):
                schema = {
                    'profile_name': 'HPL 1P Elite Block Load Profile',
                    'fields': [
                        {'key': 'RTC Timestamp', 'type': 'datetime', 'scale': 1},
                        {'key': 'Average Voltage', 'type': 'numeric', 'scale': 100.0},
                        {'key': 'Block Energy - kWh Import/Forwarded', 'type': 'numeric', 'scale': 100.0},
                        {'key': 'Block Energy - kVAh Import/Forwarded', 'type': 'numeric', 'scale': 100.0},
                        {'key': 'Block Energy - kWh Export', 'type': 'numeric', 'scale': 100.0},
                        {'key': 'Block Energy - kVAh Export', 'type': 'numeric', 'scale': 100.0},
                        {'key': 'Average Current', 'type': 'numeric', 'scale': 1000.0}
                    ]
                }
            schema['profile_name'] = infer_profile_name(field_entries, schema['profile_name'])
            return schema

        guessed_fields = []
        for idx, entry in enumerate(field_entries):
            if idx == 0 and entry['tag'] == 'OctetString' and len(entry['raw']) == 24:
                guessed_fields.append({'key': 'RTC Timestamp', 'type': 'datetime', 'scale': 1})
            else:
                comment_label = canonicalize_field_label(entry['comment']) if entry['comment'] else None
                if comment_label and comment_label != entry['comment']:
                    guessed_fields.append({'key': comment_label, 'type': 'numeric', 'scale': 100.0})
                else:
                    guessed_fields.append({'key': f'Field {idx + 1}', 'type': 'numeric', 'scale': 100.0})

        return {
            'profile_name': f'Dynamic {count}-Field Profile',
            'fields': guessed_fields
        }

    def normalize_field_label(entry, schema_field, index):
        if schema_field and schema_field['key']:
            if entry['comment']:
                resolved = canonicalize_field_label(entry['comment'])
                if resolved != entry['comment'] and resolved in FIELD_LABEL_ALIASES.values():
                    return resolved
            return schema_field['key']
        if entry['comment']:
            return canonicalize_field_label(entry['comment'])
        return f'Field {index + 1}'

    wrapper_blocks = re.findall(r'<WRAPPER.*?>(.*?)</WRAPPER>', raw_text, re.DOTALL)
    parsed_records = []

    for idx, block in enumerate(wrapper_blocks, start=1):
        try:
            sys_title_match = re.search(r'<SystemTitle\s+Value="([0-9A-Fa-f]+)"', block)
            system_title = sys_title_match.group(1) if sys_title_match else f'Unknown_Asset_{idx}'

            qty_val, target_content = select_data_block(block)
            if target_content is None:
                continue

            field_entries = extract_fields_from_structure(target_content)
            if not field_entries:
                continue

            asset_id = get_readable_asset_id(field_entries, system_title)
            active_schema = build_schema_for_fields(field_entries, asset_id)
            schema_fields = active_schema['fields']

            record_dict = {
                'Sample_Index': f'Record {idx}',
                'System_Title': system_title,
                'Asset_ID': asset_id,
                'Profile_Type': active_schema['profile_name'],
                'Metrics': {},
                'RawMetrics': {},
                'FieldMeta': []
            }

            for field_index, entry in enumerate(field_entries):
                schema_field = schema_fields[field_index] if field_index < len(schema_fields) else None
                field_key = normalize_field_label(entry, schema_field, field_index)
                record_dict['RawMetrics'][field_key] = entry['raw']
                record_dict['FieldMeta'].append({
                    'FieldKey': field_key,
                    'TagType': entry['tag'],
                    'RawValue': entry['raw'],
                    'SchemaField': schema_field['key'] if schema_field else None,
                    'ObjectReference': entry['comment']
                })

                if schema_field and schema_field['type'] == 'datetime':
                    record_dict['Metrics'][field_key] = decode_dlms_timestamp(entry['raw'])
                elif entry['tag'] == 'DateTime' or (entry['tag'] == 'OctetString' and len(entry['raw']) == 24):
                    record_dict['Metrics'][field_key] = decode_dlms_timestamp(entry['raw'])
                else:
                    try:
                        record_dict['Metrics'][field_key] = int(entry['raw'], 16) / (schema_field['scale'] if schema_field else 100.0)
                    except ValueError:
                        record_dict['Metrics'][field_key] = entry['raw']

            parsed_records.append(record_dict)
        except Exception:
            continue

    return parsed_records


def evaluate_electrical_physics(metrics, active_load, time_frame):
    """
    Validates telemetry against active phase configuration rules and performs generic checks
    for every parsed value so the page supports multiple meter families dynamically.
    """
    logs = {}
    is_3p = any(k in metrics and any(phase in k for phase in ['VRN', 'VYN', 'VBN', 'IR', 'IY', 'IB']) for k in metrics)
    voltage = next((value for k, value in metrics.items() if 'Average Voltage' in k and isinstance(value, (int, float))), None)
    expected_current = calculate_expected_current(active_load, voltage, is_3p)
    expected_formula = current_formula_summary(is_3p)
    target_wh = active_load * (time_frame / 60.0)

    for param, value in metrics.items():
        if isinstance(value, str):
            if value == 'N/A' or value.strip() == '':
                logs[param] = ('WARN', 'Timestamp or text field missing / could not be decoded.')
            else:
                logs[param] = ('PASS', 'Text or datetime field decoded successfully.')
            continue

        if 'Voltage' in param:
            if 210 <= value <= 260:
                logs[param] = ('PASS', f'Voltage within acceptable band: {value:.2f} V.')
            else:
                logs[param] = ('FAIL', f'Voltage out of nominal range: {value:.2f} V.')
            continue

        if 'Current' in param:
            if active_load == 0 and value == 0:
                logs[param] = ('PASS', 'Zero current condition is nominal for no-load operation.')
            elif expected_current > 0 and expected_current * 0.85 <= value <= expected_current * 1.15:
                logs[param] = ('PASS', f'Current approximates expected load current ({expected_formula}): {value:.3f} A, expected {expected_current:.3f} A.')
            else:
                logs[param] = ('FAIL', f'Current does not match expected load window ({expected_formula}): {value:.3f} A, expected {expected_current:.3f} A.')
            continue

        if 'kWh' in param or 'kVAh' in param or 'Energy' in param:
            if value < 0:
                logs[param] = ('FAIL', f'Negative energy reading detected: {value:.2f}.')
            elif active_load > 0 and value == 0:
                logs[param] = ('WARN', f'Energy counter flat while load is active ({active_load} W).')
            else:
                logs[param] = ('PASS', f'Energy value validated: {value:.2f}.')
            continue

        if 'Timestamp' in param or 'DateTime' in param:
            logs[param] = ('PASS', f'Datetime field present: {value}.')
            continue

        if isinstance(value, (int, float)):
            if value == 0:
                logs[param] = ('WARN', 'Zero numeric field detected; verify mapping or instrument configuration.')
            elif value > 1e8:
                logs[param] = ('WARN', 'Large numeric value detected; check scaling and offset assumptions.')
            else:
                logs[param] = ('PASS', 'Numeric field parsed successfully.')
            continue

        logs[param] = ('PASS', 'Field parsed and included in validation.')

    return logs


def main():
    st.set_page_config(layout="wide", page_title="Universal Meter Data Analyzer")
    st.title("⚡ Dynamic Multi-Vendor DLMS Stream Diagnostic Terminal")
    st.markdown(
        "Automated smart meter structural compliance engine. Handles alignment variables layout processing smoothly.")
    st.write("---")

    # Bench Configuration Block Control Group
    with st.container(border=True):
        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            st.markdown("### 🎛️ Verification Control Inputs")
            bench_load = st.selectbox("Test Bench Active Load (Watts)", [0, 50, 100, 200, 500], index=2)
            time_window = st.number_input("Integration Step Window (Minutes)", min_value=1, max_value=60, value=15)
            st.metric(label="Calculated Energy Delta Expected", value=f"{bench_load * (time_window / 60.0):.2f} Wh")
        with col_c2:
            st.markdown("### 📥 Decrypted Packet Stream Input")
            with st.form(key="dlms_ingest_form"):
                stream_payload = st.text_area("Paste Raw Unwrapped XML Logs here:", value="", height=160)
                execute_audit = st.form_submit_button(label="🚀 Execute Structural Verification")

    if not (execute_audit and stream_payload.strip()):
        st.info("Awaiting smart meter telemetry stream log entries input inside terminal panel.")
        return

    parsed_records = parse_dlms_xml_stream(stream_payload)
    if not parsed_records:
        st.error(
            "🚫 Processing Exception: No matching structural wrapper matrices resolved. Please verify structural parameters data integrity.")
        return

    # ==============================================================================
    # SECTION 1: DASHBOARD MATRIX VIEW
    # ==============================================================================
    st.write("### 📊 Dashboard Matrix View")
    st.info(f"**Auto-Detected Profiler:** {parsed_records[0]['Profile_Type']}")

    matrix_rows = []
    diagnostics_by_record = {}
    for r in parsed_records:
        diagnostics_by_record[r["Sample_Index"]] = evaluate_electrical_physics(r["Metrics"], bench_load, time_window)

    for r in parsed_records:
        row_summary = {
            "Index": r["Sample_Index"],
            "Asset Identification": r.get("Asset_ID", r["System_Title"])
        }
        for field, value in r["Metrics"].items():
            if "Timestamp" in field:
                row_summary[field] = str(value)
            elif "Current" in field:
                row_summary[f"{field} (A)"] = format_metric_value(field, value)
            elif "Voltage" in field:
                row_summary[f"{field} (V)"] = format_metric_value(field, value)
            else:
                row_summary[field] = format_metric_value(field, value)

        anomaly_flag = any(status == "FAIL" for status, _ in diagnostics_by_record[r["Sample_Index"]].values())
        row_summary["System Health Evaluation"] = "❌ DISCREPANCY" if anomaly_flag else "🟢 NOMINAL OPERATION"
        matrix_rows.append(row_summary)

    df_matrix = pd.DataFrame(matrix_rows)
    st.dataframe(df_matrix, use_container_width=True, hide_index=True)

    st.write("### 📌 Reviewer Notes & Pass/Fail Criteria")
    reviewer_notes = summary_insights(parsed_records, diagnostics_by_record)
    st.markdown(f"**Summary:** {reviewer_notes}")
    st.markdown(section_pass_fail_criteria(), unsafe_allow_html=True)

    # HTML report export and preview
    html_report = build_html_report(parsed_records, diagnostics_by_record, reviewer_notes)
    st.write("### 📄 Generated HTML Validation Report")
    st.download_button(
        label="Download HTML Validation Report",
        data=html_report.encode('utf-8'),
        file_name="meter_validation_report.html",
        mime="text/html"
    )
    try:
        components.html(html_report, height=640, scrolling=True)
    except Exception:
        st.info("HTML preview is unavailable in this environment; use the download button to export the report.")

    plot_df = prepare_plot_data(parsed_records)
    if not plot_df.empty:
        st.write("### 📈 Trend Analysis")
        chart_cols = []
        if any("Average Voltage" in c for c in plot_df.columns):
            voltage_cols = [c for c in plot_df.columns if "Average Voltage" in c]
            chart_cols.extend(voltage_cols)
        if any("Block Energy - kWh Import" in c for c in plot_df.columns):
            chart_cols.append("Block Energy - kWh Import")

        if chart_cols:
            trend_df = plot_df[["Record"] + chart_cols].copy()
            trend_df = trend_df.set_index("Record")
            st.line_chart(trend_df)

    combined_df = build_combined_field_validation_table(parsed_records, diagnostics_by_record)
    st.write("### 🧾 Unified Raw/Standard/Validation Table")
    st.dataframe(combined_df, use_container_width=True, hide_index=True)

    # ==============================================================================
    # SECTION 2: VALIDATION WITH JUSTIFICATION
    # ==============================================================================
    st.write("---")
    st.write("### 🔍 Granular Validation & Engineering Justification Matrix")

    for r in parsed_records:
        with st.expander(f"📋 Parameter Analysis Breakdown — {r['Sample_Index']} (Asset: {r.get('Asset_ID', r['System_Title'])})",
                         expanded=True):
            diagnostics = evaluate_electrical_physics(r["Metrics"], bench_load, time_window)

            justification_table = []
            for param, (flag, narrative) in diagnostics.items():
                justification_table.append({
                    "Hardware Data Channel Parameter": param,
                    "Evaluation Status Flag": "🟢 PASS" if flag == "PASS" else "🔴 FAIL",
                    "Engineering Physics Justification / Calculation Log": narrative
                })

            st.table(pd.DataFrame(justification_table))


def run():
    """Entry point for Streamlit framework."""
    main()


if __name__ == "__main__":
    main()