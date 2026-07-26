"""
Utils - Shared helpers for file I/O and logging.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    filename="outputs/logs.csv",
    level=logging.INFO,
    format="%(asctime)s,%(levelname)s,%(message)s",
)


def save_csv(data: dict, path: str):
    """Save a flat dict or list of dicts to CSV."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows = data if isinstance(data, list) else [data]
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def log_event(event: str, payload: dict = None):
    """Log a named event with optional JSON payload."""
    msg = event if payload is None else f"{event} | {json.dumps(payload, default=str)}"
    logging.info(msg)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
