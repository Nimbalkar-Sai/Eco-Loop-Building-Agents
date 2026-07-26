"""page_modules/ai_analysis.py — AI Analysis + Decision Log"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import backend as bk


def render():
    st.markdown("<div class='main-title'>🤖 AI Analysis</div>", unsafe_allow_html=True)
    st.caption("AI reasoning engine — occupancy, weather, carbon, IAQ-aware optimization with explainability.")
    st.divider()

    run_btn = st.button("🔍 Run AI Analysis Now", type="primary")
    log_box = st.empty()
    st.divider()

    logs = []

    def log(msg: str):
        logs.append(msg)
        log_box.markdown("\n\n".join(f"`{l}`" for l in logs))

    if run_btn:
        log("🚀 Starting AI analysis pipeline...")
        log("📡 Reading building sensor data...")
        with st.spinner("Running AI analysis..."):
            metrics, decision, err = bk.run_optimization_pipeline()
        log("✅ Metrics loaded from EnergyPlus")
        log("🧠 Sending data to Llama 3.2...")
        log("✅ AI decision received")
        if err:
            log(f"⚠ Warning: {err}")
    else:
        with st.spinner("Loading latest data..."):
            metrics, decision, err = bk.run_optimization_pipeline()

    if metrics is None:
        st.error(f"Could not load metrics: {err}")
        return

    ci = getattr(metrics, 'carbon_intensity', None) or 0.233
    co2 = getattr(metrics, 'co2_ppm', None) or 0

    # ── Building Conditions ───────────────────────────────────────────────────
    st.subheader("📡 Current Building Conditions")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⚡ Energy",      f"{metrics.energy_kwh:.2f} kWh")
    c2.metric("🌡 Indoor Temp", f"{metrics.indoor_temperature:.1f} °C")
    c3.metric("🌤 Outdoor",     f"{metrics.outdoor_temperature:.1f} °C")
    c4.metric("👥 Occupancy",   str(int(metrics.occupancy)))

    c5, c6, c7, c8, c9 = st.columns(5)
    c5.metric("💧 Humidity",    f"{metrics.humidity:.0f}%")
    c6.metric("😊 PMV",         f"{metrics.pmv:.2f}")
    c7.metric("💡 Lighting",    f"{metrics.lighting_kw:.1f} kW")
    c8.metric("🌿 Grid Carbon", f"{ci:.3f} kg/kWh")
    co2_icon = "🟢" if co2 < 800 else "🟡" if co2 < 1000 else "🔴"
    c9.metric(f"{co2_icon} CO₂ (IAQ)", f"{int(co2)} ppm")

    st.divider()

    # ── Detected Inefficiencies ───────────────────────────────────────────────
    st.subheader("⚠ Detected Inefficiencies")
    issues = []
    if (metrics.occupancy or 0) == 0 and metrics.energy_kwh > 5:
        issues.append(("🏢 Unoccupied Building", f"Building empty but consuming {metrics.energy_kwh:.1f} kWh", "High"))
    if (metrics.occupancy or 0) < 10 and metrics.energy_kwh > 10:
        issues.append(("👥 Low Occupancy / High Energy", f"{int(metrics.occupancy)} people, {metrics.energy_kwh:.1f} kWh", "High"))
    if metrics.indoor_temperature and metrics.indoor_temperature > 26:
        issues.append(("🔥 Overheating", f"Indoor {metrics.indoor_temperature}°C exceeds comfort range", "High"))
    if metrics.indoor_temperature and metrics.indoor_temperature < 21:
        issues.append(("🥶 Overcooling", f"Indoor {metrics.indoor_temperature}°C below comfort range", "High"))
    if metrics.pmv and metrics.pmv > 0.7:
        issues.append(("😓 Warm Discomfort", f"PMV {metrics.pmv:.2f} — occupants too warm", "Medium"))
    if metrics.pmv and metrics.pmv < -0.7:
        issues.append(("🥶 Cold Discomfort", f"PMV {metrics.pmv:.2f} — occupants too cold", "Medium"))
    if metrics.lighting_kw and metrics.lighting_kw > 6:
        issues.append(("💡 High Lighting", f"Lighting at {metrics.lighting_kw:.1f} kW — dim when unoccupied", "Medium"))
    if ci > 0.4:
        issues.append(("⚡ High Grid Carbon", f"Grid at {ci:.3f} kg/kWh — reduce HVAC load now", "Medium"))
    if co2 > 1200:
        issues.append(("🌬 Poor Indoor Air Quality", f"CO₂ at {int(co2)} ppm — ventilation required immediately", "High"))
    elif co2 > 1000:
        issues.append(("🌬 Elevated CO₂", f"CO₂ at {int(co2)} ppm — increase fan speed", "Medium"))
    if metrics.outdoor_temperature and metrics.outdoor_temperature > 38:
        issues.append(("🌡 Extreme Heat", f"Outdoor {metrics.outdoor_temperature}°C — high cooling demand", "Low"))

    if not issues:
        st.success("✅ No significant inefficiencies detected.")
    else:
        for title, desc, sev in issues:
            if sev == "High":
                st.error(f"**{title}** — {desc}")
            elif sev == "Medium":
                st.warning(f"**{title}** — {desc}")
            else:
                st.info(f"**{title}** — {desc}")

    st.divider()

    # ── AI Reasoning Chain ────────────────────────────────────────────────────
    st.subheader("🧠 AI Reasoning Chain")
    if decision:
        iaq_status = "✅ Good air quality" if co2 < 800 else ("⚠ Elevated — increase ventilation" if co2 < 1200 else "❌ Poor IAQ — ventilation critical")
        st.markdown(f"""
**Step 1 — Occupancy Check**
→ {int(metrics.occupancy)} people present {"(unoccupied — energy saving mode)" if metrics.occupancy == 0 else ""}

**Step 2 — Weather Analysis**
→ Outdoor temperature: **{metrics.outdoor_temperature}°C**
{"→ ⚠ Extreme heat — cooling demand is high" if metrics.outdoor_temperature > 38 else "→ ✅ Weather within normal range"}

**Step 3 — Comfort Assessment**
→ PMV: **{metrics.pmv:.2f}** {"✅ Within ASHRAE comfort zone" if -0.5 <= metrics.pmv <= 0.5 else "⚠ Outside comfort zone — adjustment needed"}

**Step 4 — Carbon Intensity**
→ Grid carbon: **{ci:.3f} kg/kWh** {"⚠ High — reduce load" if ci > 0.4 else "✅ Acceptable"}

**Step 5 — Indoor Air Quality (IAQ)**
→ CO₂: **{int(co2)} ppm** — {iaq_status}

**Step 6 — AI Decision**
→ Cooling: **{decision.cooling_setpoint}°C** | Heating: **{decision.heating_setpoint}°C**
→ Lighting: **{decision.lighting_level}%** | Fan: **{decision.fan_speed}%**
""")

        st.info(f"🤖 **AI Explanation:** {decision.reason}")

        st.divider()
        st.subheader("📊 Decision Confidence & Impact")
        col_conf, col_sav, col_carb = st.columns(3)

        conf_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=decision.confidence,
            title={"text": "AI Confidence"},
            number={"suffix": "%"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#00D4FF"},
                "steps": [
                    {"range": [0, 60],  "color": "#E74C3C"},
                    {"range": [60, 80], "color": "#F1C40F"},
                    {"range": [80, 100], "color": "#2ECC71"},
                ],
            },
        ))
        conf_gauge.update_layout(height=250, paper_bgcolor="#161B22",
                                 font=dict(color="white"), margin=dict(l=10, r=10, t=40, b=10))
        col_conf.plotly_chart(conf_gauge, use_container_width=True)

        comfort = bk.compute_comfort_score(metrics)
        col_sav.metric("Expected Energy Savings", f"{decision.expected_savings_pct:.1f}%")
        col_sav.metric("Comfort Score", f"{comfort:.0f}%")
        col_sav.metric("Carbon Reduction", f"{round(decision.expected_savings_pct * metrics.energy_kwh * 0.233 / 100, 2)} kg CO₂")

        col_carb.markdown("### 🎯 Optimization Summary")
        col_carb.markdown(f"""
| Parameter | Before | After |
|---|---|---|
| Cooling SP | {metrics.indoor_temperature:.1f}°C | {decision.cooling_setpoint}°C |
| Lighting | 100% | {decision.lighting_level}% |
| Fan Speed | 100% | {decision.fan_speed}% |
| Expected Savings | — | {decision.expected_savings_pct:.1f}% |
""")

    st.divider()

    # ── Decision Log ──────────────────────────────────────────────────────────
    st.subheader("📋 Decision Log")
    hist = bk.get_history_df()
    if hist.empty:
        st.info("No decisions logged yet.")
    else:
        for _, row in hist.iloc[::-1].head(10).iterrows():
            ts      = row.get("Timestamp", row.get("Time", "N/A"))
            reason  = row.get("Reason", "—")
            savings = row.get("ExpectedSavings", "—")
            conf    = row.get("Confidence", "—")
            cool    = row.get("CoolingSP", "—")
            fan     = row.get("Fan", "—")
            st.markdown(f"""
<div style="background:#161B22;border-left:4px solid #00D4FF;padding:12px;
border-radius:8px;margin-bottom:8px;">
<b>🕒 {ts}</b> &nbsp;|&nbsp; Cooling: <b>{cool}°C</b> &nbsp;|&nbsp;
Fan: <b>{fan}%</b> &nbsp;|&nbsp; Savings: <b>{savings}%</b> &nbsp;|&nbsp;
Confidence: <b>{conf}%</b><br>
🤖 {reason}
</div>""", unsafe_allow_html=True)

    st.divider()

    if not hist.empty and "Energy" in hist.columns:
        hist["Energy"] = pd.to_numeric(hist["Energy"], errors="coerce")
        fig = px.line(hist, x="Timestamp" if "Timestamp" in hist.columns else hist.index,
                      y="Energy", markers=True, title="Energy Consumption History")
        fig.update_layout(height=280, paper_bgcolor="#161B22",
                          plot_bgcolor="#161B22", font_color="white")
        st.plotly_chart(fig, use_container_width=True)
