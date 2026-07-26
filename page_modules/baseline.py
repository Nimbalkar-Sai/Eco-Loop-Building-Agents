"""pages/baseline.py — Baseline Simulation"""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("outputs")
ENERGY_FILE = OUTPUT_DIR / "energy.csv"
ERR_FILE = OUTPUT_DIR / "eplusout.err"
END_FILE = OUTPUT_DIR / "eplusout.end"


def _run_simulation():
    try:
        from simulation import Simulation
        sim = Simulation()
        return sim.run(), ""
    except Exception as e:
        return False, str(e)


def _load_results():
    if not ENERGY_FILE.exists():
        return pd.DataFrame()
    return pd.read_csv(ENERGY_FILE)


def render():
    st.markdown("<div class='main-title'>⚡ Baseline Simulation</div>", unsafe_allow_html=True)
    st.caption("Run EnergyPlus baseline simulation and extract performance metrics.")
    st.divider()

    col_run, col_status = st.columns([1, 2])

    with col_run:
        run_btn = st.button("▶ Run EnergyPlus Simulation", use_container_width=True, type="primary")

    with col_status:
        if END_FILE.exists():
            end_text = END_FILE.read_text(errors="ignore")
            if "Successfully" in end_text:
                st.success("✅ Last simulation completed successfully")
            else:
                st.warning("⚠ Last simulation may have issues")
        else:
            st.info("No simulation run yet.")

    if run_btn:
        progress = st.progress(0, text="Initializing EnergyPlus...")
        log_box = st.empty()

        progress.progress(20, text="Reading IDF file...")
        progress.progress(40, text="Loading weather data...")
        progress.progress(60, text="Running simulation...")

        start = datetime.now()
        success, err = _run_simulation()
        elapsed = (datetime.now() - start).seconds

        progress.progress(90, text="Extracting results...")

        if success:
            progress.progress(100, text="✅ Simulation complete!")
            st.success(f"Simulation finished in {elapsed}s")
        else:
            progress.progress(100, text="❌ Simulation failed")
            st.error(f"Simulation failed: {err}")

        if ERR_FILE.exists():
            with st.expander("📋 Console Output"):
                st.code(ERR_FILE.read_text(errors="ignore")[:3000], language="text")

    st.divider()
    df = _load_results()

    if df.empty:
        st.info("No simulation results yet. Run the simulation above.")
        return

    st.subheader("📊 Simulation Results")

    total_e = df["energy_kwh"].sum()
    peak_d = df["demand_kw"].max()
    total_cool = df["cooling_kwh"].sum() if "cooling_kwh" in df.columns else 0
    total_heat = df["heating_kwh"].sum() if "heating_kwh" in df.columns else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Energy", f"{total_e:.2f} kWh")
    k2.metric("Peak Demand", f"{peak_d:.2f} kW")
    k3.metric("Cooling Energy", f"{total_cool:.2f} kWh")
    k4.metric("Heating Energy", f"{total_heat:.2f} kWh")

    st.divider()
    st.subheader("📈 Energy Profile")

    fig = px.line(df, x="timestamp", y="energy_kwh", markers=True,
                  title="Hourly Energy Consumption (kWh)")
    fig.update_layout(height=350, paper_bgcolor="#161B22", plot_bgcolor="#161B22",
                      font_color="white", xaxis_title="Time", yaxis_title="kWh")
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        fig2 = px.line(df, x="timestamp", y="demand_kw", markers=True,
                       title="Peak Demand (kW)")
        fig2.update_layout(height=300, paper_bgcolor="#161B22", plot_bgcolor="#161B22",
                           font_color="white")
        st.plotly_chart(fig2, use_container_width=True)

    with c2:
        if "cooling_kwh" in df.columns and "heating_kwh" in df.columns:
            pie_df = pd.DataFrame({
                "Type": ["Cooling", "Heating", "Other"],
                "kWh": [total_cool, total_heat, max(0, total_e - total_cool - total_heat)]
            })
            fig3 = px.pie(pie_df, names="Type", values="kWh", title="Energy Breakdown")
            fig3.update_layout(height=300, paper_bgcolor="#161B22", font_color="white")
            st.plotly_chart(fig3, use_container_width=True)

    st.divider()
    st.subheader("📋 Raw Data")
    st.dataframe(df, use_container_width=True, hide_index=True)
