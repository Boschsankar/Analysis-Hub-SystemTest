# _pages/esw_flag_control.py
import streamlit as st

def _init_state():
    if "binary_str" not in st.session_state:
        st.session_state.binary_str = ""
    if "index_direction" not in st.session_state:
        st.session_state.index_direction = "Left to Right (0-based)"

def _update_text_area(new_value: str):
    # Single source of truth for the binary payload
    st.session_state.binary_str = new_value

def run():
    _init_state()

    st.header("ESW flag : Copy the 128 bit ESW and check/modify critical bit status")
    st.subheader("📊 Bit Inspector Dashboard (0-based indexing)")

    # --- Input and controls ---
    st.markdown("Paste the binary payload below. Use the controls to inspect or modify critical bits.")
    st.selectbox(
        "Bit indexing direction",
        options=["Left to Right (0-based)", "Right to Left (0-based)"],
        index=0 if st.session_state.index_direction.startswith("Left") else 1,
        key="index_direction",
        help="Choose how bit positions are interpreted when editing."
    )

    # We read from session_state.binary_str and do not assign a conflicting 'key="binary_input"'
    raw_input = st.text_area(
        "🔢 Paste your meter payload (binary string):",
        value=st.session_state.binary_str,
        height=140,
        help="Enter only 0s and 1s. Example: 101010..."
    )

    # Clean up any accidental copy-pasted trailing spaces/newlines
    cleaned_input = raw_input.strip() if raw_input else ""

    # Sync session state if user edited the text_area directly
    if cleaned_input != st.session_state.binary_str:
        _update_text_area(cleaned_input)
        st.rerun()

    # --- Validation and basic info ---
    if st.session_state.binary_str and not all(c in "01" for c in st.session_state.binary_str):
        st.error("❌ Invalid input: Only 0s and 1s are allowed.")
        return

    if not st.session_state.binary_str:
        st.info("Paste a binary string to inspect bits.")
        return

    binary_list = list(st.session_state.binary_str)
    length = len(binary_list)
    st.markdown(f"**Binary length:** {length} bits")

    # Helper to map displayed index -> actual list index based on direction
    def to_actual_index(display_index: int) -> int:
        if st.session_state.index_direction.startswith("Left"):
            return display_index
        return length - 1 - display_index

    # --- Enabled/Disabled Lists ---
    enabled_bits = [i for i, b in enumerate(binary_list) if b == "1"]
    disabled_bits = [i for i, b in enumerate(binary_list) if b == "0"]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### ✅ Enabled Bits")
        st.write(enabled_bits)
    with col2:
        st.markdown("### ❌ Disabled Bits")
        st.write(disabled_bits)

    # --- Critical Bits (81–87) ---
    critical_bits = {
        81: "Magnet Influence",
        84: "Meter load connect/Disconnect",
        85: "Last-Gasp occurrence",
        86: "First Breath - Restoration",
        87: "MD reset"
    }

    st.markdown("### ⭐ Critical Bits (81–87)")
    summary = []
    for pos, name in critical_bits.items():
        if pos < length:
            actual_idx = to_actual_index(pos)
            state = "Enabled (1)" if binary_list[actual_idx] == "1" else "Disabled (0)"
            st.markdown(f"**Bit {pos}: {name}**")
            if binary_list[actual_idx] == "1":
                st.success(state)
            else:
                st.error(state)
            summary.append(f"{name}: {state}")
        else:
            st.warning(f"Bit {pos} not present in the provided string (length {length}).")

    # --- Stakeholder Summary ---
    st.markdown("### 📑 Stakeholder Summary")
    for line in summary:
        st.write(f"- {line}")

    # --- Quick Actions ---
    st.markdown("### ⚡ Quick Actions")
    col_a, col_b, col_c = st.columns(3)
    if col_a.button("Enable All Critical Bits", key="enable_all_critical"):
        for pos in critical_bits.keys():
            if pos < length:
                binary_list[to_actual_index(pos)] = "1"
        _update_text_area("".join(binary_list))
        st.rerun()

    if col_b.button("Disable All Critical Bits", key="disable_all_critical"):
        for pos in critical_bits.keys():
            if pos < length:
                binary_list[to_actual_index(pos)] = "0"
        _update_text_area("".join(binary_list))
        st.rerun()

    if col_c.button("Reset Critical Bits (Default Disabled)", key="reset_critical"):
        for pos in critical_bits.keys():
            if pos < length:
                binary_list[to_actual_index(pos)] = "0"
        _update_text_area("".join(binary_list))
        st.rerun()

    # --- Manual Editor ---
    st.markdown("### 🔧 Modify Bit")
    max_pos = max(0, length - 1)
    with st.form(key="manual_edit_form"):
        bit_position = st.number_input(
            "Bit position to modify (0-based, display index):",
            min_value=0,
            max_value=max_pos,
            value=0,
            step=1,
            key="manual_bit_pos"
        )
        action = st.radio("Action:", ["Enable (set to 1)", "Disable (set to 0)"], key="manual_action")
        submit = st.form_submit_button("Apply Change", use_container_width=True)
        if submit:
            actual_idx = to_actual_index(bit_position)
            if 0 <= actual_idx < length:
                binary_list[actual_idx] = "1" if action.startswith("Enable") else "0"
                _update_text_area("".join(binary_list))
                st.success("Updated binary string.")
                st.rerun()
            else:
                st.error("Position exceeds string length!")

    # --- Show current binary and provide download ---
    st.markdown("### 🔁 Current Binary")
    st.code(st.session_state.binary_str, language="text")

    st.download_button(
        label="📥 Download binary as .txt",
        data=st.session_state.binary_str.encode("utf-8"),
        file_name="esw_binary.txt",
        mime="text/plain",
        key="download_binary"
    )

if __name__ == "__main__":
    run()