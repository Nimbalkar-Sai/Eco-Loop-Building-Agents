from dataclasses import dataclass, field


@dataclass
class OptimizationDecision:
    cooling_setpoint: float = 24.0
    heating_setpoint: float = 20.0
    lighting_level: int = 100
    fan_speed: int = 70
    reason: str = "Default optimization"
    confidence: float = 80.0          # 0–100 %
    expected_savings_pct: float = 0.0  # estimated energy saving %
