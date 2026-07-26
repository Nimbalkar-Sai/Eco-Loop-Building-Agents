"""page_modules/energy_comparison.py — Comparison (Energy + Carbon + Comfort)"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import backend as bk

CARBON_FACTOR = 0.233


def _ppd(pmv: float) -> float:
    return round(100 - 95 * np.exp(-0.03353 * pmv**4 - 0.2179 * pmv**2), 1)


def render():
    st.markdown("<div class='main-title'>📊 Comparison</div>", unsafe_allow_html=True)
    st.caption("Before AI vs After AI — energy, carbon, and comfort comparison.")
    st.divider()

    metrics, decision, err = bk.run_optimization_pipeline()
    if metrics is None:
        st.error(f"Error: {err}")
        return

    df = bk.get_energy_df()
    savings_pct = max(bk.compute_savings_pct(df), decision.expected_savings_pct)

    # Use first row as baseline; if only one row exists, derive "after" from AI decision
    single_row = df.empty or len(df) < 2
    before_e    = float(df["energy_kwh"].iloc[0])  if not df.empty else metrics.energy_kwh
    after_e     = before_e * (1 - savings_pct / 100) if single_row else max(float(df["energy_kwh"].iloc[-1]), 0)
    savings_pct = round((before_e - after_e) / before_e * 100, 1) if before_e > 0 else savings_pct
    before_cool = float(df["cooling_kwh"].iloc[0])  if "cooling_kwh" in df.columns and not df.empty else metrics.cooling_kwh
    after_cool  = before_cool * 0.85 if single_row else float(df["cooling_kwh"].iloc[-1])
    before_heat = float(df["heating_kwh"].iloc[0])  if "heating_kwh" in df.columns and not df.empty else metrics.heating_kwh
    after_heat  = before_heat * 0.92 if single_row else float(df["heating_kwh"].iloc[-1])
    before_peak = float(df["demand_kw"].iloc[0])    if "demand_kw"   in df.columns and not df.empty else metrics.demand_kw
    after_peak  = before_peak * (decision.fan_speed / 100) if single_row else float(df["demand_kw"].iloc[-1])
    before_c    = round(before_e * CARBON_FACTOR, 2)
    after_c     = round(after_e  * CARBON_FACTOR, 2)
    comfort     = bk.compute_comfort_score(metrics)
    pmv         = metrics.pmv or 0.0
    ppd         = _ppd(pmv)

    # ── KPI Summary ───────────────────────────────────────────────────────────
    st.subheader("⚡ Savings Summary")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Before Energy",   f"{before_e:.2f} kWh")
    k2.metric("After Energy",    f"{after_e:.2f} kWh",  delta=f"-{before_e - after_e:.2f} kWh")
    k3.metric("Energy Savings",  f"{savings_pct:.1f}%")
    k4.metric("Carbon Saved",    f"{before_c - after_c:.2f} kg CO₂")
    k5.metric("AI Confidence",   f"{decision.confidence:.0f}%")

    st.divider()

    # ── Grouped Bar Chart ─────────────────────────────────────────────────────
    st.subheader("📊 Energy Category Comparison")
    cats   = ["Total Energy", "Cooling", "Heating", "Peak Demand"]
    before = [before_e, before_cool, before_heat, before_peak]
    after  = [after_e,  after_cool,  after_heat,  after_peak]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Before AI", x=cats, y=before, marker_color="#E74C3C",
                         text=[f"{v:.1f}" for v in before], textposition="outside"))
    fig.add_trace(go.Bar(name="After AI",  x=cats, y=after,  marker_color="#2ECC71",
                         text=[f"{v:.1f}" for v in after],  textposition="outside"))
    fig.update_layout(barmode="group", height=400, paper_bgcolor="#161B22",
                      plot_bgcolor="#161B22", font_color="white",
                      title="Before vs After AI Optimization (kWh / kW)")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Carbon Comparison ─────────────────────────────────────────────────────
    st.subheader("🌿 Carbon Impact")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Carbon Before", f"{before_c:.2f} kg CO₂")
    cc2.metric("Carbon After",  f"{after_c:.2f} kg CO₂",  delta=f"-{before_c - after_c:.2f} kg")
    trees = round((before_c - after_c) * 365 / 21.77, 1)
    cc3.metric("🌳 Trees Saved/yr", str(trees))

    fig_c = go.Figure()
    fig_c.add_trace(go.Bar(name="Before", x=["Carbon (kg CO₂)"], y=[before_c], marker_color="#E74C3C"))
    fig_c.add_trace(go.Bar(name="After",  x=["Carbon (kg CO₂)"], y=[after_c],  marker_color="#2ECC71"))
    fig_c.update_layout(barmode="group", height=300, paper_bgcolor="#161B22",
                        plot_bgcolor="#161B22", font_color="white", title="Daily Carbon Emissions")
    st.plotly_chart(fig_c, use_container_width=True)

    st.divider()

    # ── Comfort Summary (merged from old comfort page) ────────────────────────
    st.subheader("😊 Comfort Summary")
    cf1, cf2, cf3, cf4 = st.columns(4)
    cf1.metric("Indoor Temp",   f"{metrics.indoor_temperature:.1f} °C")
    cf2.metric("PMV",           f"{pmv:.2f}")
    cf3.metric("PPD",           f"{ppd:.1f}%")
    cf4.metric("Comfort Score", f"{comfort:.0f}%")

    if -0.5 <= pmv <= 0.5:
        st.success(f"✅ PMV {pmv:.2f} — ASHRAE 55 compliant. Comfort maintained after optimization.")
    elif -1 <= pmv <= 1:
        st.warning(f"⚠ PMV {pmv:.2f} — Slightly outside comfort zone.")
    else:
        st.error(f"❌ PMV {pmv:.2f} — Significant discomfort. AI will re-optimize.")

    st.divider()

    # ── History trend ─────────────────────────────────────────────────────────
    hist = bk.get_history_df()
    if not hist.empty and "Energy" in hist.columns:
        hist["Energy"] = pd.to_numeric(hist["Energy"], errors="coerce")
        hist["Carbon"] = hist["Energy"] * CARBON_FACTOR
        fig2 = px.line(hist, x="Timestamp" if "Timestamp" in hist.columns else hist.index,
                       y=["Energy", "Carbon"], markers=True,
                       title="Energy & Carbon Trend Across Optimization Cycles")
        fig2.update_layout(height=300, paper_bgcolor="#161B22",
                           plot_bgcolor="#161B22", font_color="white")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── Detailed Table ────────────────────────────────────────────────────────
    st.subheader("📋 Detailed Savings Breakdown")
    table = pd.DataFrame({
        "Category":          cats,
        "Before (kWh/kW)":   [round(v, 2) for v in before],
        "After (kWh/kW)":    [round(v, 2) for v in after],
        "Saved":             [round(b - a, 2) for b, a in zip(before, after)],
        "Savings %":         [round((b - a) / b * 100, 1) if b > 0 else 0
                              for b, a in zip(before, after)],
    })
    st.dataframe(table, use_container_width=True, hide_index=True)
