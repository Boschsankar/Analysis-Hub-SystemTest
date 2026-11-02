import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st


def run():
    """Run the Last Gasp and First Breath validation tool from the hub."""
    st.caption(
        "Upload a meter list and HES ESWF event report to validate alert "
        "coverage, SLA compliance, and required actions."
    )
    return upload_and_validate_lastgasp_firstbreath()


def upload_and_validate_lastgasp_firstbreath():
    """
    Streamlit upload-and-validation module for Last Gasp and First Breath.

    INPUT 1:
        Meter master/list file in XLSX, XLS, or CSV format.

    INPUT 2:
        HES ESWF Events file in XLSX, XLS, or CSV format.

    MAIN RULES:
        1. Only meters available in the meter master are considered.
        2. Last Gasp and First Breath alerts are identified from Description.
        3. Duplicate event rows do not increase the received count.
        4. One meter contributes a maximum count of:
              - 1 Last Gasp
              - 1 First Breath
        5. Delay = HES Received Time - Meter Date & Time.
        6. SLA Pass requires:
              0 <= Delay < 3 minutes
        7. Negative delays and invalid timestamps are treated separately.
        8. Output includes received, missing, duplicate, SLA, and consolidated views.
    """

    # ================================================================
    # INTERNAL HELPER FUNCTIONS
    # ================================================================

    def normalize_column_name(value):
        """
        Normalizes a column name for reliable alias matching.
        Example:
            'Meter Sr. No' -> 'metersrno'
            'Meter Date & Time' -> 'meterdatetime'
        """
        return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())

    def normalize_meter_number(value):
        """
        Normalizes meter numbers without changing meaningful characters.

        Handles common Excel issues such as:
            123456.0 -> 123456
            leading/trailing spaces
            missing values
        """
        if pd.isna(value):
            return pd.NA

        text = str(value).strip()

        if not text or text.lower() in {"nan", "none", "nat", "<na>"}:
            return pd.NA

        # Remove Excel-generated trailing .0 for integer-style meter numbers.
        if re.fullmatch(r"-?\d+\.0", text):
            text = text[:-2]

        return text.upper()

    def read_uploaded_file(uploaded_file):
        """
        Reads XLSX, XLS, XLSM, or CSV uploads.
        Returns a DataFrame and the selected sheet name where applicable.
        """
        if uploaded_file is None:
            return None, None

        uploaded_file.seek(0)
        extension = Path(uploaded_file.name).suffix.lower()

        if extension == ".csv":
            raw_bytes = uploaded_file.getvalue()

            # Try common CSV encodings.
            encoding_options = ["utf-8-sig", "utf-8", "latin-1"]
            last_error = None

            for encoding in encoding_options:
                try:
                    raw_text = raw_bytes.decode(encoding)
                    first_line = raw_text.splitlines()[0] if raw_text else ""
                    separator = next(
                        (
                            candidate
                            for candidate in [",", ";", "\t", "|"]
                            if candidate in first_line
                        ),
                        ",",
                    )
                    dataframe = pd.read_csv(
                        io.StringIO(raw_text),
                        dtype=object,
                        sep=separator,
                    )
                    return dataframe, "CSV"
                except Exception as error:
                    last_error = error

            raise ValueError(
                f"Unable to read CSV file '{uploaded_file.name}'. "
                f"Last error: {last_error}"
            )

        if extension in {".xlsx", ".xlsm", ".xls"}:
            excel_bytes = io.BytesIO(uploaded_file.getvalue())
            excel_file = pd.ExcelFile(excel_bytes)

            if not excel_file.sheet_names:
                raise ValueError(
                    f"No worksheet was found in '{uploaded_file.name}'."
                )

            # Prefer a meaningful non-empty sheet.
            preferred_words = [
                "meter",
                "event",
                "eswf",
                "last gasp",
                "first breath",
                "data",
                "report",
            ]

            ordered_sheets = sorted(
                excel_file.sheet_names,
                key=lambda sheet_name: (
                    not any(
                        word in sheet_name.lower()
                        for word in preferred_words
                    ),
                    excel_file.sheet_names.index(sheet_name),
                ),
            )

            first_non_empty_dataframe = None
            first_non_empty_sheet = None

            for sheet_name in ordered_sheets:
                current_dataframe = pd.read_excel(
                    excel_file,
                    sheet_name=sheet_name,
                    dtype=object,
                )

                current_dataframe = current_dataframe.dropna(
                    how="all"
                ).dropna(axis=1, how="all")

                if not current_dataframe.empty:
                    first_non_empty_dataframe = current_dataframe
                    first_non_empty_sheet = sheet_name
                    break

            if first_non_empty_dataframe is None:
                raise ValueError(
                    f"All worksheets in '{uploaded_file.name}' are empty."
                )

            return first_non_empty_dataframe, first_non_empty_sheet

        raise ValueError(
            "Unsupported file format. Upload an XLSX, XLS, XLSM, or CSV file."
        )

    def detect_header_row(uploaded_file, required_alias_groups, max_rows=20):
        """
        Attempts to detect the real header row when the Excel report contains
        title rows before the actual table.

        required_alias_groups:
            List containing alias lists.
            A candidate header must match at least one alias from each group.
        """
        uploaded_file.seek(0)
        extension = Path(uploaded_file.name).suffix.lower()

        if extension == ".csv":
            # CSV is expected to have the header in the first row.
            dataframe, sheet_name = read_uploaded_file(uploaded_file)
            return dataframe, sheet_name, 0

        excel_bytes = io.BytesIO(uploaded_file.getvalue())
        excel_file = pd.ExcelFile(excel_bytes)

        for sheet_name in excel_file.sheet_names:
            preview = pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
                header=None,
                nrows=max_rows,
                dtype=object,
            )

            if preview.empty:
                continue

            for row_index in range(len(preview)):
                row_values = {
                    normalize_column_name(value)
                    for value in preview.iloc[row_index].tolist()
                    if pd.notna(value)
                }

                all_groups_found = True

                for alias_group in required_alias_groups:
                    normalized_aliases = {
                        normalize_column_name(alias)
                        for alias in alias_group
                    }

                    if not row_values.intersection(normalized_aliases):
                        all_groups_found = False
                        break

                if all_groups_found:
                    dataframe = pd.read_excel(
                        excel_file,
                        sheet_name=sheet_name,
                        header=row_index,
                        dtype=object,
                    )

                    dataframe = dataframe.dropna(
                        how="all"
                    ).dropna(axis=1, how="all")

                    return dataframe, sheet_name, row_index

        # Fall back to the normal file reader.
        dataframe, sheet_name = read_uploaded_file(uploaded_file)
        return dataframe, sheet_name, 0

    def find_column(dataframe, aliases, required=True):
        """
        Finds a DataFrame column using normalized aliases.
        """
        normalized_column_map = {
            normalize_column_name(column): column
            for column in dataframe.columns
        }

        # First, try exact normalized alias matching.
        for alias in aliases:
            normalized_alias = normalize_column_name(alias)

            if normalized_alias in normalized_column_map:
                return normalized_column_map[normalized_alias]

        # Second, try conservative partial matching.
        for normalized_column, original_column in normalized_column_map.items():
            for alias in aliases:
                normalized_alias = normalize_column_name(alias)

                if (
                        normalized_alias
                        and len(normalized_alias) >= 6
                        and (
                        normalized_alias in normalized_column
                        or normalized_column in normalized_alias
                )
                ):
                    return original_column

        if required:
            raise ValueError(
                "Required column was not found.\n\n"
                f"Accepted names: {', '.join(aliases)}\n\n"
                f"Available columns: {', '.join(map(str, dataframe.columns))}"
            )

        return None

    def parse_datetime_series(series):
        """
        Parses mixed Excel/date-time values.

        Handles:
            - pandas/Excel date-time objects
            - dd-mm-yyyy HH:MM:SS
            - dd/mm/yyyy HH:MM:SS
            - yyyy-mm-dd HH:MM:SS
            - Excel serial date numbers
        """
        source = series.copy()

        # First attempt normal mixed-format conversion.
        try:
            parsed = pd.to_datetime(
                source,
                errors="coerce",
                dayfirst=True,
                format="mixed",
            )
        except TypeError:
            # Compatible with older pandas versions.
            parsed = pd.to_datetime(
                source,
                errors="coerce",
                dayfirst=True,
            )

        # ``dayfirst=True`` is required for common Indian report formats such
        # as 31-01-2026, but pandas can then misread ISO values (2026-01-10)
        # as 1 October. Reparse explicit year-first strings without day-first.
        text_values = source.astype("string").str.strip()
        iso_date_mask = text_values.str.match(
            r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}",
            na=False,
        )

        if iso_date_mask.any():
            try:
                parsed.loc[iso_date_mask] = pd.to_datetime(
                    source.loc[iso_date_mask],
                    errors="coerce",
                    dayfirst=False,
                    format="mixed",
                )
            except TypeError:
                parsed.loc[iso_date_mask] = pd.to_datetime(
                    source.loc[iso_date_mask],
                    errors="coerce",
                    dayfirst=False,
                )

        # Handle numeric Excel serial date/time values not parsed correctly.
        numeric_values = pd.to_numeric(source, errors="coerce")

        excel_serial_mask = (
                parsed.isna()
                & numeric_values.notna()
                & numeric_values.between(1, 100000)
        )

        if excel_serial_mask.any():
            parsed.loc[excel_serial_mask] = pd.to_datetime(
                numeric_values.loc[excel_serial_mask],
                unit="D",
                origin="1899-12-30",
                errors="coerce",
            )

        return parsed

    def detect_event_type(description):
        """
        Classifies only Last Gasp and First Breath events.

        Supports:
            Last Gasp
            LastGasp
            LAST_GASP
            First Breath
            FirstBreath
            FIRST_BREATH
        """
        if pd.isna(description):
            return pd.NA

        normalized_description = normalize_column_name(description)

        if "lastgasp" in normalized_description:
            return "Last Gasp"

        if "firstbreath" in normalized_description:
            return "First Breath"

        return pd.NA

    def format_columns_for_display(dataframe):
        """
        Returns a display copy with readable date/time and delay values.
        """
        display_dataframe = dataframe.copy()

        datetime_columns = [
            "Meter Date & Time",
            "HES Received Time",
            "Last Gasp Meter Time",
            "Last Gasp HES Time",
            "First Breath Meter Time",
            "First Breath HES Time",
        ]

        for column in datetime_columns:
            if column in display_dataframe.columns:
                display_dataframe[column] = display_dataframe[column].apply(
                    lambda value: (
                        value.strftime("%d-%m-%Y %H:%M:%S")
                        if pd.notna(value)
                        else ""
                    )
                )

        delay_columns = [
            column
            for column in display_dataframe.columns
            if "Delay (Minutes)" in str(column)
        ]

        for column in delay_columns:
            display_dataframe[column] = pd.to_numeric(
                display_dataframe[column],
                errors="coerce",
            ).round(2)

        return display_dataframe

    def create_excel_output(
            executive_summary_dataframe,
            summary_dataframe,
            unique_events_dataframe,
            received_last_gasp_dataframe,
            received_first_breath_dataframe,
            missing_last_gasp_dataframe,
            missing_first_breath_dataframe,
            duplicate_details_dataframe,
            rejected_rows_dataframe,
    ):
        """
        Creates a multi-sheet Excel validation report in memory.
        """
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            executive_summary_dataframe.to_excel(
                writer,
                sheet_name="Executive Summary",
                index=False,
            )

            format_columns_for_display(summary_dataframe).to_excel(
                writer,
                sheet_name="Meter Summary",
                index=False,
            )

            format_columns_for_display(unique_events_dataframe).to_excel(
                writer,
                sheet_name="Unique Events",
                index=False,
            )

            format_columns_for_display(
                received_last_gasp_dataframe
            ).to_excel(
                writer,
                sheet_name="Last Gasp Received",
                index=False,
            )

            format_columns_for_display(
                received_first_breath_dataframe
            ).to_excel(
                writer,
                sheet_name="First Breath Received",
                index=False,
            )

            format_columns_for_display(
                missing_last_gasp_dataframe
            ).to_excel(
                writer,
                sheet_name="Last Gasp Missing",
                index=False,
            )

            format_columns_for_display(
                missing_first_breath_dataframe
            ).to_excel(
                writer,
                sheet_name="First Breath Missing",
                index=False,
            )

            format_columns_for_display(
                duplicate_details_dataframe
            ).to_excel(
                writer,
                sheet_name="Duplicate Details",
                index=False,
            )

            format_columns_for_display(
                rejected_rows_dataframe
            ).to_excel(
                writer,
                sheet_name="Rejected Rows",
                index=False,
            )

            workbook = writer.book

            for worksheet in workbook.worksheets:
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions

                for column_cells in worksheet.columns:
                    maximum_length = 0
                    column_letter = column_cells[0].column_letter

                    for cell in column_cells:
                        if cell.value is not None:
                            maximum_length = max(
                                maximum_length,
                                len(str(cell.value)),
                            )

                    worksheet.column_dimensions[column_letter].width = min(
                        maximum_length + 2,
                        45,
                    )

        output.seek(0)
        return output.getvalue()

    # ================================================================
    # STREAMLIT UI
    # ================================================================

    st.subheader("Last Gasp and First Breath Validation")

    st.caption(
        "Upload the meter list and ESWF event report. "
        "The dashboard counts one Last Gasp and one First Breath per meter, "
        "irrespective of duplicate alerts. SLA Pass requires "
        "HES Received Time minus Meter Date & Time to be less than 3 minutes."
    )

    upload_column_1, upload_column_2 = st.columns(2)

    with upload_column_1:
        meter_file = st.file_uploader(
            "1. Upload Meter List",
            type=["xlsx", "xls", "xlsm", "csv"],
            key="lastgasp_meter_master_upload",
            help=(
                "The file must contain a meter-number column such as "
                "Meter Sr. No, Target Meter List, Meter ID, Device ID, "
                "Serial Number, or Meter No."
            ),
        )

    with upload_column_2:
        event_file = st.file_uploader(
            "2. Upload Last Gasp / First Breath ESWF Report",
            type=["xlsx", "xls", "xlsm", "csv"],
            key="lastgasp_eswf_event_upload",
            help=(
                "The event file must contain meter number, Description, "
                "Meter Date & Time, and HES Received Time."
            ),
        )

    if meter_file is None or event_file is None:
        st.info(
            "Upload both input files to start the Last Gasp and "
            "First Breath validation."
        )
        return None

    try:
        # ============================================================
        # COLUMN ALIASES
        # ============================================================

        meter_aliases = [
            "Meter Sr. No",
            "Meter Sr No",
            "Meter Serial Number",
            "Meter Serial No",
            "Meter Number",
            "Meter No",
            "Meter ID",
            "Device ID",
            "Serial Number",
            "Serial No",
            "Target Meter List",
            "Target Meter",
            "Target Meter Number",
            "Target Meter ID",
            "Meter",
        ]

        description_aliases = [
            "Description",
            "Event Description",
            "ESWF Events",
            "ESWF Event",
            "Event Name",
            "Event",
            "Alert Description",
        ]

        meter_datetime_aliases = [
            "Meter Date & Time",
            "Meter Date and Time",
            "Meter Date Time",
            "Event Date & Time",
            "Event Date and Time",
            "Event Date Time",
            "Meter Time",
            "Event Time",
            "RTC",
        ]

        hes_datetime_aliases = [
            "HES Received Time",
            "HES Receive Time",
            "HES Received Date & Time",
            "HES Received Date and Time",
            "Received Time",
            "Received Date & Time",
            "Server Received Time",
            "HES Time",
        ]

        # ============================================================
        # READ INPUT FILES
        # ============================================================

        meter_dataframe, meter_sheet, meter_header_row = detect_header_row(
            meter_file,
            required_alias_groups=[meter_aliases],
        )

        event_dataframe, event_sheet, event_header_row = detect_header_row(
            event_file,
            required_alias_groups=[
                meter_aliases,
                description_aliases,
                meter_datetime_aliases,
                hes_datetime_aliases,
            ],
        )

        meter_dataframe.columns = [
            str(column).strip()
            for column in meter_dataframe.columns
        ]

        event_dataframe.columns = [
            str(column).strip()
            for column in event_dataframe.columns
        ]

        # ============================================================
        # FIND REQUIRED COLUMNS
        # ============================================================

        meter_master_column = find_column(
            meter_dataframe,
            meter_aliases,
        )

        event_meter_column = find_column(
            event_dataframe,
            meter_aliases,
        )

        description_column = find_column(
            event_dataframe,
            description_aliases,
        )

        meter_datetime_column = find_column(
            event_dataframe,
            meter_datetime_aliases,
        )

        hes_datetime_column = find_column(
            event_dataframe,
            hes_datetime_aliases,
        )

        # ============================================================
        # PREPARE METER MASTER
        # ============================================================

        meter_master = pd.DataFrame(
            {
                "Meter Number": meter_dataframe[
                    meter_master_column
                ].map(normalize_meter_number)
            }
        )

        meter_master = (
            meter_master
            .dropna(subset=["Meter Number"])
            .drop_duplicates(subset=["Meter Number"], keep="first")
            .reset_index(drop=True)
        )

        if meter_master.empty:
            raise ValueError(
                "The uploaded meter list does not contain any valid meter numbers."
            )

        target_meter_set = set(meter_master["Meter Number"])

        # ============================================================
        # PREPARE EVENT DATA
        # ============================================================

        event_working = event_dataframe.copy()

        event_working["Source Row"] = np.arange(
            2 + event_header_row,
            2 + event_header_row + len(event_working),
        )

        event_working["Meter Number"] = event_working[
            event_meter_column
        ].map(normalize_meter_number)

        event_working["Description"] = event_working[
            description_column
        ].astype("string").str.strip()

        event_working["Event Type"] = event_working[
            "Description"
        ].map(detect_event_type)

        event_working["Meter Date & Time"] = parse_datetime_series(
            event_working[meter_datetime_column]
        )

        event_working["HES Received Time"] = parse_datetime_series(
            event_working[hes_datetime_column]
        )

        # Keep a copy of rejected rows for traceability.
        relevant_description_mask = event_working["Event Type"].notna()
        target_meter_mask = event_working["Meter Number"].isin(
            target_meter_set
        )

        rejected_rows = event_working[
            relevant_description_mask & ~target_meter_mask
            ].copy()

        if not rejected_rows.empty:
            rejected_rows["Rejection Reason"] = (
                "Meter not found in uploaded meter list"
            )

        # Only target-meter Last Gasp and First Breath rows.
        matched_events = event_working[
            relevant_description_mask & target_meter_mask
            ].copy()

        matched_events["Timestamp Status"] = np.select(
            [
                matched_events["Meter Date & Time"].isna()
                & matched_events["HES Received Time"].isna(),

                matched_events["Meter Date & Time"].isna(),

                matched_events["HES Received Time"].isna(),
            ],
            [
                "Both timestamps invalid/missing",
                "Meter timestamp invalid/missing",
                "HES timestamp invalid/missing",
            ],
            default="Valid",
        )

        matched_events["Delay (Seconds)"] = (
                matched_events["HES Received Time"]
                - matched_events["Meter Date & Time"]
        ).dt.total_seconds()

        matched_events["Delay (Minutes)"] = (
                matched_events["Delay (Seconds)"] / 60
        )

        # Strict requirement:
        # HES Received Time - Meter Date & Time must be >= 0 and < 3 min.
        matched_events["SLA Status"] = np.select(
            [
                matched_events["Timestamp Status"] != "Valid",
                matched_events["Delay (Seconds)"] < 0,
                (
                        matched_events["Delay (Seconds)"] >= 0
                )
                & (
                        matched_events["Delay (Seconds)"] < 180
                ),
            ],
            [
                "Invalid Timestamp",
                "Negative Delay",
                "Pass",
            ],
            default="Fail",
        )

        matched_events["Raw Event Count"] = matched_events.groupby(
            ["Meter Number", "Event Type"]
        )["Event Type"].transform("size")

        matched_events["Duplicate Alert Count"] = (
                matched_events["Raw Event Count"] - 1
        )

        # ============================================================
        # DUPLICATE HANDLING
        # ============================================================
        #
        # Count rule:
        # One meter contributes only one received record per event type.
        #
        # Selection rule:
        # If duplicates exist, retain the earliest event using:
        #   1. Meter Date & Time
        #   2. HES Received Time
        #   3. Original source row
        #
        # All duplicate rows remain available in Duplicate Details.
        # ============================================================

        matched_events["_MeterSortTime"] = matched_events[
            "Meter Date & Time"
        ].fillna(pd.Timestamp.max)

        matched_events["_HesSortTime"] = matched_events[
            "HES Received Time"
        ].fillna(pd.Timestamp.max)

        matched_events = matched_events.sort_values(
            by=[
                "Meter Number",
                "Event Type",
                "_MeterSortTime",
                "_HesSortTime",
                "Source Row",
            ],
            ascending=True,
            kind="stable",
        )

        matched_events["Occurrence Number"] = (
                matched_events.groupby(
                    ["Meter Number", "Event Type"]
                ).cumcount()
                + 1
        )

        matched_events["Record Classification"] = np.where(
            matched_events["Occurrence Number"] == 1,
            "Counted Record",
            "Duplicate Alert",
        )

        duplicate_details = matched_events[
            matched_events["Occurrence Number"] > 1
            ].copy()

        unique_events = matched_events[
            matched_events["Occurrence Number"] == 1
            ].copy()

        columns_to_remove = [
            "_MeterSortTime",
            "_HesSortTime",
        ]

        matched_events = matched_events.drop(
            columns=columns_to_remove,
            errors="ignore",
        )

        unique_events = unique_events.drop(
            columns=columns_to_remove,
            errors="ignore",
        )

        duplicate_details = duplicate_details.drop(
            columns=columns_to_remove,
            errors="ignore",
        )

        # ============================================================
        # CREATE EVENT-SPECIFIC TABLES
        # ============================================================

        last_gasp_received = unique_events[
            unique_events["Event Type"] == "Last Gasp"
            ].copy()

        first_breath_received = unique_events[
            unique_events["Event Type"] == "First Breath"
            ].copy()

        last_gasp_meter_set = set(
            last_gasp_received["Meter Number"]
        )

        first_breath_meter_set = set(
            first_breath_received["Meter Number"]
        )

        missing_last_gasp = meter_master[
            ~meter_master["Meter Number"].isin(last_gasp_meter_set)
        ].copy()

        missing_last_gasp["Event Type"] = "Last Gasp"
        missing_last_gasp["Status"] = "Not Received"

        missing_first_breath = meter_master[
            ~meter_master["Meter Number"].isin(first_breath_meter_set)
        ].copy()

        missing_first_breath["Event Type"] = "First Breath"
        missing_first_breath["Status"] = "Not Received"

        # ============================================================
        # CREATE ONE-ROW-PER-METER SUMMARY
        # ============================================================

        summary = meter_master.copy()

        last_gasp_summary = last_gasp_received[
            [
                "Meter Number",
                "Meter Date & Time",
                "HES Received Time",
                "Delay (Minutes)",
                "SLA Status",
                "Raw Event Count",
                "Duplicate Alert Count",
            ]
        ].rename(
            columns={
                "Meter Date & Time": "Last Gasp Meter Time",
                "HES Received Time": "Last Gasp HES Time",
                "Delay (Minutes)": "Last Gasp Delay (Minutes)",
                "SLA Status": "Last Gasp SLA",
                "Raw Event Count": "Last Gasp Raw Count",
                "Duplicate Alert Count": "Last Gasp Duplicate Count",
            }
        )

        first_breath_summary = first_breath_received[
            [
                "Meter Number",
                "Meter Date & Time",
                "HES Received Time",
                "Delay (Minutes)",
                "SLA Status",
                "Raw Event Count",
                "Duplicate Alert Count",
            ]
        ].rename(
            columns={
                "Meter Date & Time": "First Breath Meter Time",
                "HES Received Time": "First Breath HES Time",
                "Delay (Minutes)": "First Breath Delay (Minutes)",
                "SLA Status": "First Breath SLA",
                "Raw Event Count": "First Breath Raw Count",
                "Duplicate Alert Count": "First Breath Duplicate Count",
            }
        )

        summary = summary.merge(
            last_gasp_summary,
            on="Meter Number",
            how="left",
            validate="one_to_one",
        )

        summary = summary.merge(
            first_breath_summary,
            on="Meter Number",
            how="left",
            validate="one_to_one",
        )

        summary["Last Gasp Received Count"] = (
            summary["Meter Number"]
            .isin(last_gasp_meter_set)
            .astype(int)
        )

        summary["First Breath Received Count"] = (
            summary["Meter Number"]
            .isin(first_breath_meter_set)
            .astype(int)
        )

        summary["Last Gasp Status"] = np.where(
            summary["Last Gasp Received Count"].eq(1),
            "Received",
            "Not Received",
        )

        summary["First Breath Status"] = np.where(
            summary["First Breath Received Count"].eq(1),
            "Received",
            "Not Received",
        )

        summary["Pair Status"] = np.select(
            [
                (
                        summary["Last Gasp Received Count"].eq(1)
                        & summary["First Breath Received Count"].eq(1)
                ),
                (
                        summary["Last Gasp Received Count"].eq(1)
                        & summary["First Breath Received Count"].eq(0)
                ),
                (
                        summary["Last Gasp Received Count"].eq(0)
                        & summary["First Breath Received Count"].eq(1)
                ),
            ],
            [
                "Complete Pair",
                "Last Gasp Only",
                "First Breath Only",
            ],
            default="Both Missing",
        )

        summary["Overall Validation"] = np.select(
            [
                (
                        summary["Last Gasp Received Count"].eq(1)
                        & summary["First Breath Received Count"].eq(1)
                        & summary["Last Gasp SLA"].eq("Pass")
                        & summary["First Breath SLA"].eq("Pass")
                ),
                (
                        summary["Last Gasp Received Count"].eq(0)
                        | summary["First Breath Received Count"].eq(0)
                ),
            ],
            [
                "Pass",
                "Fail - Missing Event",
            ],
            default="Fail - SLA/Timestamp",
        )

        summary["Stakeholder Action"] = np.select(
            [
                summary["Overall Validation"].eq("Pass"),
                summary["Overall Validation"].eq("Fail - Missing Event"),
            ],
            ["No action required", "Investigate missing event"],
            default="Review SLA or timestamp",
        )

        # Arrange summary columns in operational order.
        summary_columns = [
            "Meter Number",
            "Last Gasp Status",
            "Last Gasp Received Count",
            "Last Gasp Meter Time",
            "Last Gasp HES Time",
            "Last Gasp Delay (Minutes)",
            "Last Gasp SLA",
            "Last Gasp Raw Count",
            "Last Gasp Duplicate Count",
            "First Breath Status",
            "First Breath Received Count",
            "First Breath Meter Time",
            "First Breath HES Time",
            "First Breath Delay (Minutes)",
            "First Breath SLA",
            "First Breath Raw Count",
            "First Breath Duplicate Count",
            "Pair Status",
            "Overall Validation",
            "Stakeholder Action",
        ]

        summary = summary.reindex(columns=summary_columns)

        count_columns = [
            "Last Gasp Received Count",
            "Last Gasp Raw Count",
            "Last Gasp Duplicate Count",
            "First Breath Received Count",
            "First Breath Raw Count",
            "First Breath Duplicate Count",
        ]

        for column in count_columns:
            summary[column] = (
                pd.to_numeric(summary[column], errors="coerce")
                .fillna(0)
                .astype(int)
            )

        # ============================================================
        # KPI CALCULATIONS
        # ============================================================

        total_target_meters = len(meter_master)

        last_gasp_received_count = len(last_gasp_meter_set)
        first_breath_received_count = len(first_breath_meter_set)

        last_gasp_missing_count = (
                total_target_meters - last_gasp_received_count
        )

        first_breath_missing_count = (
                total_target_meters - first_breath_received_count
        )

        last_gasp_sla_pass_count = int(
            last_gasp_received["SLA Status"].eq("Pass").sum()
        )

        first_breath_sla_pass_count = int(
            first_breath_received["SLA Status"].eq("Pass").sum()
        )

        complete_pair_count = int(
            summary["Pair Status"].eq("Complete Pair").sum()
        )

        fully_passed_meter_count = int(
            summary["Overall Validation"].eq("Pass").sum()
        )

        duplicate_row_count = len(duplicate_details)
        invalid_timestamp_count = int(
            matched_events["Timestamp Status"].ne("Valid").sum()
        )
        action_required_count = total_target_meters - fully_passed_meter_count

        def percentage(numerator, denominator):
            """Return a safe, display-ready percentage."""
            return 0.0 if denominator == 0 else numerator / denominator * 100

        executive_summary = pd.DataFrame(
            [
                {
                    "Measure": "Target meters",
                    "Value": total_target_meters,
                    "Interpretation": "Meters included in this validation scope",
                },
                {
                    "Measure": "Fully compliant meters",
                    "Value": fully_passed_meter_count,
                    "Interpretation": (
                        f"{percentage(fully_passed_meter_count, total_target_meters):.1f}% "
                        "have both events within the 3-minute SLA"
                    ),
                },
                {
                    "Measure": "Meters needing attention",
                    "Value": action_required_count,
                    "Interpretation": "Missing event, SLA failure, or invalid timestamp",
                },
                {
                    "Measure": "Last Gasp coverage",
                    "Value": f"{percentage(last_gasp_received_count, total_target_meters):.1f}%",
                    "Interpretation": (
                        f"{last_gasp_received_count:,} of {total_target_meters:,} target meters"
                    ),
                },
                {
                    "Measure": "First Breath coverage",
                    "Value": f"{percentage(first_breath_received_count, total_target_meters):.1f}%",
                    "Interpretation": (
                        f"{first_breath_received_count:,} of {total_target_meters:,} target meters"
                    ),
                },
                {
                    "Measure": "Data-quality records excluded",
                    "Value": duplicate_row_count + len(rejected_rows),
                    "Interpretation": (
                        f"{duplicate_row_count:,} duplicate alerts and "
                        f"{len(rejected_rows):,} out-of-scope meter records"
                    ),
                },
            ]
        )

        # ============================================================
        # FILE INFORMATION
        # ============================================================

        with st.expander("Detected Input Structure", expanded=False):
            input_info = pd.DataFrame(
                [
                    {
                        "Input": "Meter List",
                        "File": meter_file.name,
                        "Sheet": meter_sheet,
                        "Header Row": meter_header_row + 1,
                        "Detected Meter Column": meter_master_column,
                    },
                    {
                        "Input": "ESWF Events",
                        "File": event_file.name,
                        "Sheet": event_sheet,
                        "Header Row": event_header_row + 1,
                        "Detected Meter Column": event_meter_column,
                        "Description Column": description_column,
                        "Meter Time Column": meter_datetime_column,
                        "HES Time Column": hes_datetime_column,
                    },
                ]
            )

            st.dataframe(
                input_info,
                use_container_width=True,
                hide_index=True,
            )

        # ============================================================
        # DASHBOARD KPIs
        # ============================================================

        alert_reception_rate = percentage(
            complete_pair_count,
            total_target_meters,
        )
        last_gasp_sla_rate = percentage(
            last_gasp_sla_pass_count,
            last_gasp_received_count,
        )
        first_breath_sla_rate = percentage(
            first_breath_sla_pass_count,
            first_breath_received_count,
        )
        complete_sla_rate = percentage(
            fully_passed_meter_count,
            complete_pair_count,
        )

        st.markdown("### Decision Dashboard")

        count_scorecard = pd.DataFrame(
            [
                {
                    "KPI view": "Alert reception",
                    "Target": total_target_meters,
                    "Last Gasp": last_gasp_received_count,
                    "First Breath": first_breath_received_count,
                    "Both alerts / compliant": complete_pair_count,
                    "Attention needed": total_target_meters - complete_pair_count,
                },
                {
                    "KPI view": "SLA outcome",
                    "Target": total_target_meters,
                    "Last Gasp": last_gasp_sla_pass_count,
                    "First Breath": first_breath_sla_pass_count,
                    "Both alerts / compliant": fully_passed_meter_count,
                    "Attention needed": action_required_count,
                },
            ]
        )
        st.markdown("#### Count scorecard")
        st.dataframe(
            count_scorecard,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### KPI 1 — Alert reception (unique meters)")
        reception_kpis = st.columns(4)
        reception_kpis[0].metric("Target meters", f"{total_target_meters:,}")
        reception_kpis[1].metric(
            "Last Gasp received",
            f"{last_gasp_received_count:,}",
            delta=f"{percentage(last_gasp_received_count, total_target_meters):.1f}% coverage",
        )
        reception_kpis[2].metric(
            "First Breath received",
            f"{first_breath_received_count:,}",
            delta=f"{percentage(first_breath_received_count, total_target_meters):.1f}% coverage",
        )
        reception_kpis[3].metric(
            "Both alerts received",
            f"{complete_pair_count:,}",
            delta=f"{alert_reception_rate:.1f}% coverage",
        )
        st.progress(
            int(round(alert_reception_rate)),
            text=(
                f"{alert_reception_rate:.1f}% of target meters received both "
                "unique alerts (duplicates excluded)."
            ),
        )
        reception_detail_kpis = st.columns(3)
        reception_detail_kpis[0].metric("Last Gasp missing", f"{last_gasp_missing_count:,}")
        reception_detail_kpis[1].metric("First Breath missing", f"{first_breath_missing_count:,}")
        reception_detail_kpis[2].metric("Duplicates excluded", f"{duplicate_row_count:,}")

        st.markdown("#### KPI 2 — SLA performance (received unique alerts)")
        sla_kpis = st.columns(4)
        sla_kpis[0].metric(
            "Last Gasp within SLA",
            f"{last_gasp_sla_pass_count:,} / {last_gasp_received_count:,}",
            delta=f"{last_gasp_sla_rate:.1f}% within 3 minutes",
        )
        sla_kpis[1].metric(
            "First Breath within SLA",
            f"{first_breath_sla_pass_count:,} / {first_breath_received_count:,}",
            delta=f"{first_breath_sla_rate:.1f}% within 3 minutes",
        )
        sla_kpis[2].metric(
            "Fully compliant meters",
            f"{fully_passed_meter_count:,} / {total_target_meters:,}",
            delta=f"{percentage(fully_passed_meter_count, total_target_meters):.1f}% of target",
        )
        sla_kpis[3].metric(
            "Action required",
            f"{action_required_count:,}",
            delta="Missing event or SLA issue",
            delta_color="inverse",
        )
        sla_progress_1, sla_progress_2 = st.columns(2)
        with sla_progress_1:
            st.progress(
                int(round(last_gasp_sla_rate)),
                text=f"Last Gasp SLA: {last_gasp_sla_rate:.1f}%",
            )
        with sla_progress_2:
            st.progress(
                int(round(first_breath_sla_rate)),
                text=f"First Breath SLA: {first_breath_sla_rate:.1f}%",
            )

        if action_required_count:
            st.warning(
                f"Decision: prioritise {action_required_count:,} meter(s) needing "
                f"attention. Of meters with both alerts, {complete_sla_rate:.1f}% "
                "meet the full SLA. Open ‘Meter Summary’ for the action list."
            )
        else:
            st.success("Decision: no immediate action is required; all target meters meet the full SLA.")

        # ============================================================
        # DASHBOARD TABS
        # ============================================================

        (
            summary_tab,
            last_gasp_tab,
            first_breath_tab,
            missing_tab,
            duplicate_tab,
            rejected_tab,
        ) = st.tabs(
            [
                "Meter Summary",
                "Last Gasp",
                "First Breath",
                "Missing Events",
                "Duplicate Alerts",
                "Excluded Rows",
            ]
        )

        with summary_tab:
            st.markdown("#### Action list")

            review_view = st.radio(
                "Review",
                options=["Action required", "All target meters"],
                horizontal=True,
                key="lgfb_summary_review_view",
            )

            displayed_summary = summary.copy()
            if review_view == "Action required":
                displayed_summary = displayed_summary[
                    displayed_summary["Overall Validation"].ne("Pass")
                ]

            action_columns = [
                "Meter Number",
                "Stakeholder Action",
                "Overall Validation",
                "Pair Status",
                "Last Gasp SLA",
                "Last Gasp Delay (Minutes)",
                "First Breath SLA",
                "First Breath Delay (Minutes)",
                "Last Gasp Duplicate Count",
                "First Breath Duplicate Count",
            ]

            st.caption(
                "Use Stakeholder Action to prioritise follow-up. The downloaded "
                "workbook opens with the Executive Summary."
            )

            st.dataframe(
                format_columns_for_display(
                    displayed_summary.reindex(columns=action_columns)
                ),
                use_container_width=True,
                hide_index=True,
            )

        with last_gasp_tab:
            st.markdown(
                "#### Unique Last Gasp Records Used for Counting"
            )

            last_gasp_display_columns = [
                "Meter Number",
                "Meter Date & Time",
                "HES Received Time",
                "Delay (Minutes)",
                "SLA Status",
                "Raw Event Count",
                "Duplicate Alert Count",
                "Description",
                "Source Row",
            ]

            st.dataframe(
                format_columns_for_display(
                    last_gasp_received.reindex(
                        columns=last_gasp_display_columns
                    )
                ),
                use_container_width=True,
                hide_index=True,
            )

        with first_breath_tab:
            st.markdown(
                "#### Unique First Breath Records Used for Counting"
            )

            first_breath_display_columns = [
                "Meter Number",
                "Meter Date & Time",
                "HES Received Time",
                "Delay (Minutes)",
                "SLA Status",
                "Raw Event Count",
                "Duplicate Alert Count",
                "Description",
                "Source Row",
            ]

            st.dataframe(
                format_columns_for_display(
                    first_breath_received.reindex(
                        columns=first_breath_display_columns
                    )
                ),
                use_container_width=True,
                hide_index=True,
            )

        with missing_tab:
            missing_column_1, missing_column_2 = st.columns(2)

            with missing_column_1:
                st.markdown(
                    f"#### Last Gasp Missing: {len(missing_last_gasp):,}"
                )

                st.dataframe(
                    missing_last_gasp,
                    use_container_width=True,
                    hide_index=True,
                )

            with missing_column_2:
                st.markdown(
                    f"#### First Breath Missing: "
                    f"{len(missing_first_breath):,}"
                )

                st.dataframe(
                    missing_first_breath,
                    use_container_width=True,
                    hide_index=True,
                )

        with duplicate_tab:
            st.markdown(
                "#### Duplicate Alert Rows Excluded from Received Counts"
            )

            if duplicate_details.empty:
                st.success("No duplicate Last Gasp or First Breath rows found.")
            else:
                duplicate_display_columns = [
                    "Meter Number",
                    "Event Type",
                    "Meter Date & Time",
                    "HES Received Time",
                    "Delay (Minutes)",
                    "SLA Status",
                    "Description",
                    "Occurrence Number",
                    "Record Classification",
                    "Source Row",
                ]

                st.warning(
                    f"{len(duplicate_details):,} duplicate event rows were "
                    "excluded from the received counts."
                )

                st.dataframe(
                    format_columns_for_display(
                        duplicate_details.reindex(
                            columns=duplicate_display_columns
                        )
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        with rejected_tab:
            st.markdown(
                "#### Event Rows Excluded Because Meter Is Not in Meter List"
            )

            if rejected_rows.empty:
                st.success(
                    "No Last Gasp or First Breath rows were excluded."
                )
            else:
                rejected_display_columns = [
                    "Meter Number",
                    "Event Type",
                    "Meter Date & Time",
                    "HES Received Time",
                    "Description",
                    "Rejection Reason",
                    "Source Row",
                ]

                st.dataframe(
                    format_columns_for_display(
                        rejected_rows.reindex(
                            columns=rejected_display_columns
                        )
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        # ============================================================
        # EXCEL DOWNLOAD
        # ============================================================

        export_bytes = create_excel_output(
            executive_summary_dataframe=executive_summary,
            summary_dataframe=summary,
            unique_events_dataframe=unique_events,
            received_last_gasp_dataframe=last_gasp_received,
            received_first_breath_dataframe=first_breath_received,
            missing_last_gasp_dataframe=missing_last_gasp,
            missing_first_breath_dataframe=missing_first_breath,
            duplicate_details_dataframe=duplicate_details,
            rejected_rows_dataframe=rejected_rows,
        )

        st.download_button(
            label="Download Last Gasp and First Breath Validation Report",
            data=export_bytes,
            file_name="Last_Gasp_First_Breath_Validation.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

        # Return the calculated DataFrames so the function can be
        # integrated with other application modules.
        return {
            "meter_master": meter_master,
            "matched_event_rows": matched_events,
            "unique_events": unique_events,
            "last_gasp_received": last_gasp_received,
            "first_breath_received": first_breath_received,
            "missing_last_gasp": missing_last_gasp,
            "missing_first_breath": missing_first_breath,
            "duplicate_details": duplicate_details,
            "rejected_rows": rejected_rows,
            "summary": summary,
            "executive_summary": executive_summary,
            "kpis": {
                "target_meters": total_target_meters,
                "last_gasp_received": last_gasp_received_count,
                "first_breath_received": first_breath_received_count,
                "last_gasp_missing": last_gasp_missing_count,
                "first_breath_missing": first_breath_missing_count,
                "last_gasp_sla_pass": last_gasp_sla_pass_count,
                "first_breath_sla_pass": first_breath_sla_pass_count,
                "complete_pairs": complete_pair_count,
                "fully_passed_meters": fully_passed_meter_count,
                "duplicate_rows_ignored": duplicate_row_count,
                "invalid_timestamp_rows": invalid_timestamp_count,
                "action_required_meters": action_required_count,
            },
        }

    except Exception as error:
        st.error("Unable to complete Last Gasp / First Breath validation.")
        st.warning(
            "Check that both files contain the required columns and valid "
            "date/time values, then try again."
        )
        with st.expander("Technical details", expanded=False):
            st.exception(error)
        return None


if __name__ == "__main__":
    st.set_page_config(
        page_title="Last Gasp & First Breath Validation",
        page_icon="⚡",
        layout="wide",
    )
    st.title("Last Gasp & First Breath Validation")
    st.caption(
        "Upload the meter list and HES event report to review event coverage, "
        "SLA compliance, and required actions."
    )
    run()
