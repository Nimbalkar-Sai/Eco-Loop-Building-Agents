"""
mcp_server.py — EcoLoop MCP Server
Exposes EcoLoop building optimization tools to AI agents via Model Context Protocol.

Run with:
    python mcp_server.py
    OR
    fastmcp run mcp_server.py
"""

from mcp.server.fastmcp import FastMCP
from prompts import SYSTEM_PROMPT

mcp = FastMCP("EcoLoop")


# ── Tool 1: Run full optimization pipeline ────────────────────────────────────

@mcp.tool()
def run_optimization() -> dict:
    """
    Run the full EcoLoop pipeline:
    EnergyPlus simulation → AI analysis → optimization decision → IDF update.
    Returns current building metrics and AI decision.
    """
    try:
        import backend as bk
        metrics, decision, err = bk.run_optimization_pipeline()

        if metrics is None:
            return {"success": False, "error": err}

        return {
            "success": True,
            "error": err or None,
            "metrics": {
                "timestamp": metrics.timestamp,
                "energy_kwh": metrics.energy_kwh,
                "demand_kw": metrics.demand_kw,
                "cooling_kwh": metrics.cooling_kwh,
                "heating_kwh": metrics.heating_kwh,
                "indoor_temperature": metrics.indoor_temperature,
                "outdoor_temperature": metrics.outdoor_temperature,
                "humidity": metrics.humidity,
                "pmv": metrics.pmv,
                "occupancy": metrics.occupancy,
                "lighting_kw": metrics.lighting_kw,
            },
            "decision": {
                "cooling_setpoint": decision.cooling_setpoint,
                "heating_setpoint": decision.heating_setpoint,
                "lighting_level": decision.lighting_level,
                "fan_speed": decision.fan_speed,
                "reason": decision.reason,
            } if decision else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 2: Get current building metrics ──────────────────────────────────────

@mcp.tool()
def get_building_metrics() -> dict:
    """
    Return the latest building metrics from the most recent EnergyPlus simulation.
    Does NOT re-run the simulation.
    """
    try:
        import backend as bk
        metrics = bk.get_latest_metrics()
        if metrics is None:
            return {"success": False, "error": "No simulation data available"}
        return {
            "success": True,
            "timestamp": metrics.timestamp,
            "energy_kwh": metrics.energy_kwh,
            "demand_kw": metrics.demand_kw,
            "cooling_kwh": metrics.cooling_kwh,
            "heating_kwh": metrics.heating_kwh,
            "indoor_temperature": metrics.indoor_temperature,
            "outdoor_temperature": metrics.outdoor_temperature,
            "humidity": metrics.humidity,
            "pmv": metrics.pmv,
            "occupancy": metrics.occupancy,
            "lighting_kw": metrics.lighting_kw,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 3: Get optimization history ─────────────────────────────────────────

@mcp.tool()
def get_optimization_history() -> dict:
    """
    Return the full optimization history including all past cycles,
    energy trends, and summary statistics.
    """
    try:
        import backend as bk
        df = bk.get_history_df()
        summary = bk.get_history_summary()

        if df.empty:
            return {"success": True, "cycles": 0, "history": [], "summary": summary}

        return {
            "success": True,
            "cycles": len(df),
            "summary": summary,
            "history": df.tail(20).to_dict(orient="records"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 4: Get energy comparison ─────────────────────────────────────────────

@mcp.tool()
def get_energy_comparison() -> dict:
    """
    Return before vs after energy comparison showing savings achieved by AI optimization.
    """
    try:
        import backend as bk
        df = bk.get_energy_df()
        metrics, decision, err = bk.run_optimization_pipeline()

        if metrics is None:
            return {"success": False, "error": err}

        savings_pct = bk.compute_savings_pct(df)
        daily_energy = bk.compute_daily_energy(df)
        peak = bk.compute_peak_demand(df)
        savings_dollar = bk.compute_savings_dollar(df)

        before_e = metrics.energy_kwh
        after_e = max(before_e * (1 - savings_pct / 100), 0)

        return {
            "success": True,
            "before_energy_kwh": before_e,
            "after_energy_kwh": round(after_e, 2),
            "savings_pct": savings_pct,
            "savings_dollar_per_day": savings_dollar,
            "daily_energy_kwh": daily_energy,
            "peak_demand_kw": peak,
            "carbon_before_kg": round(before_e * 0.233, 2),
            "carbon_after_kg": round(after_e * 0.233, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 5: Get comfort metrics ───────────────────────────────────────────────

@mcp.tool()
def get_comfort_metrics() -> dict:
    """
    Return occupant thermal comfort metrics including PMV, PPD, and comfort score.
    """
    try:
        import numpy as np
        import backend as bk

        metrics = bk.get_latest_metrics()
        if metrics is None:
            return {"success": False, "error": "No simulation data available"}

        comfort_score = bk.compute_comfort_score(metrics)
        pmv = metrics.pmv or 0.0
        ppd = round(100 - 95 * np.exp(-0.03353 * pmv**4 - 0.2179 * pmv**2), 1)

        return {
            "success": True,
            "indoor_temperature": metrics.indoor_temperature,
            "humidity": metrics.humidity,
            "pmv": pmv,
            "ppd": ppd,
            "comfort_score": comfort_score,
            "ashrae_compliant": -0.5 <= pmv <= 0.5,
            "status": (
                "Thermally Neutral" if -0.5 <= pmv <= 0.5
                else "Slightly Uncomfortable" if -1 <= pmv <= 1
                else "Significant Discomfort"
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 6: Get carbon metrics ────────────────────────────────────────────────

@mcp.tool()
def get_carbon_metrics() -> dict:
    """
    Return carbon emissions metrics and sustainability analysis.
    """
    try:
        import backend as bk
        df = bk.get_energy_df()
        daily_e = bk.compute_daily_energy(df)
        savings_pct = bk.compute_savings_pct(df)

        daily_carbon = round(daily_e * 0.233, 2)
        monthly_carbon = round(daily_carbon * 30, 2)
        annual_carbon = round(daily_carbon * 365, 2)
        carbon_reduction = round(daily_carbon * savings_pct / 100, 2)
        trees_saved = round(annual_carbon * savings_pct / 100 / 21.77, 1)
        sustainability_score = min(100, round(50 + savings_pct * 2, 0))

        return {
            "success": True,
            "daily_carbon_kg": daily_carbon,
            "monthly_carbon_kg": monthly_carbon,
            "annual_carbon_kg": annual_carbon,
            "carbon_reduction_kg_per_day": carbon_reduction,
            "trees_saved_per_year": trees_saved,
            "sustainability_score": sustainability_score,
            "savings_pct": savings_pct,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 7: Get system status ─────────────────────────────────────────────────

@mcp.tool()
def get_system_status() -> dict:
    """
    Return the status of all EcoLoop system components:
    EnergyPlus, Ollama, LLM model, history database, simulation data.
    """
    try:
        import backend as bk
        return {"success": True, "status": bk.get_system_status()}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 8: Apply optimization decision ───────────────────────────────────────

@mcp.tool()
def apply_optimization(
    cooling_setpoint: float,
    heating_setpoint: float,
    lighting_level: int,
    fan_speed: int,
) -> dict:
    """
    Directly apply a custom optimization decision to the building IDF.
    Parameters:
        cooling_setpoint: Target cooling temperature in °C (e.g. 24.0)
        heating_setpoint: Target heating temperature in °C (e.g. 20.0)
        lighting_level:   Lighting level as percentage 0-100
        fan_speed:        Fan speed as percentage 0-100
    """
    try:
        from decision import OptimizationDecision
        from idf_modifier import IDFModifier

        decision = OptimizationDecision(
            cooling_setpoint=cooling_setpoint,
            heating_setpoint=heating_setpoint,
            lighting_level=lighting_level,
            fan_speed=fan_speed,
            reason="Manually applied via MCP tool",
        )
        IDFModifier().apply(decision)
        return {
            "success": True,
            "applied": {
                "cooling_setpoint": cooling_setpoint,
                "heating_setpoint": heating_setpoint,
                "lighting_level": lighting_level,
                "fan_speed": fan_speed,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 9: Run EnergyPlus simulation ───────────────────────────────────────

@mcp.tool()
def run_energyplus() -> dict:
    """
    Execute the EnergyPlus simulation using the current building.idf and weather.epw.
    Returns success status and simulation duration.
    """
    try:
        import time
        from simulation import Simulation
        sim = Simulation()
        t0 = time.time()
        success = sim.run()
        elapsed = round(time.time() - t0, 2)
        return {
            "success": success,
            "simulation_time_sec": elapsed,
            "message": "Simulation completed successfully" if success else "Simulation failed",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 10: Read simulation results ─────────────────────────────────────────

@mcp.tool()
def read_simulation_results() -> dict:
    """
    Parse and return the raw EnergyPlus output CSV (energy.csv).
    Returns all rows as a list of records plus summary statistics.
    """
    try:
        from simulation import Simulation
        df = Simulation().load_results()
        return {
            "success": True,
            "rows": len(df),
            "columns": list(df.columns),
            "summary": {
                "total_energy_kwh": round(float(df["energy_kwh"].sum()), 3),
                "peak_demand_kw":   round(float(df["demand_kw"].max()), 3),
                "avg_energy_kwh":   round(float(df["energy_kwh"].mean()), 3),
            },
            "records": df.tail(24).to_dict(orient="records"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 11: Modify building model ────────────────────────────────────────────

@mcp.tool()
def modify_building_model(
    cooling_setpoint: float,
    heating_setpoint: float,
    lighting_level: int,
    fan_speed: int,
    cycle: int = None,
) -> dict:
    """
    Directly modify the building IDF file with new control setpoints.
    Saves a versioned copy as iteration_<cycle>.idf.
    Parameters:
        cooling_setpoint: Cooling thermostat setpoint in °C
        heating_setpoint: Heating thermostat setpoint in °C
        lighting_level:   Lighting level percentage 0-100
        fan_speed:        Fan speed percentage 0-100
        cycle:            Optional cycle number for versioned IDF filename
    """
    try:
        from decision import OptimizationDecision
        from idf_modifier import IDFModifier
        decision = OptimizationDecision(
            cooling_setpoint=cooling_setpoint,
            heating_setpoint=heating_setpoint,
            lighting_level=lighting_level,
            fan_speed=fan_speed,
            reason="Modified via MCP modify_building_model tool",
        )
        modifier = IDFModifier()
        versioned_path = modifier.apply(decision, cycle=cycle)
        return {
            "success": True,
            "versioned_idf": str(versioned_path),
            "applied": {
                "cooling_setpoint": cooling_setpoint,
                "heating_setpoint": heating_setpoint,
                "lighting_level": lighting_level,
                "fan_speed": fan_speed,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 12: Validate simulation ──────────────────────────────────────────────

@mcp.tool()
def validate_simulation() -> dict:
    """
    Validate the last EnergyPlus simulation by inspecting eplusout.end and eplusout.err.
    Returns success status, error count, warning count, and usability of results.
    """
    try:
        from pathlib import Path
        end_file = Path("outputs/eplusout.end")
        err_file = Path("outputs/eplusout.err")

        if not end_file.exists():
            return {"success": False, "valid": False, "message": "No simulation has been run yet"}

        end_text = end_file.read_text(errors="ignore")
        completed = "Successfully" in end_text

        errors, warnings = [], []
        if err_file.exists():
            for line in err_file.read_text(errors="ignore").splitlines():
                ll = line.lower()
                if "** severe" in ll or "** fatal" in ll:
                    errors.append(line.strip())
                elif "** warning" in ll:
                    warnings.append(line.strip())

        return {
            "success": True,
            "valid": completed and len(errors) == 0,
            "simulation_completed": completed,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors[:10],
            "warnings": warnings[:10],
            "end_file_content": end_text.strip(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 13: True closed-loop pipeline ───────────────────────────────────────

@mcp.tool()
def run_closed_loop(cycles: int = 3, max_self_correct_iterations: int = 3) -> dict:
    """
    Run the true end-to-end closed-loop optimization pipeline.
    For each cycle:
      1. Run EnergyPlus simulation
      2. Extract building metrics (energy, PMV, occupancy, temps)
      3. Llama 3.2 self-correction loop -> best OptimizationDecision
      4. Modify building.idf via eppy (versioned copy saved)
      5. Re-run EnergyPlus with updated IDF
      6. Rollback IDF if energy regressed vs best cycle
      7. Save cycle to history.csv
    Parameters:
        cycles:                      Number of optimization cycles to run (default 3)
        max_self_correct_iterations: Max Llama self-correction iterations per cycle (default 3)
    Returns summary of all cycles including energy, decisions, rollbacks, and timing.
    """
    try:
        import backend as bk
        cycle_results = bk.run_closed_loop(
            cycles=cycles,
            max_self_correct_iterations=max_self_correct_iterations,
        )
        successful = [r for r in cycle_results if "error" not in r]
        rolled_back = [r for r in cycle_results if r.get("rollback")]
        best = min(successful, key=lambda r: r.get("post_energy_kwh", float("inf")), default=None)
        return {
            "success": True,
            "cycles_run": len(cycle_results),
            "cycles_successful": len(successful),
            "cycles_rolled_back": len(rolled_back),
            "best_cycle": best["cycle"] if best else None,
            "best_energy_kwh": best["post_energy_kwh"] if best else None,
            "cycle_results": cycle_results,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Prompt: System prompt for AI agents ──────────────────────────────────────

@mcp.prompt()
def system_prompt() -> str:
    """Return the EcoLoop AI agent system prompt."""
    return SYSTEM_PROMPT


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
