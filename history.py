"""history.py — Saves and loads full optimization cycle records."""

import pandas as pd
from pathlib import Path
from datetime import datetime

FILE = Path("outputs/history.csv")
FILE.parent.mkdir(exist_ok=True)


def save(metrics, decision, cycle: int = None,
         sim_time: float = None, llm_time: float = None, total_time: float = None):
    row = {
        "Timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Cycle":           cycle or 1,
        # ── Inputs ──────────────────────────────────────────────────────────
        "Energy":          round(metrics.energy_kwh, 3),
        "Demand":          round(metrics.demand_kw, 3),
        "IndoorTemp":      metrics.indoor_temperature,
        "OutdoorTemp":     metrics.outdoor_temperature,
        "Humidity":        metrics.humidity,
        "PMV":             metrics.pmv,
        "Occupancy":       metrics.occupancy,
        "LightingKW":      metrics.lighting_kw,
        "CarbonIntensity": metrics.carbon_intensity,
        # ── Decision ────────────────────────────────────────────────────────
        "CoolingSP":       decision.cooling_setpoint,
        "HeatingSP":       decision.heating_setpoint,
        "Lighting":        decision.lighting_level,
        "Fan":             decision.fan_speed,
        "Confidence":      decision.confidence,
        "ExpectedSavings": decision.expected_savings_pct,
        "Reason":          decision.reason,
        # ── Timing ──────────────────────────────────────────────────────────
        "SimTimeSec":      round(sim_time, 2) if sim_time is not None else None,
        "LLMTimeSec":      round(llm_time, 2) if llm_time is not None else None,
        "TotalTimeSec":    round(total_time, 2) if total_time is not None else None,
    }

    df = pd.read_csv(FILE) if FILE.exists() else pd.DataFrame()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(FILE, index=False)


def load() -> pd.DataFrame:
    if FILE.exists():
        return pd.read_csv(FILE)
    return pd.DataFrame()


def summary() -> dict:
    df = load()
    if df.empty:
        return {"cycles": 0, "avg_energy": 0, "min_energy": 0,
                "max_energy": 0, "total_savings_pct": 0, "avg_confidence": 0}
    e = df["Energy"] if "Energy" in df.columns else pd.Series([0])
    c = df["Confidence"] if "Confidence" in df.columns else pd.Series([0])
    s = df["ExpectedSavings"] if "ExpectedSavings" in df.columns else pd.Series([0])
    return {
        "cycles":            len(df),
        "avg_energy":        round(float(e.mean()), 2),
        "min_energy":        round(float(e.min()), 2),
        "max_energy":        round(float(e.max()), 2),
        "avg_confidence":    round(float(c.mean()), 1),
        "avg_savings_pct":   round(float(s.mean()), 1),
        "total_savings_pct": round(
            (float(e.iloc[0]) - float(e.iloc[-1])) / float(e.iloc[0]) * 100, 1
        ) if len(df) > 1 and float(e.iloc[0]) != 0 else 0,
    }


def best_cycle(metric: str = "ExpectedSavings") -> dict | None:
    """Return the row with the best value for the given metric."""
    df = load()
    if df.empty or metric not in df.columns:
        return None
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    return df.loc[df[metric].idxmin() if metric == "Energy" else df[metric].idxmax()].to_dict()
