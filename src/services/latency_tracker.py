"""
End-to-End Latency Tracker

Measures the time from when the user finishes speaking
to when the agent starts speaking (first TTS audio).

Results are written to a JSON file for analysis.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Output file path — can be overridden via env var
LATENCY_LOG_PATH = os.getenv(
    "LATENCY_LOG_PATH",
    str(Path(__file__).resolve().parents[2] / "latency_logs.json"),
)


class LatencyTracker:
    """Tracks end-to-end latency per room (user speech end → agent speech start)."""

    def __init__(self) -> None:
        self._pending: dict[str, float] = {}  # room_name → timestamp
        self._lock = Lock()

    def on_user_speech_end(self, room_name: str) -> None:
        """Call when user finishes speaking (VAD committed)."""
        with self._lock:
            self._pending[room_name] = time.perf_counter()
        logger.debug("User speech ended", room=room_name)

    def on_agent_speech_start(self, room_name: str) -> Optional[float]:
        """Call when agent starts speaking. Returns latency in ms or None."""
        with self._lock:
            t0 = self._pending.pop(room_name, None)

        if t0 is None:
            return None

        latency_s = time.perf_counter() - t0
        latency_ms = round(latency_s * 1000, 1)

        logger.info(
            "E2E latency measured",
            room=room_name,
            latency_ms=latency_ms,
        )

        self._write_to_file(room_name, latency_ms)
        return latency_ms

    def _write_to_file(self, room_name: str, latency_ms: float) -> None:
        """Append a latency entry to the JSON log file."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "room_name": room_name,
            "latency_ms": latency_ms,
        }

        try:
            path = Path(LATENCY_LOG_PATH)

            # Read existing entries
            if path.exists() and path.stat().st_size > 0:
                with open(path, "r") as f:
                    data = json.load(f)
            else:
                data = []

            data.append(entry)

            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.warning("Failed to write latency log", error=str(e))


# Singleton instance
latency_tracker = LatencyTracker()
