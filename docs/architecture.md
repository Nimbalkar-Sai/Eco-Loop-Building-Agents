# EcoLoop AI — Architecture & Technical Reference

---

## System Architecture

![Architecture](../assets/architecture.png)

---

## Autonomous Optimization Loop

```
Run EnergyPlus Baseline Simulation
              │
              ▼
Extract Metrics
  energy_kwh, demand_kw, cooling_kwh, heating_kwh
  indoor_temperature, outdoor_temperature, humidity
  pmv, occupancy, lighting_kw, carbon_intensity
              │
              ▼
Llama 3.2 AI Agent — Self-Correction Loop
  ┌─────────────────────────────────────────┐
  │  Iteration 1: Generate decision         │
  │  Score = savings% + (20 if PMV OK)      │
  │  Stop if: PMV OK + confidence ≥ 85%     │
  │        or: improvement < 1%             │
  │        or: max iterations reached       │
  │  Iteration 2, 3 ... → pick best score   │
  └─────────────────────────────────────────┘
              │
              ▼
OptimizationDecision
  { cooling_setpoint, heating_setpoint,
    lighting_level, fan_speed,
    reason, confidence, expected_savings_pct }
              │
              ▼
Modify IDF via eppy
  → Save versioned copy: outputs/idf_versions/iteration_N.idf
  → Baseline preserved: outputs/idf_versions/baseline.idf
              │
              ▼
Energy worse than best cycle?
  YES → Rollback IDF to best cycle
  NO  → Update best cycle record
              │
              ▼
Save to history.csv → Repeat N Cycles
```

---

## Self-Correction Algorithm

```
Score = expected_savings_pct + (20 bonus if PMV within [-0.5, +0.5])

Stopping conditions (whichever comes first):
  1. PMV within [-0.5, +0.5] AND confidence ≥ 85%  → converged
  2. Improvement between iterations < 1%             → marginal gain, stop
  3. max_iterations reached                          → hard stop
```

---

## AI Memory

All decisions from the current session are stored in `_decision_memory`. The last 3 are summarised and injected into every LLM prompt:

```
Previous optimization cycles (7 total, showing last 3):
  Cycle 5: cooling=24.0°C, fan=65%, lighting=80%, savings=6.2%, confidence=88%
  Cycle 6: cooling=24.5°C, fan=60%, lighting=75%, savings=8.1%, confidence=91%
  Cycle 7: cooling=25.0°C, fan=55%, lighting=70%, savings=9.3%, confidence=93%
```

---

## AI Awareness Rules

**Occupancy Awareness**
- Occupancy = 0 → raise cooling setpoint 26°C, lighting 50%, fan 50%
- Occupancy ≥ 10 → cooling setpoint 22–24°C for comfort

**Weather Awareness**
- Outdoor temp > 38°C → lower cooling setpoint by 1°C
- Outdoor temp > 30°C → moderate cooling
- Outdoor temp < 20°C → raise heating setpoint, reduce cooling
- Outdoor temp 20–30°C → raise cooling setpoint to save energy

**Carbon Intensity Awareness**
- Grid carbon > 0.4 kg/kWh → aggressively reduce HVAC load
- Grid carbon < 0.2 kg/kWh → comfort can take priority

**Comfort Rules (ASHRAE 55)**
- Keep PMV between -0.5 and +0.5
- PMV > 0.7 → lower cooling setpoint immediately
- PMV < -0.7 → raise heating setpoint immediately

---

## IDF Versioning & Rollback

```
outputs/idf_versions/
├── baseline.idf       ← original, written once, never overwritten
├── iteration_1.idf
├── iteration_2.idf
└── iteration_3.idf
```

Rollback triggers when:
- EnergyPlus fails after an IDF modification
- Current cycle energy is >1% worse than the best recorded cycle

---

## MCP Server — 12 Tools

| # | Tool | Description |
|---|---|---|
| 1 | `run_optimization()` | Full pipeline: simulate → AI → modify IDF → save history |
| 2 | `get_building_metrics()` | Latest sensor and simulation data |
| 3 | `get_optimization_history()` | All past cycles and summary statistics |
| 4 | `get_energy_comparison()` | Before vs after energy savings |
| 5 | `get_comfort_metrics()` | PMV, PPD, comfort score, ASHRAE 55 compliance |
| 6 | `get_carbon_metrics()` | Daily/monthly/annual CO₂, trees saved |
| 7 | `get_system_status()` | EnergyPlus, Ollama, LLM model (`ollama.list().models`), history DB status |
| 8 | `apply_optimization()` | Push custom setpoints directly to IDF |
| 9 | `run_energyplus()` | Execute EnergyPlus simulation standalone |
| 10 | `read_simulation_results()` | Parse and return raw energy.csv output |
| 11 | `modify_building_model()` | Modify IDF with versioned file saving |
| 12 | `validate_simulation()` | Inspect eplusout.end/.err for errors and warnings |

**Plus 1 prompt:** `system_prompt()` — returns the full Llama 3.2 system prompt.

---

## Optimization History Schema

`outputs/history.csv` — one row per optimization cycle:

| Column | Description |
|---|---|
| `Timestamp` | Date and time of the cycle |
| `Cycle` | Cycle number |
| `Energy` | Energy consumption (kWh) |
| `Demand` | Peak demand (kW) |
| `IndoorTemp` | Indoor temperature (°C) |
| `OutdoorTemp` | Outdoor temperature (°C) |
| `Humidity` | Relative humidity (%) |
| `PMV` | Predicted Mean Vote |
| `Occupancy` | Number of occupants |
| `CoolingSP` | AI-decided cooling setpoint (°C) |
| `HeatingSP` | AI-decided heating setpoint (°C) |
| `Lighting` | AI-decided lighting level (%) |
| `Fan` | AI-decided fan speed (%) |
| `Confidence` | AI confidence score (0–100%) |
| `ExpectedSavings` | AI-estimated energy savings (%) |
| `Reason` | Full AI explanation text |
| `SimTimeSec` | EnergyPlus simulation time (seconds) |
| `LLMTimeSec` | Llama 3.2 response time (seconds) |
| `TotalTimeSec` | Total elapsed time (seconds) |

---

## File Responsibilities

| File | Responsibility |
|---|---|
| `app.py` | Streamlit entry point — premium sidebar, navigation, page routing |
| `backend.py` | Data-access layer — KPI calculations, pipeline runner, report exports |
| `simulation.py` | EnergyPlus subprocess wrapper — runs simulation, reads energy.csv |
| `optimizer.py` | Llama 3.2 AI engine — retry logic, session memory, self-correction |
| `idf_modifier.py` | IDF editor — applies decisions via eppy, versioned copies, rollback |
| `history.py` | CSV persistence — saves all cycle data including timing |
| `decision.py` | `OptimizationDecision` dataclass |
| `models.py` | `BuildingState` dataclass |
| `prompts.py` | Llama 3.2 system prompt |
| `report_generator.py` | reportlab PDF builder |
| `mcp_server.py` | FastMCP server — 12 tools + 1 prompt |
| `config.py` | EnergyPlus paths |
| `utils.py` | CSV save helper, event logger |
