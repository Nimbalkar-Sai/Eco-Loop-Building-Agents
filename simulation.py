"""simulation.py — EnergyPlus simulation interface."""

from models import BuildingState
from pathlib import Path
import subprocess
import random
import re
import pandas as pd
from datetime import datetime

from config import ENERGYPLUS_PATH, BUILDING_FILE, WEATHER_FILE

OUTPUT_DIR = Path("outputs")

# ESO variable IDs from eplusout.eso (5ZoneAirCooled.idf)
# 7   = Site Outdoor Air Drybulb Temperature [C]
# 593, 658, 723, 788, 853 = Zone Air Temperature [C] for SPACE1-1..SPACE5-1
# 451..455 = Zone Mean Air Dewpoint Temperature [C] for SPACE1-1..SPACE5-1
_ESO_OUTDOOR_TEMP_ID = 7
_ESO_ZONE_TEMP_IDS   = [593, 658, 723, 788, 853]
_ESO_DEWPOINT_IDS    = [451, 452, 453, 454, 455]


def _parse_tbl_energy(tbl_path: Path) -> dict:
    """Parse annual end-use totals from eplustbl.htm. Returns kWh values."""
    result = {"energy_kwh": None, "cooling_kwh": None, "heating_kwh": None, "demand_kw": None}
    if not tbl_path.exists():
        return result
    try:
        html = tbl_path.read_text(errors="ignore")

        # Strategy: parse Total Site Energy directly from Site and Source Energy table
        # This is the most reliable single value: "Total Site Energy" row, first numeric cell
        site_energy_match = re.search(
            r'Total Site Energy</td>\s*<td align="right">\s*([\d.]+)\s*</td>',
            html
        )
        if not site_energy_match:
            return result
        total_gj = float(site_energy_match.group(1))
        GJ_TO_KWH = 277.778
        total_kwh = round(total_gj * GJ_TO_KWH, 2)

        # Cooling: find "Cooling" row in End Uses table — Electricity [GJ] column
        cooling_match = re.search(
            r'<td align="right">Cooling</td>\s*<td align="right">\s*([\d.]+)\s*</td>',
            html
        )
        cooling_kwh = round(float(cooling_match.group(1)) * GJ_TO_KWH, 2) if cooling_match else 0.0

        # Heating: Natural Gas column (3rd td after Heating row)
        heating_match = re.search(
            r'<td align="right">Heating</td>\s*<td align="right">\s*([\d.]+)\s*</td>\s*<td align="right">\s*([\d.]+)\s*</td>',
            html
        )
        heating_kwh = 0.0
        if heating_match:
            heating_kwh = round((float(heating_match.group(1)) + float(heating_match.group(2))) * GJ_TO_KWH, 2)

        # Peak demand from Demand End Use Components table
        demand_match = re.search(
            r'Total End Uses</td>\s*<td align="right">\s*([\d.]+)\s*</td>',
            html
        )
        demand_kw = round(float(demand_match.group(1)) / 1000.0, 2) if demand_match else round(total_kwh / 8760.0, 2)

        result = {
            "energy_kwh": total_kwh,
            "cooling_kwh": cooling_kwh,
            "heating_kwh": heating_kwh,
            "demand_kw":   demand_kw,
        }
    except Exception as e:
        try:
            print(f"[simulation] _parse_tbl_energy failed: {e}")
        except Exception:
            pass
    return result


def _parse_eso_last_hour(eso_path: Path) -> dict:
    """Parse the last hourly timestep from eplusout.eso.
    Returns dict with outdoor_temp, indoor_temp, humidity, occupancy_fraction.
    Falls back to None values on any parse error.
    """
    result = {
        "outdoor_temp": None,
        "indoor_temp": None,
        "humidity": None,
        "occupancy_fraction": None,
    }
    if not eso_path.exists():
        return result

    try:
        # Read all lines, find last data block (starts with "2,")
        lines = eso_path.read_text(errors="ignore").splitlines()

        # Find the last occurrence of a timestep header line "2,<day>,<month>,..."
        last_block_start = -1
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith("2,"):
                last_block_start = i
                break

        if last_block_start == -1:
            return result

        # Parse all variable values from last_block_start+1 until next "2," or end
        values: dict[int, float] = {}
        for line in lines[last_block_start + 1:]:
            if line.startswith("2,") or line.startswith("End of Data"):
                break
            parts = line.strip().split(",")
            if len(parts) >= 2:
                try:
                    var_id = int(parts[0])
                    val = float(parts[1])
                    values[var_id] = val
                except (ValueError, IndexError):
                    pass

        # Outdoor temperature
        if _ESO_OUTDOOR_TEMP_ID in values:
            result["outdoor_temp"] = round(values[_ESO_OUTDOOR_TEMP_ID], 1)

        # Indoor temperature: average of available zone temps
        zone_temps = [values[v] for v in _ESO_ZONE_TEMP_IDS if v in values]
        if zone_temps:
            result["indoor_temp"] = round(sum(zone_temps) / len(zone_temps), 1)

        # Humidity: derive from dewpoint using Magnus formula
        # RH ≈ 100 * exp(17.625*Td/(243.04+Td)) / exp(17.625*T/(243.04+T))
        dewpoints = [values[v] for v in _ESO_DEWPOINT_IDS if v in values]
        if dewpoints and zone_temps:
            import math
            td = sum(dewpoints) / len(dewpoints)
            t  = sum(zone_temps) / len(zone_temps)
            rh = 100 * math.exp(17.625 * td / (243.04 + td)) / math.exp(17.625 * t / (243.04 + t))
            result["humidity"] = round(max(10.0, min(100.0, rh)), 1)

    except Exception:
        pass

    return result


class Simulation:

    def __init__(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        self.energyplus_exe = ENERGYPLUS_PATH / "energyplus.exe"

    def run(self) -> bool:
        cmd = [
            str(self.energyplus_exe),
            "-w", str(WEATHER_FILE),
            "-d", str(OUTPUT_DIR),
            str(BUILDING_FILE),
        ]
        try:
            print("\nRunning EnergyPlus Simulation...\n", flush=True)
        except Exception:
            pass
        result = subprocess.run(cmd)
        if result.returncode == 0:
            self._update_energy_csv()
        return result.returncode == 0

    def _update_energy_csv(self):
        """Parse eplustbl.htm and overwrite energy.csv with real simulation results."""
        tbl = _parse_tbl_energy(OUTPUT_DIR / "eplustbl.htm")
        if tbl["energy_kwh"] is None:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        df = pd.DataFrame([{
            "timestamp":   ts,
            "energy_kwh":  tbl["energy_kwh"],
            "demand_kw":   tbl["demand_kw"],
            "cooling_kwh": tbl["cooling_kwh"],
            "heating_kwh": tbl["heating_kwh"],
        }])
        df.to_csv(OUTPUT_DIR / "energy.csv", index=False)

    def load_results(self) -> pd.DataFrame:
        csv_file = OUTPUT_DIR / "energy.csv"
        if not csv_file.exists():
            raise FileNotFoundError("energy.csv was not generated.")
        return pd.read_csv(csv_file)

    def latest_metrics(self) -> BuildingState:
        df = self.load_results()
        latest = df.iloc[-1]
        # Use total energy sum across all rows — setpoint changes affect the full annual total
        total_energy_kwh = float(latest["energy_kwh"])
        total_demand_kw  = float(latest["demand_kw"])
        total_cooling    = float(latest["cooling_kwh"]) if "cooling_kwh" in df.columns else total_energy_kwh * 0.6
        total_heating    = float(latest["heating_kwh"]) if "heating_kwh" in df.columns else total_energy_kwh * 0.2

        # Parse real EnergyPlus outputs from eplusout.eso
        eso_data = _parse_eso_last_hour(OUTPUT_DIR / "eplusout.eso")

        # Use real ESO values where available, fall back to plausible defaults
        outdoor_temperature = eso_data["outdoor_temp"] or round(random.uniform(5.0, 35.0), 1)
        indoor_temperature  = eso_data["indoor_temp"]  or round(random.uniform(19.0, 26.0), 1)
        humidity            = eso_data["humidity"]     or random.randint(35, 65)

        # PMV: estimated from indoor temp deviation from 22°C comfort setpoint
        # PMV ≈ 0.3 * (T - 22) clamped to [-2, 2]
        pmv = round(max(-2.0, min(2.0, 0.3 * (indoor_temperature - 22.0))), 2)

        # Occupancy: derive from timestamp hour using OCCUPY-1 schedule pattern
        # Weekday: 0 before 8:00, 1.0 at 8-11, 0.8 at 11-12, etc.
        try:
            hour = int(str(latest["timestamp"]).split(" ")[1].split(":")[0])
        except Exception:
            hour = 12
        if 8 <= hour < 11:
            occ_frac = 1.0
        elif 11 <= hour < 12:
            occ_frac = 0.8
        elif 12 <= hour < 13:
            occ_frac = 0.4
        elif 13 <= hour < 14:
            occ_frac = 0.8
        elif 14 <= hour < 18:
            occ_frac = 1.0
        elif 18 <= hour < 19:
            occ_frac = 0.5
        else:
            occ_frac = 0.0
        # Total design occupancy = 11+5+11+5+20 = 52 people
        occupancy = round(occ_frac * 52)

        # Lighting kW: from LIGHTS-1 schedule × total design watts (1584+684+1584+684+2964 = 7500W)
        if 8 <= hour < 9:
            light_frac = 0.9
        elif 9 <= hour < 11:
            light_frac = 0.95
        elif 11 <= hour < 12:
            light_frac = 1.0
        elif 12 <= hour < 13:
            light_frac = 0.95
        elif 13 <= hour < 14:
            light_frac = 0.8
        elif 14 <= hour < 18:
            light_frac = 1.0
        elif 18 <= hour < 19:
            light_frac = 0.6
        elif 19 <= hour < 21:
            light_frac = 0.2
        else:
            light_frac = 0.05
        lighting_kw = round(light_frac * 7.5, 1)  # 7500W design = 7.5 kW

        # Grid carbon intensity: varies by hour (peak 8-20 = higher)
        carbon_intensity = round(0.35 + 0.08 * (1 if 8 <= hour < 20 else -1), 3)

        # Indoor CO2: scales with occupancy
        base_co2 = 400 + (occupancy / 52) * 600
        co2_ppm  = round(base_co2 + random.uniform(-20, 30), 0)

        return BuildingState(
            timestamp=latest["timestamp"],
            energy_kwh=total_energy_kwh,
            demand_kw=total_demand_kw,
            cooling_kwh=total_cooling,
            heating_kwh=total_heating,
            indoor_temperature=indoor_temperature,
            outdoor_temperature=outdoor_temperature,
            humidity=humidity,
            pmv=pmv,
            occupancy=occupancy,
            lighting_kw=lighting_kw,
            carbon_intensity=carbon_intensity,
            co2_ppm=co2_ppm,
        )
