"""idf_modifier.py — Modifies IDF setpoints via direct text replacement. Keeps versioned copies and supports rollback."""

import re
import shutil
from pathlib import Path

from config import BUILDING_FILE
from decision import OptimizationDecision

VERSIONS_DIR = Path("outputs/idf_versions")
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_IDF = VERSIONS_DIR / "baseline.idf"


class IDFModifier:

    def __init__(self):
        if not BASELINE_IDF.exists() and BUILDING_FILE.exists():
            shutil.copy2(BUILDING_FILE, BASELINE_IDF)

    def _set_schedule_values(self, text: str, schedule_name: str, value: float) -> str:
        """
        Find the SCHEDULE:COMPACT block by name and replace all numeric value
        fields (lines like '    24.0,  !- Field N') with the new value.
        """
        name_idx = text.lower().find(schedule_name.lower())
        if name_idx == -1:
            return text

        block_start = text.rfind('SCHEDULE:COMPACT', 0, name_idx)
        if block_start == -1:
            block_start = text.lower().rfind('schedule:compact', 0, name_idx)
        if block_start == -1:
            return text

        # End of block = next line that starts at column 0 with a letter (next IDF object)
        next_obj = re.search(r'\n[A-Za-z]', text[block_start + 20:])
        block_end = (block_start + 20 + next_obj.start() + 1) if next_obj else len(text)

        block = text[block_start:block_end]

        # Replace lines whose only content (before the comment) is a number
        new_block = re.sub(
            r'^([ \t]+)([0-9]+(?:\.[0-9]*)?)(,[ \t]*(?:!-[^\n]*)?)$',
            lambda m: m.group(1) + str(value) + m.group(3),
            block,
            flags=re.MULTILINE,
        )

        return text[:block_start] + new_block + text[block_end:]

    def _set_fan_min_flow(self, text: str, value: float) -> str:
        """Replace Fan_Power_Minimum_Flow_Fraction in FAN:VARIABLEVOLUME block."""
        pattern = re.compile(
            r'(Fan_Power_Minimum_Flow_Fraction\s*[,;]\s*\n\s*)([0-9.]+)',
            re.IGNORECASE,
        )
        # FAN:VARIABLEVOLUME uses positional fields, not keyword fields.
        # The minimum flow fraction is the 9th field. Use a targeted field replacement.
        # Find FAN:VARIABLEVOLUME block and replace the minimum flow fraction field.
        fan_pattern = re.compile(
            r'(FAN:VARIABLEVOLUME\s*,.*?)(,\s*\n\s*)([0-9.]+)(\s*,\s*\n\s*[0-9.]+\s*,\s*\n\s*[0-9.]+\s*,\s*\n\s*[0-9.]+\s*[,;])',
            re.IGNORECASE | re.DOTALL,
        )
        # Simpler: just find the line with the current min flow fraction value after
        # "Fan Power Minimum Flow Fraction" comment or positionally.
        # Most reliable: regex on the known field order in 5ZoneAirCooled.idf
        # Field order: Name, Availability Schedule, Design Max Flow Rate,
        #   Speed Control Method, Min Flow Rate, Min Flow Fraction, ...
        # Use a direct search for the numeric field after FAN:VARIABLEVOLUME
        result = re.sub(
            r'(FAN:VARIABLEVOLUME\s*,[^\n]*\n'   # object header
            r'(?:[^\n]*\n){7})'                   # skip 7 fields (name + 6 others)
            r'(\s*)([0-9.]+)',                     # capture indent + current value
            lambda m: m.group(1) + m.group(2) + str(round(value, 4)),
            text,
            flags=re.IGNORECASE,
        )
        return result

    def apply(self, decision: OptimizationDecision, cycle: int = None) -> Path:
        cooling   = max(decision.cooling_setpoint, decision.heating_setpoint + 2.0)
        heating   = min(decision.heating_setpoint, cooling - 2.0)
        light_frac = max(0.0, min(1.0, decision.lighting_level / 100.0))
        fan_frac   = max(0.2, min(0.8, decision.fan_speed / 100.0))

        text = BUILDING_FILE.read_text(encoding="utf-8", errors="ignore")

        text = self._set_schedule_values(text, "Clg-SetP-Sch", cooling)
        text = self._set_schedule_values(text, "Htg-SetP-Sch", heating)
        text = self._set_schedule_values(text, "LIGHTS-1", light_frac)
        text = self._set_fan_min_flow(text, fan_frac)

        BUILDING_FILE.write_text(text, encoding="utf-8")

        label = f"iteration_{cycle}" if cycle is not None else "latest"
        versioned = VERSIONS_DIR / f"{label}.idf"
        shutil.copy2(BUILDING_FILE, versioned)

        return versioned

    def rollback(self, cycle: int = None):
        if cycle is not None:
            source = VERSIONS_DIR / f"iteration_{cycle}.idf"
            if source.exists():
                shutil.copy2(source, BUILDING_FILE)
                return True
        if BASELINE_IDF.exists():
            shutil.copy2(BASELINE_IDF, BUILDING_FILE)
            return True
        return False
