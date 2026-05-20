import streamlit as st

def file_upload_widget(label="Upload file", types=["xlsx","csv","log","txt"]):
    """Generic file uploader widget."""
    return st.file_uploader(label, type=types)

def kpi_widgets(summary_counts):
    """Render KPI metrics in a row."""
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Expected", summary_counts.get("Expected Count", 0))
    col2.metric("Achieved", summary_counts.get("Achieved Count", 0))
    col3.metric("Missing", summary_counts.get("Missing Count", 0))
    col4.metric("Unexpected", summary_counts.get("Unexpected Count", 0))
    col5.metric("Achieved %", f"{summary_counts.get('Achieved %', 0)}%")

def chart_summary(status_summary):
    """Show bar and pie chart for status distribution."""
    colA, colB = st.columns(2)
    with colA:
        st.bar_chart(status_summary)
    with colB:
        st.pyplot(status_summary.plot.pie(y="Count", autopct="%1.1f%%").figure)
