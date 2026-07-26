"""pages/reports.py — Reports"""

import streamlit as st
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import backend as bk


def _build_excel(metrics, decision, hist: pd.DataFrame) -> bytes:
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Summary sheet
        summary = pd.DataFrame({
            "Metric": ["Timestamp", "Energy (kWh)", "Demand (kW)", "Cooling (kWh)",
                       "Heating (kWh)", "Indoor Temp", "Outdoor Temp", "Humidity",
                       "PMV", "Occupancy", "Lighting (kW)"],
            "Value": [metrics.timestamp, metrics.energy_kwh, metrics.demand_kw,
                      metrics.cooling_kwh, metrics.heating_kwh, metrics.indoor_temperature,
                      metrics.outdoor_temperature, metrics.humidity, metrics.pmv,
                      metrics.occupancy, metrics.lighting_kw],
        })
        summary.to_excel(writer, sheet_name="Building Metrics", index=False)

        decision_df = pd.DataFrame({
            "Setting": ["Cooling Setpoint", "Heating Setpoint", "Lighting", "Fan Speed", "Reason"],
            "Value": [decision.cooling_setpoint, decision.heating_setpoint,
                      decision.lighting_level, decision.fan_speed, decision.reason],
        })
        decision_df.to_excel(writer, sheet_name="AI Decision", index=False)

        if not hist.empty:
            hist.to_excel(writer, sheet_name="Optimization History", index=False)

    return buf.getvalue()


def render():
    st.markdown("<div class='main-title'>📄 Reports</div>", unsafe_allow_html=True)
    st.caption("Download comprehensive optimization reports in multiple formats.")
    st.divider()

    with st.spinner("Preparing report data..."):
        metrics, decision, err = bk.run_optimization_pipeline()

    if metrics is None:
        st.error(f"Error: {err}")
        return

    hist = bk.get_history_df()
    summary = bk.get_history_summary()
    savings_pct = max(bk.compute_savings_pct(bk.get_energy_df()),
                      decision.expected_savings_pct)
    comfort = bk.compute_comfort_score(metrics)
    carbon = round(metrics.energy_kwh * 0.233, 2)

    # ── Executive Summary ─────────────────────────────────────────────────────
    st.subheader("📊 Executive Summary")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Energy Savings", f"{savings_pct:.1f}%")
    k2.metric("Comfort Score", f"{comfort:.0f}%")
    k3.metric("Carbon Reduction", f"{round(carbon * savings_pct / 100, 2)} kg CO₂")
    k4.metric("Optimization Cycles", str(summary.get("cycles", 0)))

    st.divider()

    # ── Report Preview ────────────────────────────────────────────────────────
    st.subheader("📋 Report Preview")
    with st.expander("📄 Building Metrics", expanded=True):
        metrics_df = pd.DataFrame({
            "Metric": ["Energy (kWh)", "Demand (kW)", "Cooling (kWh)", "Heating (kWh)",
                       "Indoor Temp (°C)", "Outdoor Temp (°C)", "Humidity (%)", "PMV",
                       "Occupancy", "Lighting (kW)"],
            "Value": [metrics.energy_kwh, metrics.demand_kw, metrics.cooling_kwh,
                      metrics.heating_kwh, metrics.indoor_temperature, metrics.outdoor_temperature,
                      metrics.humidity, metrics.pmv, metrics.occupancy, metrics.lighting_kw],
        })
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    with st.expander("🤖 AI Recommendations"):
        st.write(f"- Cooling Setpoint: **{decision.cooling_setpoint}°C**")
        st.write(f"- Heating Setpoint: **{decision.heating_setpoint}°C**")
        st.write(f"- Lighting Level: **{decision.lighting_level}%**")
        st.write(f"- Fan Speed: **{decision.fan_speed}%**")
        st.info(decision.reason)

    with st.expander("📈 Optimization History"):
        if not hist.empty:
            st.dataframe(hist, use_container_width=True, hide_index=True)
        else:
            st.info("No history yet.")

    st.divider()

    # ── Download Buttons ──────────────────────────────────────────────────────
    st.subheader("⬇ Download Reports")
    d1, d2, d3, d4 = st.columns(4)

    with d1:
        csv_data = bk.export_csv()
        st.download_button("📊 Download CSV", data=csv_data,
                           file_name="ecoloop_report.csv", mime="text/csv",
                           use_container_width=True)

    with d2:
        json_data = bk.export_json()
        st.download_button("📋 Download JSON", data=json_data,
                           file_name="ecoloop_report.json", mime="application/json",
                           use_container_width=True)

    with d3:
        try:
            excel_data = _build_excel(metrics, decision, hist)
            st.download_button("📗 Download Excel", data=excel_data,
                               file_name="ecoloop_report.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception as e:
            st.warning(f"Excel export requires openpyxl: {e}")

    with d4:
        pdf_path = bk.export_pdf(metrics, decision)
        if pdf_path and Path(pdf_path).exists():
            with open(pdf_path, "rb") as f:
                st.download_button("📕 Download PDF", data=f.read(),
                                   file_name="EcoLoop_Report.pdf", mime="application/pdf",
                                   use_container_width=True)
        else:
            st.info("PDF requires reportlab. Install with: pip install reportlab")

    st.divider()
    st.caption(f"Report generated: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
