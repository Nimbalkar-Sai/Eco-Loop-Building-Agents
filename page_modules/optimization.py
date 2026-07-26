"""page_modules/optimization.py — Autonomous Optimization Loop"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
from datetime import datetime
import backend as bk


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _decision_card(cycle: int, energy_before: float, energy_after: float,
                   decision, metrics):
    savings_pct = round((energy_before - energy_after) / energy_before * 100, 1) if energy_before else 0
    pmv = metrics.pmv or 0
    carbon_saved = round((energy_before - energy_after) * 0.233, 2)
    pmv_ok = -0.5 <= pmv <= 0.5

    st.markdown(f"""
<div style="background:#161B22;border:1px solid #30363D;border-left:4px solid #00D4FF;
padding:16px;border-radius:8px;margin-bottom:12px;">
<b style="font-size:1.1em;">Cycle {cycle}</b>
<div style="display:flex;gap:32px;margin-top:10px;flex-wrap:wrap;">
  <div>⚡ <b>Energy</b><br><span style="color:#2ECC71;font-size:1.2em;">↓ {savings_pct}%</span></div>
  <div>😊 <b>PMV</b><br><span style="color:{'#2ECC71' if pmv_ok else '#E74C3C'};font-size:1.2em;">{pmv:.2f}</span></div>
  <div>🎯 <b>Confidence</b><br><span style="color:#00D4FF;font-size:1.2em;">{decision.confidence:.0f}%</span></div>
  <div>🌿 <b>Carbon Saved</b><br><span style="color:#2ECC71;font-size:1.2em;">{carbon_saved} kg</span></div>
  <div>❄ <b>Cooling SP</b><br><span style="font-size:1.2em;">{decision.cooling_setpoint}°C</span></div>
  <div>💡 <b>Lighting</b><br><span style="font-size:1.2em;">{decision.lighting_level}%</span></div>
  <div>🌀 <b>Fan</b><br><span style="font-size:1.2em;">{decision.fan_speed}%</span></div>
</div>
<div style="margin-top:10px;color:#8B949E;font-size:0.9em;">🤖 {decision.reason}</div>
</div>""", unsafe_allow_html=True)


def render():
    st.markdown("<div class='main-title'>🎯 Autonomous Optimization Loop</div>", unsafe_allow_html=True)
    st.caption("Closed-loop: Simulate → AI → Self-Correct → Modify IDF → Rollback if worse → Repeat → Best Config")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        max_cycles = st.number_input("Optimization Cycles", min_value=1, max_value=10, value=3)
        self_correct_iters = st.number_input("Self-Correction Iterations per Cycle", min_value=1, max_value=5, value=2)
    with col2:
        comfort_threshold = st.slider("Min Comfort Threshold (%)", 50, 100, 70)
        goal = st.selectbox("Optimization Goal", ["Balanced", "Energy Saving", "Comfort", "Carbon"])

    run_btn = st.button("🚀 Start Autonomous Loop", type="primary", use_container_width=True)
    st.divider()

    if not run_btn:
        hist = bk.get_history_df()
        if not hist.empty:
            st.subheader("📋 Previous Optimization History")
            for col in ["Energy", "ExpectedSavings", "Confidence"]:
                if col in hist.columns:
                    hist[col] = pd.to_numeric(hist[col], errors="coerce")
            st.dataframe(hist.tail(15), use_container_width=True, hide_index=True)
            if "Energy" in hist.columns:
                fig = px.line(hist, x="Timestamp" if "Timestamp" in hist.columns else hist.index,
                              y="Energy", markers=True, title="Energy Across Cycles")
                fig.update_layout(height=300, paper_bgcolor="#161B22",
                                  plot_bgcolor="#161B22", font_color="white")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Click **Start Autonomous Loop** to begin.")
        return

    # ── Live Log ──────────────────────────────────────────────────────────────
    st.subheader("📡 Live Pipeline Logs")
    log_area = st.empty()
    live_logs = []

    def log(msg: str):
        live_logs.append(f"[{_ts()}] {msg}")
        log_area.code("\n".join(live_logs), language="text")

    # ── Cards placeholder ─────────────────────────────────────────────────────
    cards_area = st.empty()

    # ── Run Cycles ────────────────────────────────────────────────────────────
    overall_bar = st.progress(0, text="Initializing...")
    cycle_results = []
    best_decision = None
    best_energy = float("inf")
    best_cycle = 1
    best_metrics = None
    baseline_energy = None

    loop_start = time.time()

    # Run the true closed loop: simulate → AI → modify IDF → re-simulate → rollback → save
    raw_results, true_baseline = bk.run_closed_loop(
        cycles=max_cycles,
        max_self_correct_iterations=self_correct_iters,
        log_fn=log,
    )
    baseline_energy = true_baseline

    for r in raw_results:
        cycle = r["cycle"]
        overall_bar.progress(int(cycle / max_cycles * 100), text=f"Cycle {cycle}/{max_cycles}")

        if "error" in r:
            log(f"[ERROR] Cycle {cycle}: {r['error']}")
            continue

        pre_e  = r.get("pre_energy_kwh", 0)
        post_e = r.get("post_energy_kwh", pre_e)
        d      = r["decision"]
        rolled = r.get("rollback", False)

        if baseline_energy is None:
            baseline_energy = pre_e

        if rolled:
            log(f"[ROLLBACK] Cycle {cycle}: rolled back (energy regressed)")
        else:
            if post_e < best_energy:
                best_energy = post_e
                best_cycle  = cycle
            log(f"[BEST] Cycle {cycle} -> {round(post_e/365,1)} kWh/day")

        # Actual savings vs previous cycle (not AI's estimate)
        actual_savings_pct = round((pre_e - post_e) / pre_e * 100, 1) if pre_e else 0
        comfort = max(0.0, 100.0 - abs(0.0) * 60.0)

        cycle_results.append({
            "Cycle":          cycle,
            "Energy (kWh)":   round(post_e, 2),
            "Pre-mod (kWh)": round(pre_e, 2),
            "Rollback":       "↩ Yes" if rolled else "✅ No",
            "Comfort (%)":    round(comfort, 1),
            "Carbon (kg)":    round(post_e * 0.233, 2),
            "Savings (%)":    actual_savings_pct,
            "Confidence (%)": d["confidence"],
            "Cooling SP":     d["cooling_setpoint"],
            "Fan Speed":      d["fan_speed"],
            "Lighting":       d["lighting_level"],
            "SC Iters":       r.get("self_correction_iterations", 1),
            "Sim Time (s)":   r.get("sim_time_sec", 0),
            "LLM Time (s)":   r.get("llm_time_sec", 0),
            "Total Time (s)": r.get("total_time_sec", 0),
        })

        best_decision = type("D", (), d)()
        best_metrics  = bk.get_latest_metrics()

    total_elapsed = round(time.time() - loop_start, 2)
    log(f"{'='*50}")
    log(f"[BEST] Cycle {best_cycle} | Energy: {round(best_energy/365,1)} kWh/day")
    log(f"[TIME] Total runtime: {total_elapsed}s")
    log("[DONE] Autonomous loop complete")

    st.divider()

    # ── Results Summary ───────────────────────────────────────────────────────
    if cycle_results and baseline_energy is not None and best_metrics:
        st.subheader("🏆 Optimization Summary")
        best_savings_pct = round((baseline_energy - best_energy) / baseline_energy * 100, 1) if baseline_energy else 0
        carbon_saved = round((baseline_energy - best_energy) * 0.233, 2)
        carbon_label = f"{carbon_saved} kg CO₂" if carbon_saved >= 0 else f"⚠️ +{abs(carbon_saved)} kg CO₂"
        trees = round(max(0, carbon_saved) * 365 / 21.77, 1)

        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.metric("Baseline Energy",  f"{baseline_energy:.2f} kWh")
        s2.metric("Best Energy",      f"{best_energy:.2f} kWh",    delta=f"-{baseline_energy - best_energy:.2f} kWh")
        s3.metric("Energy Savings",   f"{best_savings_pct:.1f}%")
        s4.metric("PMV",              f"{best_metrics.pmv:.2f}")
        s5.metric("Carbon Saved",     carbon_label)
        s6.metric("Total Runtime",    f"{total_elapsed}s")

        st.divider()

        # ── Decision Cards ────────────────────────────────────────────────────
        st.subheader("🏆 Best Cycle Decision")
        best_r = next((r for r in cycle_results if r["Cycle"] == best_cycle), cycle_results[-1])
        e_before = baseline_energy
        e_after  = best_r["Energy (kWh)"]
        class _D:
            pass
        d = _D()
        d.cooling_setpoint = best_r["Cooling SP"]
        d.lighting_level   = best_r["Lighting"]
        d.fan_speed        = best_r["Fan Speed"]
        d.confidence       = best_r["Confidence (%)"]
        import history as _hist
        _df = _hist.load()
        d.reason = _df.query(f"Cycle == {best_cycle}")["Reason"].iloc[-1] \
            if not _df.empty and "Reason" in _df.columns else "—"
        class _M:
            pass
        m = _M()
        m.pmv = best_metrics.pmv
        _decision_card(best_cycle, e_before, e_after, d, m)

        st.divider()

        df = pd.DataFrame(cycle_results)

        # ── Progress Chart ────────────────────────────────────────────────────
        st.subheader("📈 Optimization Progress")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Cycle"], y=df["Energy (kWh)"],
                                 mode="lines+markers", name="Energy (kWh)",
                                 line_color="#E74C3C", yaxis="y1"))
        fig.add_trace(go.Scatter(x=df["Cycle"], y=df["Savings (%)"],
                                 mode="lines+markers", name="Savings (%)",
                                 line_color="#2ECC71", yaxis="y2"))
        fig.add_trace(go.Scatter(x=df["Cycle"], y=df["Confidence (%)"],
                                 mode="lines+markers", name="Confidence (%)",
                                 line_color="#00D4FF", yaxis="y2"))
        fig.add_trace(go.Scatter(x=df["Cycle"], y=df["Comfort (%)"],
                                 mode="lines+markers", name="Comfort (%)",
                                 line_color="#F1C40F", yaxis="y2"))
        fig.update_layout(
            height=380, paper_bgcolor="#161B22", plot_bgcolor="#161B22",
            font_color="white", title="Energy / Savings / Confidence / Comfort per Cycle",
            xaxis_title="Cycle",
            yaxis=dict(title="Energy (kWh)", color="#E74C3C"),
            yaxis2=dict(title="% Value", overlaying="y", side="right",
                        range=[0, 110], color="white"),
            legend=dict(bgcolor="#161B22"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Timing Chart ──────────────────────────────────────────────────────
        st.subheader("⏱ Timing Breakdown")
        fig_t = go.Figure()
        fig_t.add_trace(go.Bar(x=df["Cycle"], y=df["Sim Time (s)"],
                               name="Simulation (s)", marker_color="#F1C40F"))
        fig_t.add_trace(go.Bar(x=df["Cycle"], y=df["LLM Time (s)"],
                               name="LLM (s)", marker_color="#00D4FF"))
        fig_t.update_layout(barmode="stack", height=280, paper_bgcolor="#161B22",
                            plot_bgcolor="#161B22", font_color="white",
                            title="Time per Cycle (seconds)", xaxis_title="Cycle")
        st.plotly_chart(fig_t, use_container_width=True)

        st.divider()
        st.dataframe(df, use_container_width=True, hide_index=True)
