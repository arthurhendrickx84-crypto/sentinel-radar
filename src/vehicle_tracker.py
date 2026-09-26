"""Vehicle tracking from RF burst patterns (Blueye-style, no decoding).

A nearby emergency vehicle produces several transmissions on the SAME
C2000 uplink channel within a short window (voice press-to-talk, or
periodic status/location updates). Broadband vehicle noise does not:
it hits random channels. By clustering bursts per channel and tracking
the RSSI trend we can show whether that vehicle is approaching.
"""

import time
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class VehicleTracker:
    """Clusters bursts into per-channel tracks and derives approach trends."""

    def __init__(self, cluster_window_s: float = 60.0,
                 track_timeout_s: float = 120.0,
                 trend_delta_db: float = 3.0):
        """
        Args:
            cluster_window_s: Bursts within this window belong together
            track_timeout_s: Track expires after this much silence
            trend_delta_db: RSSI median shift that counts as trend change
        """
        self.cluster_window_s = cluster_window_s
        self.track_timeout_s = track_timeout_s
        self.trend_delta_db = trend_delta_db
        # freq_hz -> list of (time, rssi, distance)
        self._tracks: Dict[int, List[tuple]] = {}

    def feed(self, freq_hz: int, rssi_dbm: float, distance_m: float,
             now: Optional[float] = None) -> dict:
        """Add an accepted burst; returns the current nearest-track summary."""
        if now is None:
            now = time.time()

        entries = self._tracks.setdefault(freq_hz, [])
        entries.append((now, rssi_dbm, distance_m))

        # Keep only bursts inside the cluster window
        cutoff = now - self.cluster_window_s
        while entries and entries[0][0] < cutoff:
            entries.pop(0)

        # Drop tracks that have gone silent
        for f in list(self._tracks):
            if now - self._tracks[f][-1][0] > self.track_timeout_s:
                del self._tracks[f]

        return self.summary(now)

    def _trend(self, entries: List[tuple]) -> str:
        """Compare recent vs earlier RSSI medians inside a cluster."""
        if len(entries) < 4:
            return ""
        half = len(entries) // 2
        recent = sorted(r for _, r, _ in entries[half:])
        older = sorted(r for _, r, _ in entries[:half])
        delta = recent[len(recent) // 2] - older[len(older) // 2]
        if delta >= self.trend_delta_db:
            return "dichterbij"
        if delta <= -self.trend_delta_db:
            return "verder"
        return "stabiel"

    def summary(self, now: Optional[float] = None) -> dict:
        """Nearest active track: freq, distance, burst count and trend."""
        if now is None:
            now = time.time()
        best = None
        for f, entries in self._tracks.items():
            if not entries:
                continue
            last_t, last_rssi, last_dist = entries[-1]
            if now - last_t > self.track_timeout_s:
                continue
            recent = [e for e in entries if e[0] >= now - self.cluster_window_s]
            if best is None or last_dist < best['distance_m']:
                best = {
                    'freq_mhz': f / 1e6,
                    'distance_m': last_dist,
                    'rssi_dbm': last_rssi,
                    'bursts': len(recent),
                    'trend': self._trend(recent),
                }
        return best or {}
