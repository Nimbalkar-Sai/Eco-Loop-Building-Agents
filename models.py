from dataclasses import dataclass


@dataclass
class BuildingState:
    timestamp: str
    energy_kwh: float
    demand_kw: float
    cooling_kwh: float
    heating_kwh: float
    indoor_temperature: float | None = None
    outdoor_temperature: float | None = None
    humidity: float | None = None
    pmv: float | None = None
    occupancy: float | None = None
    lighting_kw: float | None = None
    carbon_intensity: float | None = None  # kg CO2/kWh — grid carbon intensity
    co2_ppm: float | None = None           # Indoor CO2 concentration (ppm) — IAQ indicator
