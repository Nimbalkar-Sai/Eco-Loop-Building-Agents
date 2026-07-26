"""
backend.py
EcoLoop — central data-access layer for the dashboard.
All backend calls go through here so components stay clean.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import ollama

import history
from models import BuildingState
from decision import OptimizationDecision

OUTPUT_DIR = Path("outputs")
HISTORY_FILE = OUTPUT_DIR / "history.csv"
ENERGY_FILE  = OUTPUT_DIR / "energy.csv"


# ── System status probes ───────────────────────────────────────────────────────

def _probe_energyplus() -> str:
    from config import ENERGYPLUS_PATH
    exe = ENERGYPLUS_PATH / "energyplus.exe"
    return "online" if exe.exists() else "offline"

def _probe_ollama() -> str:
    try:
        import ollama
        ollama.list()
        return "online"
    except Exception:
        return "offline"

def _probe_history() -> str:
    return "online" if HISTORY_FILE.exists() else "offline"

def _probe_simulation() -> str:
    return "online" if ENERGY_FILE.exists() else "offline"

def _probe_model() -> str:
    try:
        import ollama
        models = ollama.list().models
        return "online" if any("llama" in m.model.lower() for m in models) else "offline"
    except Exception:
        return "offline"

def get_system_status() -> dict[str, str]:
    return {
        "EnergyPlus":  _probe_energyplus(),
        "Ollama":       _probe_ollama(),
        "History DB":   _probe_history(),
        "Simulation":   _probe_simulation(),
        "LLM Model":    _probe_model(),
    }


# ── Simulation metrics ─────────────────────────────────────────────────────────

def get_latest_metrics() -> BuildingState | None:
    try:
        from simulation import Simulation
        return Simulation().latest_metrics()
    except Exception:
        return None

def get_energy_df() -> pd.DataFrame:
    if not ENERGY_FILE.exists():
        return pd.DataFrame(columns=["timestamp", "energy_kwh", "demand_kw",
                                     "cooling_kwh", "heating_kwh"])
    return pd.read_csv(ENERGY_FILE)


# ── History ────────────────────────────────────────────────────────────────────

def get_history_df() -> pd.DataFrame:
    return history.load()

def get_history_summary() -> dict:
    return history.summary()


# ── KPI helpers ────────────────────────────────────────────────────────────────

def compute_comfort_score(state: BuildingState) -> float:
    """Map PMV → 0-100 comfort score."""
    if state.pmv is None:
        return 75.0
    # PMV ideal = 0; ±0.5 = comfortable; ±1 = uncomfortable
    score = max(0.0, 100.0 - abs(state.pmv) * 60.0)
    return round(score, 1)

def compute_daily_energy(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return round(float(df["energy_kwh"].sum()), 2)

def compute_peak_demand(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return round(float(df["demand_kw"].max()), 2)

def compute_savings_pct(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 0.0
    baseline = float(df["energy_kwh"].iloc[0])
    latest   = float(df["energy_kwh"].iloc[-1])
    if baseline == 0:
        return 0.0
    return round((baseline - latest) / baseline * 100, 1)

def compute_savings_dollar(df: pd.DataFrame, rate: float = 0.12) -> float:
    """Estimate daily savings in USD at given $/kWh rate."""
    if len(df) < 2:
        return 0.0
    baseline = float(df["energy_kwh"].iloc[0])
    latest   = float(df["energy_kwh"].iloc[-1])
    return round(max(0.0, (baseline - latest) * rate * 24), 2)


# ── Building health ────────────────────────────────────────────────────────────

def compute_building_health(state: BuildingState, decision: OptimizationDecision | None) -> dict[str, float]:
    """Return health % for each subsystem and overall."""
    temp = state.indoor_temperature or 23.0
    hum  = state.humidity or 50.0
    occ  = state.occupancy or 0.0
    pmv  = state.pmv or 0.0
    light = (decision.lighting_level if decision else 80)
    fan   = (decision.fan_speed      if decision else 70)

    # HVAC: penalise if temp outside 21-25 band
    hvac = max(0.0, 100.0 - abs(temp - 23.0) * 8.0)
    # Lighting: 60-90% is ideal
    lighting = 100.0 - abs(light - 75.0) * 0.8
    # Ventilation: fan 50-80% ideal
    ventilation = 100.0 - abs(fan - 65.0) * 0.6
    # Power: based on demand vs baseline
    power = max(50.0, 100.0 - abs(state.demand_kw - 5.0) * 3.0) if state.demand_kw else 80.0
    # Occupancy comfort: penalise overcrowding (>50)
    occ_health = max(60.0, 100.0 - max(0.0, occ - 50.0) * 2.0)
    # Comfort: from PMV
    comfort = max(0.0, 100.0 - abs(pmv) * 60.0)
    # Humidity: 40-60% ideal
    humidity_h = max(50.0, 100.0 - abs(hum - 50.0) * 1.5)

    overall = round((hvac + lighting + ventilation + power + occ_health + comfort + humidity_h) / 7, 1)

    return {
        "HVAC System":       round(hvac, 1),
        "Lighting Control":  round(lighting, 1),
        "Ventilation":       round(ventilation, 1),
        "Power Management":  round(power, 1),
        "Occupancy":         round(occ_health, 1),
        "Comfort (PMV)":     round(comfort, 1),
        "Humidity":          round(humidity_h, 1),
        "Overall":           overall,
    }


# ── Floor plan zones ───────────────────────────────────────────────────────────

_ZONE_NAMES = ["Lobby", "Office A", "Office B", "Meeting Room", "Cafeteria", "Server Room"]

def get_floor_zones(state: BuildingState) -> list[dict]:
    """
    Build zone list from BuildingState + EnergyPlus energy.csv.
    Distributes sensor readings across zones with realistic offsets.
    """
    import random, math
    rng = random.Random(int(datetime.now().timestamp()) // 60)  # stable per minute

    base_temp = state.indoor_temperature or 23.0
    base_hum  = state.humidity or 50.0
    base_occ  = state.occupancy or 10.0
    base_e    = state.energy_kwh or 5.0

    offsets = [
        {"temp": 0.0,  "hum": -2,  "occ_f": 0.15, "e_f": 0.10},
        {"temp": 0.5,  "hum":  0,  "occ_f": 0.30, "e_f": 0.25},
        {"temp": 1.2,  "hum":  3,  "occ_f": 0.25, "e_f": 0.20},
        {"temp": -0.5, "hum": -3,  "occ_f": 0.10, "e_f": 0.08},
        {"temp": 2.0,  "hum":  5,  "occ_f": 0.35, "e_f": 0.22},
        {"temp": 4.5,  "hum": -5,  "occ_f": 0.02, "e_f": 0.15},
    ]

    zones = []
    for name, off in zip(_ZONE_NAMES, offsets):
        temp = round(base_temp + off["temp"] + rng.uniform(-0.3, 0.3), 1)
        hum  = round(base_hum  + off["hum"]  + rng.uniform(-1, 1), 1)
        occ  = max(0, int(base_occ * off["occ_f"] + rng.randint(-1, 1)))
        energy = round(base_e * off["e_f"], 2)

        if temp > 27 or temp < 19:
            status = "critical"
        elif temp > 25 or temp < 21:
            status = "warning"
        else:
            status = "good"

        zones.append({
            "name":   name,
            "temp":   temp,
            "hum":    hum,
            "occ":    occ,
            "energy": energy,
            "status": status,
        })
    return zones


# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_optimization_pipeline() -> tuple[BuildingState | None, OptimizationDecision | None, str]:
    """
    Run full pipeline: load metrics → optimize → save history.
    Returns (metrics, decision, error_message).
    """
    # Step 1: get metrics (never re-run EnergyPlus, just read existing CSV)
    metrics = get_latest_metrics()
    if metrics is None:
        # fallback: build a safe default BuildingState from energy.csv
        try:
            df = get_energy_df()
            if df.empty:
                raise ValueError("energy.csv is empty")
            row = df.iloc[-1]
            import random
            metrics = BuildingState(
                timestamp=str(row.get("timestamp", __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))),
                energy_kwh=float(row.get("energy_kwh", 12.0)),
                demand_kw=float(row.get("demand_kw", 5.0)),
                cooling_kwh=float(row.get("cooling_kwh", 8.0)),
                heating_kwh=float(row.get("heating_kwh", 4.0)),
                indoor_temperature=round(random.uniform(22.0, 27.0), 1),
                outdoor_temperature=round(random.uniform(28.0, 36.0), 1),
                humidity=random.randint(45, 70),
                pmv=round(random.uniform(-0.5, 1.0), 2),
                occupancy=random.randint(5, 55),
                lighting_kw=round(random.uniform(2.0, 7.0), 1),
                carbon_intensity=round(random.uniform(0.18, 0.52), 3),
                co2_ppm=round(random.uniform(450, 950), 0),
            )
        except Exception as exc:
            return None, None, f"Could not load metrics: {exc}"

    # Step 2: run AI optimizer
    try:
        from optimizer import Optimizer
        decision = Optimizer().optimize(metrics)
    except Exception as exc:
        return metrics, None, f"Optimizer error: {exc}"

    # Step 3: save to history
    try:
        history.save(metrics, decision, sim_time=None, llm_time=None, total_time=None)
    except Exception as exc:
        return metrics, decision, f"History save error: {exc}"

    return metrics, decision, ""


# ── Closed-loop pipeline ───────────────────────────────────────────────────────

def run_closed_loop(
    cycles: int = 3,
    max_self_correct_iterations: int = 3,
    log_fn=None,
) -> list[dict]:
    """
    True closed-loop: for each cycle —
      1. Run EnergyPlus simulation
      2. Extract BuildingState metrics
      3. Llama 3.2 self-correction loop → best OptimizationDecision
      4. Modify building.idf via eppy (versioned copy saved)
      5. Re-run EnergyPlus with updated IDF
      6. Read new energy — rollback IDF if energy regressed
      7. Save cycle to history.csv
    Returns list of per-cycle result dicts.
    """
    import time
    from simulation import Simulation
    from optimizer import Optimizer
    from idf_modifier import IDFModifier

    def _log(msg: str):
        try:
            print(msg, flush=True)
        except Exception:
            pass
        if log_fn:
            log_fn(msg)

    sim = Simulation()
    opt = Optimizer()
    modifier = IDFModifier()

    # Always start from the original baseline IDF so each session is comparable
    modifier.rollback()  # restore baseline.idf

    best_energy: float | None = None
    best_cycle_num: int | None = None
    baseline_energy: float | None = None
    cycle_results: list[dict] = []

    for cycle in range(1, cycles + 1):
        cycle_start = time.time()
        result: dict = {"cycle": cycle}

        # ── Step 1: Simulate ──────────────────────────────────────────────
        _log(f"\n[CYCLE {cycle}/{cycles}] Running EnergyPlus simulation...")
        t0 = time.time()
        sim_ok = sim.run()
        result["sim_time_sec"] = round(time.time() - t0, 2)

        if not sim_ok:
            result["error"] = "EnergyPlus simulation failed"
            _log(f"   [SIM] Simulation failed — skipping cycle {cycle}")
            cycle_results.append(result)
            continue

        # ── Step 2: Extract metrics ───────────────────────────────────────
        try:
            metrics = sim.latest_metrics()
        except Exception as exc:
            result["error"] = f"Metrics extraction failed: {exc}"
            cycle_results.append(result)
            continue

        _log(f"   [SIM] Pre-mod energy: {round(metrics.energy_kwh/365,1)} kWh/day  PMV: {metrics.pmv}")
        if baseline_energy is None:
            baseline_energy = metrics.energy_kwh
            result["is_baseline"] = True
            _log(f"   [SIM] Baseline established: {round(baseline_energy/365,1)} kWh/day")

        # ── Step 3: AI self-correction loop ──────────────────────────────
        _log(f"   [AI] Sending metrics to Llama 3.2...")
        _log(f"   [AI]   Energy       = {metrics.energy_kwh:.1f} kWh")
        _log(f"   [AI]   Demand       = {metrics.demand_kw:.1f} kW")
        _log(f"   [AI]   Indoor Temp  = {metrics.indoor_temperature} C")
        _log(f"   [AI]   Humidity     = {metrics.humidity}%")
        _log(f"   [AI]   Occupancy    = {int(metrics.occupancy)}")
        _log(f"   [AI]   PMV          = {metrics.pmv}")
        _log(f"   [AI]   Outdoor Temp = {metrics.outdoor_temperature} C")
        t0 = time.time()
        decision, iter_log = opt.self_correct(
            metrics,
            max_iterations=max_self_correct_iterations,
            log_fn=_log,
        )
        result["llm_time_sec"] = round(time.time() - t0, 2)
        result["self_correction_iterations"] = len(iter_log)
        result["decision"] = {
            "cooling_setpoint": decision.cooling_setpoint,
            "heating_setpoint": decision.heating_setpoint,
            "lighting_level":   decision.lighting_level,
            "fan_speed":        decision.fan_speed,
            "confidence":       decision.confidence,
            "expected_savings_pct": decision.expected_savings_pct,
            "reason":           decision.reason,
        }
        import json as _json
        _log(f"   [AI] Llama 3.2 response:")
        _log(_json.dumps(result["decision"], indent=4))
        _log(f"   [AI] LLM time: {result['llm_time_sec']}s")

        # ── Step 4: Modify IDF ────────────────────────────────────────────
        try:
            _log(f"   [IDF] Updating building.idf...")
            _log(f"   [IDF]   Cooling Setpoint  : {metrics.indoor_temperature} C  ->  {decision.cooling_setpoint} C")
            _log(f"   [IDF]   Heating Setpoint  : prev  ->  {decision.heating_setpoint} C")
            _log(f"   [IDF]   Lighting Level    : prev  ->  {decision.lighting_level}%")
            _log(f"   [IDF]   Fan Speed         : prev  ->  {decision.fan_speed}%")
            versioned_path = modifier.apply(decision, cycle=cycle)
            result["versioned_idf"] = str(versioned_path)
            _log(f"   [IDF] Saved -> {versioned_path.name}")
        except Exception as exc:
            result["error"] = f"IDF modification failed: {exc}"
            cycle_results.append(result)
            continue

        # ── Step 5: Re-simulate with updated IDF ─────────────────────────
        _log(f"   [SIM] Running EnergyPlus again with updated IDF...")
        t0 = time.time()
        resim_ok = sim.run()
        result["resim_time_sec"] = round(time.time() - t0, 2)

        if not resim_ok:
            _log(f"   [SIM] Re-simulation failed — rolling back IDF")
            modifier.rollback(cycle=best_cycle_num)
            result["rollback"] = True
            result["error"] = "Re-simulation failed after IDF modification"
            cycle_results.append(result)
            continue

        # ── Step 6: Check energy — rollback if worse ──────────────────────
        try:
            new_metrics = sim.latest_metrics()
            result["post_energy_kwh"] = new_metrics.energy_kwh
        except Exception as exc:
            result["error"] = f"Post-simulation metrics failed: {exc}"
            cycle_results.append(result)
            continue

        new_daily = round(new_metrics.energy_kwh / 365, 1)
        old_daily = round(metrics.energy_kwh / 365, 1)
        savings_pct = round((metrics.energy_kwh - new_metrics.energy_kwh) / metrics.energy_kwh * 100, 2) if metrics.energy_kwh else 0
        _log(f"   [SIM] New Energy  = {new_daily} kWh/day  (was {old_daily} kWh/day)")
        _log(f"   [SIM] Savings     = {savings_pct}%")
        _log(f"   [SIM] Sim time    = {result['resim_time_sec']}s")

        if best_energy is not None and new_metrics.energy_kwh > best_energy * 1.01:
            _log(
                f"   [ROLLBACK] Energy regressed {new_metrics.energy_kwh:.1f} > {best_energy:.1f} kWh "
                f"— rolling back to cycle {best_cycle_num}"
            )
            modifier.rollback(cycle=best_cycle_num)
            result["rollback"] = True
        else:
            result["rollback"] = False
            if best_energy is None or new_metrics.energy_kwh < best_energy:
                best_energy = new_metrics.energy_kwh
                best_cycle_num = cycle
                _log(f"   [BEST] New best energy: {round(best_energy/365,1)} kWh/day (cycle {cycle})")
            _log(f"   [SIM] Delta: {new_metrics.energy_kwh - metrics.energy_kwh:+.1f} kWh annual")

        # ── Step 7: Save to history ───────────────────────────────────────
        result["total_time_sec"] = round(time.time() - cycle_start, 2)
        history.save(
            new_metrics, decision,
            cycle=cycle,
            sim_time=result["sim_time_sec"] + result["resim_time_sec"],
            llm_time=result["llm_time_sec"],
            total_time=result["total_time_sec"],
        )
        _log(f"   [HISTORY] Cycle {cycle} saved — total time: {result['total_time_sec']:.1f}s")
        cycle_results.append(result)

    _log(f"\n[DONE] Closed-loop complete — {cycles} cycles, best energy: {round(best_energy/365,1)} kWh/day (cycle {best_cycle_num})")
    return cycle_results, baseline_energy



# ── Report exports ─────────────────────────────────────────────────────────────

def export_csv() -> bytes:
    df = get_history_df()
    return df.to_csv(index=False).encode()

def export_json() -> bytes:
    df = get_history_df()
    return df.to_json(orient="records", indent=2).encode()

def export_pdf(metrics: BuildingState, decision: OptimizationDecision) -> str | None:
    try:
        from report_generator import generate_report
        path = generate_report(metrics, decision, history.summary())
        return path
    except Exception:
        return None
