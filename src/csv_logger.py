"""CSV logging for Sentinel Radar rides.

Every application start creates a new timestamped CSV file so each ride
gets its own log. Rows are flushed immediately so data survives a power
loss (important for in-car use with a Pi).
"""

import csv
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class CSVLogger:
    """Writes ride data (bursts, alert changes, background scans) to CSV."""

    def __init__(self, log_dir: str = "~/radar_logs", enabled: bool = True,
                 log_all_scans: bool = False):
        """
        Args:
            log_dir: Directory for ride CSV files (~ is expanded)
            enabled: Master switch; when False everything is a no-op
            log_all_scans: Also log every background scan (noisier, but
                           useful for noise-floor analysis afterwards)
        """
        self.enabled = enabled
        self.log_all_scans = log_all_scans
        self._fh = None
        self._writer = None
        self.path = None

        if not enabled:
            logger.info("CSV logging disabled")
            return

        try:
            directory = Path(os.path.expanduser(log_dir))
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.path = directory / f"ride_{stamp}.csv"
            self._fh = open(self.path, "a", newline="")
            self._writer = csv.writer(self._fh)
            self._writer.writerow([
                "timestamp", "event", "freq_mhz", "rssi_dbm",
                "distance_m", "indicators", "alarm", "extra"
            ])
            self._fh.flush()
            logger.info(f"CSV logging: {self.path}")
        except Exception as e:
            logger.error(f"CSV logging init failed: {e}")
            self.enabled = False

    def _write(self, event: str, freq_mhz="", rssi_dbm="", distance_m="",
               indicators="", alarm="", extra=""):
        if not self.enabled or self._writer is None:
            return
        try:
            self._writer.writerow([
                datetime.now().isoformat(timespec="milliseconds"),
                event, freq_mhz, rssi_dbm, distance_m,
                indicators, alarm, extra
            ])
            self._fh.flush()
        except Exception as e:
            logger.error(f"CSV write failed: {e}")

    def log_burst(self, freq_hz: float, rssi_dbm: float, distance_m: float,
                  accepted: bool = True):
        """Log a detected signal burst (accepted = within max distance)."""
        self._write("burst" if accepted else "burst_far",
                    freq_mhz=round(freq_hz / 1e6, 4),
                    rssi_dbm=round(rssi_dbm, 1),
                    distance_m=round(distance_m, 1))

    def log_alert(self, indicators: int, distance_m: float, alarm: bool):
        """Log an alert level change."""
        self._write("alert", distance_m=round(distance_m, 1),
                    indicators=indicators, alarm=alarm)

    def log_scan(self, freq_hz: float, rssi_dbm: float):
        """Log a background scan result (noise floor tracking)."""
        self._write("scan", freq_mhz=round(freq_hz / 1e6, 4),
                    rssi_dbm=round(rssi_dbm, 1))

    def close(self):
        if self._fh:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            logger.info(f"CSV log closed: {self.path}")
