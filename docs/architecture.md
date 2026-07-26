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


---

## System Architecture Document

### Tool-Calling Architecture

EcoLoop AI exposes its optimization pipeline as 12 MCP tools via **FastMCP**, making every capability callable by an external AI agent or orchestrator without touching the underlying Python code directly.

Each tool maps to a single, well-scoped responsibility:

- **Simulation tools** (`run_energyplus`, `read_simulation_results`, `validate_simulation`) — isolate EnergyPlus I/O from the rest of the system. The agent calls these to get fresh physics-based data without needing to know EnergyPlus internals.
- **Building model tools** (`modify_building_model`, `apply_optimization`) — wrap eppy IDF editing behind a clean interface. The agent passes setpoints; the tool handles versioning and file writes.
- **Data tools** (`get_building_metrics`, `get_optimization_history`, `get_energy_comparison`, `get_comfort_metrics`, `get_carbon_metrics`, `get_system_status`) — read-only tools that return structured JSON, keeping the agent stateless between calls.
- **Orchestration tool** (`run_optimization`) — the top-level tool that chains simulate → AI → modify → rollback → save in one call, used when the agent wants a full closed-loop cycle without managing each step.

This design means the AI agent never directly touches files, subprocesses, or CSV state — it only calls tools and receives structured responses.

---

### Prompt Engineering Strategies

The Llama 3.2 system prompt (`prompts.py`) is structured in three layers:

**1. Role + Constraints**
The model is told it is a building energy optimization agent operating under ASHRAE 55 comfort constraints. Hard rules are stated upfront (e.g. cooling setpoint must stay between 18–28°C, PMV must stay within [-0.5, +0.5]) so the model never proposes physically unsafe or comfort-violating values.

**2. Context Injection**
Every prompt dynamically injects the current building state — occupancy, outdoor temperature, PMV, grid carbon intensity, CO₂ ppm, and energy consumption. This grounds the model in real conditions rather than relying on general knowledge.

**3. Memory Summarisation**
The last 3 optimization decisions from `_decision_memory` are appended as a compact summary (cycle number, setpoints, savings %, confidence %). This gives the model a short-term trajectory — it can see whether savings are improving or plateauing and adjust its next decision accordingly, without the prompt growing unboundedly.

**Output format enforcement:** The prompt explicitly requests a JSON-only response with fixed keys (`cooling_setpoint`, `heating_setpoint`, `lighting_level`, `fan_speed`, `reason`, `confidence`, `expected_savings_pct`). A regex-based JSON extractor in `optimizer.py` parses the response, with a fallback to safe default values if parsing fails — preventing any malformed LLM output from crashing the pipeline.

---

### Prompt Latency Management

Llama 3.2 runs locally via Ollama, so latency is bounded by local hardware rather than network round-trips. The following strategies keep LLM time low:

- **Minimal prompt size** — only the last 3 memory entries are injected (not the full history), keeping token count stable regardless of how many cycles have run.
- **Self-correction early exit** — the self-correction loop stops as soon as PMV is within range AND confidence ≥ 85%, or improvement between iterations drops below 1%. This avoids unnecessary LLM calls when the decision has already converged.
- **Parallel timing tracking** — `SimTimeSec` and `LLMTimeSec` are recorded separately per cycle (visible in the Optimization page timing chart), making it easy to identify whether bottlenecks are in EnergyPlus or the LLM.
- **No streaming** — responses are collected in full before parsing, avoiding partial-JSON parse errors that would require a retry.

---

### Handling Lengthy Simulation Logs

EnergyPlus produces verbose output files (`eplusout.err`, `eplusout.end`, `energy.csv`) that can be large and noisy. EcoLoop handles this at multiple levels:

**Selective parsing:** `simulation.py` reads only `energy.csv` for numeric results. The `.err` and `.end` files are only read when `validate_simulation()` is called or when the Simulation page expands the console output — they are never loaded into memory during normal pipeline runs.

**Truncation in UI:** The Simulation page caps the displayed error log at 3,000 characters (`ERR_FILE.read_text()[:3000]`), preventing the UI from hanging on large error files.

**Structured extraction:** Rather than passing raw EnergyPlus output to the LLM, `simulation.py` extracts only the scalar metrics needed (`energy_kwh`, `demand_kw`, `cooling_kwh`, `heating_kwh`) and populates a `BuildingState` dataclass. The LLM never sees raw simulation logs — it only sees the extracted numbers injected into the prompt.

**Error isolation:** If EnergyPlus fails mid-run, the subprocess wrapper catches the exception, logs it to `utils.py`'s event logger, and returns a failure flag. The optimizer then skips IDF modification for that cycle and optionally triggers a rollback — the rest of the pipeline continues uninterrupted.
