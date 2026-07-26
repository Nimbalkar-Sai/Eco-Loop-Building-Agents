"""page_modules/home.py — Dashboard"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import backend as bk

CARBON_FACTOR = 0.233


def render():
    st.markdown("<div class='main-title'>🏢 EcoLoop AI — Building Dashboard</div>", unsafe_allow_html=True)
    st.caption("Honeywell Smart Building | EnergyPlus + Llama 3.2 + Streamlit")
    st.divider()

    with st.spinner("Loading building data..."):
        metrics, decision, err = bk.run_optimization_pipeline()

    if metrics is None:
        st.error(f"Pipeline error: {err}")
        return
    if err:
        st.warning(err)

    df      = bk.get_energy_df()
    hist    = bk.get_history_df()
    comfort = bk.compute_comfort_score(metrics)
    annual_e = bk.compute_daily_energy(df)          # energy.csv stores annual total
    daily_e  = round(annual_e / 365, 1)             # convert to daily average
    peak    = bk.compute_peak_demand(df)
    savings = bk.compute_savings_pct(df)
    carbon  = round(daily_e * CARBON_FACTOR, 2)
    trees   = round(carbon * 365 * savings / 100 / 21.77, 1) if savings > 0 else 0

    # ── KPI Row ───────────────────────────────────────────────────────────────
    st.subheader("📊 Key Performance Indicators")
    r1 = st.columns(4)
    r1[0].metric("⚡ Energy/Day", f"{daily_e:.1f} kWh", f"-{savings:.1f}%")
    r1[1].metric("🌿 Carbon",    f"{carbon:.1f} kg CO₂")
    r1[2].metric("🌡 Indoor",    f"{metrics.indoor_temperature:.1f} °C")
    r1[3].metric("🌤 Outdoor",   f"{metrics.outdoor_temperature:.1f} °C")
    r2 = st.columns(4)
    r2[0].metric("👥 Occupancy", str(int(metrics.occupancy)))
    r2[1].metric("😊 Comfort",   f"{comfort:.0f}%")
    r2[2].metric("🌳 Trees/yr",  str(trees))
    co2 = getattr(metrics, 'co2_ppm', None) or 0
    co2_icon = "🟢" if co2 < 800 else "🟡" if co2 < 1000 else "🔴"
    r2[3].metric(f"{co2_icon} CO₂ (IAQ)", f"{int(co2)} ppm")
    st.divider()

    # ── Gauge + AI Decision ───────────────────────────────────────────────────
    left, right = st.columns([1.3, 1])
    with left:
        st.subheader("⚡ Live Energy Gauge")
        gauge_max = max(200, round(daily_e * 1.5 / 50) * 50)
        gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=daily_e,
            number={"suffix": " kWh/day", "font": {"size": 28}},
            title={"text": "Daily Avg Energy Usage"},
            gauge={
                "axis": {"range": [0, gauge_max]},
                "bar":  {"color": "#00D4FF"},
                "steps": [
                    {"range": [0,                gauge_max * 0.4],  "color": "#2ECC71"},
                    {"range": [gauge_max * 0.4,  gauge_max * 0.75], "color": "#F1C40F"},
                    {"range": [gauge_max * 0.75, gauge_max],        "color": "#E74C3C"},
                ],
                "threshold": {"line": {"color": "red", "width": 4}, "value": gauge_max * 0.75},
            },
        ))
        gauge.update_layout(height=300, paper_bgcolor="#161B22",
                            font=dict(color="white"), margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(gauge, use_container_width=True)

    with right:
        st.subheader("🤖 Latest AI Decision")
        if decision:
            st.success(f"✅ Confidence: {decision.confidence:.0f}%")
            c1, c2 = st.columns(2)
            c1.metric("Cooling SP",  f"{decision.cooling_setpoint} °C")
            c2.metric("Heating SP",  f"{decision.heating_setpoint} °C")
            c3, c4 = st.columns(2)
            c3.metric("Lighting",    f"{decision.lighting_level}%")
            c4.metric("Fan Speed",   f"{decision.fan_speed}%")
            st.metric("Expected Savings", f"{decision.expected_savings_pct:.1f}%")
            st.info(decision.reason)
        else:
            st.warning("No AI decision yet.")
    st.divider()

    # ── Occupancy + Weather + Carbon + IAQ Context ────────────────────────────
    st.subheader("🌍 Context Awareness")
    ctx1, ctx2, ctx3, ctx4 = st.columns(4)

    with ctx1:
        occ = int(metrics.occupancy)
        if occ == 0:
            st.error(f"👥 Occupancy: **{occ}** — Building unoccupied\nEnergy saving mode active")
        elif occ < 10:
            st.warning(f"👥 Occupancy: **{occ}** — Low occupancy\nSetpoints relaxed")
        else:
            st.success(f"👥 Occupancy: **{occ}** — Normal occupancy\nComfort mode active")

    with ctx2:
        ot = metrics.outdoor_temperature
        if ot > 38:
            st.error(f"🌤 Outdoor: **{ot}°C** — Extreme heat\nHigh cooling demand")
        elif ot > 30:
            st.warning(f"🌤 Outdoor: **{ot}°C** — Hot day\nModerate cooling needed")
        elif ot < 20:
            st.info(f"🌤 Outdoor: **{ot}°C** — Cool day\nReduce cooling load")
        else:
            st.success(f"🌤 Outdoor: **{ot}°C** — Mild weather\nEnergy saving opportunity")

    with ctx3:
        ci = getattr(metrics, 'carbon_intensity', None) or CARBON_FACTOR
        if ci > 0.4:
            st.error(f"⚡ Grid Carbon: **{ci:.3f} kg/kWh** — High\nReduce HVAC load")
        elif ci > 0.25:
            st.warning(f"⚡ Grid Carbon: **{ci:.3f} kg/kWh** — Moderate")
        else:
            st.success(f"⚡ Grid Carbon: **{ci:.3f} kg/kWh** — Clean grid")

    with ctx4:
        co2v = getattr(metrics, 'co2_ppm', None) or 0
        if co2v > 1200:
            st.error(f"🌬 CO₂: **{int(co2v)} ppm** — Poor IAQ\nIncrease ventilation now")
        elif co2v > 1000:
            st.warning(f"🌬 CO₂: **{int(co2v)} ppm** — Elevated\nIncrease fan speed")
        else:
            st.success(f"🌬 CO₂: **{int(co2v)} ppm** — Good air quality")

    st.divider()

    # ── Historical Charts ─────────────────────────────────────────────────────
    if not hist.empty:
        for col in ["Energy", "IndoorTemp", "PMV", "Occupancy"]:
            if col in hist.columns:
                hist[col] = pd.to_numeric(hist[col], errors="coerce")

        st.subheader("📈 Historical Trends")
        c1, c2 = st.columns(2)
        with c1:
            fig = px.line(hist, x="Timestamp" if "Timestamp" in hist.columns else hist.index,
                          y="Energy", markers=True, title="Energy Consumption (kWh)")
            fig.update_layout(height=280, paper_bgcolor="#161B22",
                              plot_bgcolor="#161B22", font_color="white")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            if "ExpectedSavings" in hist.columns:
                hist["ExpectedSavings"] = pd.to_numeric(hist["ExpectedSavings"], errors="coerce")
                fig2 = px.bar(hist, x="Timestamp" if "Timestamp" in hist.columns else hist.index,
                              y="ExpectedSavings", title="Expected Savings per Cycle (%)",
                              color_discrete_sequence=["#2ECC71"])
                fig2.update_layout(height=280, paper_bgcolor="#161B22",
                                   plot_bgcolor="#161B22", font_color="white")
                st.plotly_chart(fig2, use_container_width=True)

        hist["Carbon"] = hist["Energy"] * CARBON_FACTOR
        fig3 = px.area(hist, x="Timestamp" if "Timestamp" in hist.columns else hist.index,
                       y="Carbon", title="Carbon Emissions Trend (kg CO₂)",
                       color_discrete_sequence=["#2ECC71"])
        fig3.update_layout(height=260, paper_bgcolor="#161B22",
                           plot_bgcolor="#161B22", font_color="white")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Run the optimization loop to see historical trends.")

    st.divider()
    st.caption(f"🕒 Last Updated: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
