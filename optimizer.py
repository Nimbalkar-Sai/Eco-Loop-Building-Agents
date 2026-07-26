"""
optimizer.py — Llama 3.2 AI optimization engine.
Features: retry logic, full AI memory, self-correction, occupancy/weather/carbon awareness.
"""

import json
import ollama

from prompts import SYSTEM_PROMPT
from decision import OptimizationDecision
from models import BuildingState

_DEFAULTS = {
    "cooling_setpoint": 24.0,
    "heating_setpoint": 20.0,
    "lighting_level": 80,
    "fan_speed": 65,
    "reason": "Fallback: default safe settings applied.",
    "confidence": 60.0,
    "expected_savings_pct": 0.0,
}

# Full in-memory history — all decisions this session
_decision_memory: list[dict] = []


def _call_llm(messages: list[dict], retries: int = 3) -> dict:
    """Call Ollama with retry logic. Returns parsed dict or raises."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            response = ollama.chat(
                model="llama3.2",
                format="json",
                messages=messages,
            )
            text = response["message"]["content"]
            data = json.loads(text)
            required = {"cooling_setpoint", "heating_setpoint", "lighting_level",
                        "fan_speed", "reason"}
            if not required.issubset(data.keys()):
                raise ValueError(f"Missing keys: {required - data.keys()}")
            return data
        except Exception as e:
            last_err = e
            try:
                print(f"[Optimizer] Attempt {attempt} failed: {e}")
            except Exception:
                pass
    raise RuntimeError(f"LLM failed after {retries} retries: {last_err}")


def _build_memory_context() -> str:
    """Summarise last 3 decisions for the LLM prompt (full history kept in _decision_memory)."""
    if not _decision_memory:
        return "No previous optimization cycles."
    lines = [f"Previous optimization cycles ({len(_decision_memory)} total, showing last 3):"]
    for i, m in enumerate(_decision_memory[-3:], 1):
        lines.append(
            f"  Cycle {i}: cooling={m['cooling_setpoint']}°C, "
            f"fan={m['fan_speed']}%, lighting={m['lighting_level']}%, "
            f"savings={m.get('expected_savings_pct', 0)}%, "
            f"confidence={m.get('confidence', 0)}%"
        )
    return "\n".join(lines)


def _build_prompt(state: BuildingState) -> str:
    carbon_str = f"{state.carbon_intensity:.3f} kg CO₂/kWh" if getattr(state, 'carbon_intensity', None) else "unknown"
    co2_str = f"{int(state.co2_ppm)} ppm" if getattr(state, 'co2_ppm', None) else "unknown"
    iaq_context = ""
    if getattr(state, 'co2_ppm', None):
        if state.co2_ppm > 1200:
            iaq_context = "POOR IAQ — prioritize ventilation"
        elif state.co2_ppm > 1000:
            iaq_context = "Elevated CO₂ — increase fan speed"
        else:
            iaq_context = "Good air quality"
    occ_context = (
        "UNOCCUPIED — maximize energy savings" if (state.occupancy or 0) == 0
        else f"{int(state.occupancy)} people present"
    )
    weather_context = ""
    if state.outdoor_temperature:
        if state.outdoor_temperature > 38:
            weather_context = "EXTREME HEAT — high cooling demand expected"
        elif state.outdoor_temperature > 30:
            weather_context = "Hot day — moderate cooling needed"
        elif state.outdoor_temperature < 20:
            weather_context = "Cool day — reduce cooling, check heating"
        else:
            weather_context = "Mild weather — opportunity to save energy"

    return f"""
Current Building State
======================
Timestamp:           {state.timestamp}
Energy Consumption:  {state.energy_kwh:.2f} kWh
Peak Demand:         {state.demand_kw:.2f} kW
Cooling Energy:      {state.cooling_kwh:.2f} kWh
Heating Energy:      {state.heating_kwh:.2f} kWh
Indoor Temperature:  {state.indoor_temperature} °C
Outdoor Temperature: {state.outdoor_temperature} °C  → {weather_context}
Humidity:            {state.humidity} %
PMV:                 {state.pmv}
Occupancy:           {occ_context}
Lighting Load:       {state.lighting_kw} kW
Grid Carbon:         {carbon_str}
Indoor CO₂ (IAQ):   {co2_str}  → {iaq_context}

{_build_memory_context()}

Analyze the above and return the optimal building settings as JSON.
"""


class Optimizer:

    def optimize(self, state: BuildingState) -> OptimizationDecision:
        """Single optimization call with retry logic."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": _build_prompt(state)},
        ]
        try:
            data = _call_llm(messages)
        except Exception as e:
            try:
                print(f"[Optimizer] Using fallback defaults. Error: {e}")
            except Exception:
                pass
            data = {}

        for key, val in _DEFAULTS.items():
            if data.get(key) is None:
                data[key] = val

        data["cooling_setpoint"] = max(18.0, min(30.0, float(data["cooling_setpoint"])))
        data["heating_setpoint"] = max(15.0, min(25.0, float(data["heating_setpoint"])))
        if data["cooling_setpoint"] <= data["heating_setpoint"] + 2.0:
            data["cooling_setpoint"] = data["heating_setpoint"] + 2.0

        # Enforce lighting floor based on occupancy
        occupancy = getattr(state, "occupancy", 0) or 0
        if occupancy >= 10:
            min_light = 60
        elif occupancy >= 1:
            min_light = 40
        else:
            min_light = 10
        data["lighting_level"] = max(min_light, min(100, int(data["lighting_level"])))
        data["fan_speed"]       = max(20 if occupancy == 0 else 40, min(80, int(data["fan_speed"])))
        data["confidence"]       = max(0.0,  min(100.0, float(data.get("confidence", 80.0))))
        data["expected_savings_pct"] = max(0.0, min(20.0, float(data.get("expected_savings_pct", 0.0))))

        # Store full record in memory
        _decision_memory.append(data)

        return OptimizationDecision(**{k: data[k] for k in _DEFAULTS})

    def self_correct(
        self,
        state: BuildingState,
        max_iterations: int = 3,
        target_pmv_range: tuple = (-0.5, 0.5),
        min_improvement_pct: float = 1.0,
        log_fn=None,
    ) -> tuple[OptimizationDecision, list[dict]]:
        """
        Self-correction loop: optimize → score → repeat until stopping condition.
        Stopping conditions:
          - PMV within target AND confidence >= 85%
          - Improvement between iterations < min_improvement_pct
          - max_iterations reached
        Returns (best_decision, iteration_log).
        """
        iteration_log = []
        best_decision = None
        best_score = -1
        prev_savings = None

        for i in range(1, max_iterations + 1):
            if log_fn:
                log_fn(f"   [SC] Self-correction iteration {i}/{max_iterations}...")

            decision = self.optimize(state)
            comfort_ok = target_pmv_range[0] <= (state.pmv or 0) <= target_pmv_range[1]
            score = decision.expected_savings_pct + (20 if comfort_ok else 0)

            iteration_log.append({
                "iteration": i,
                "cooling_setpoint": decision.cooling_setpoint,
                "heating_setpoint": decision.heating_setpoint,
                "lighting_level": decision.lighting_level,
                "fan_speed": decision.fan_speed,
                "confidence": decision.confidence,
                "expected_savings_pct": decision.expected_savings_pct,
                "pmv_ok": comfort_ok,
                "score": score,
                "reason": decision.reason,
            })

            if log_fn:
                log_fn(
                    f"   [SC] Iteration {i}: savings={decision.expected_savings_pct:.1f}%, "
                    f"confidence={decision.confidence:.0f}%, PMV OK={comfort_ok}"
                )

            if score > best_score:
                best_score = score
                best_decision = decision

            # Stopping condition 1: comfort satisfied + high confidence
            if comfort_ok and decision.confidence >= 85:
                if log_fn:
                    log_fn(f"   [SC] Converged at iteration {i} - comfort OK + confidence high")
                break

            # Stopping condition 2: marginal improvement
            if prev_savings is not None:
                improvement = decision.expected_savings_pct - prev_savings
                if improvement < min_improvement_pct:
                    if log_fn:
                        log_fn(f"   [SC] Stopping - improvement {improvement:.1f}% < threshold {min_improvement_pct}%")
                    break

            prev_savings = decision.expected_savings_pct

        return best_decision, iteration_log
