"""SDR (Software Defined Radio) handler for police frequency scanning."""

import numpy as np
from rtlsdr import RtlSdr
import logging
import time
from collections import deque
from typing import Optional, Tuple, List, Set

logger = logging.getLogger(__name__)


class SDRHandler:
    """Manages RTL-SDR dongle for frequency scanning and signal detection."""

    def __init__(self, center_freq: int, sample_rate: int = 2400000, gain: str = "auto",
                 detection_threshold_dbm: float = -40.0,
                 scan_frequencies: Optional[List[int]] = None,
                 detection_margin_db: float = 6.0,
                 min_burst_rssi_dbm: float = -52.0,
                 noise_correlation_window_s: float = 0.4):
        """
        Initialize SDR handler.
        
        Args:
            center_freq: Center frequency in Hz
            sample_rate: Sample rate in Hz
            gain: Gain setting ('auto' or dB value)
            detection_threshold_dbm: Absolute fallback threshold in dBm
            scan_frequencies: List of frequencies to round-robin scan. If None,
                              only center_freq is scanned.
            detection_margin_db: Burst must exceed the per-frequency noise
                                 baseline by this many dB to count as detected
        """
        self.center_freq = center_freq
        self.sample_rate = sample_rate
        self.gain = gain
        self.detection_threshold_dbm = detection_threshold_dbm
        self.scan_freqs: List[int] = scan_frequencies if scan_frequencies else [center_freq]
        self._scan_idx = 0
        self.detection_margin_db = detection_margin_db
        self._baselines = {f: deque(maxlen=10) for f in self.scan_freqs}
        
        # Mast filter: fixed base stations transmit nearly continuously on a
        # frequency, mobile radios transmit in short bursts. Track carrier
        # streaks and duty cycle per frequency and suppress "always-on"
        # carriers so only mobile transmitters trigger alerts.
        self.mast_hold_s = 12.0          # continuous carrier this long = mast
        self.mast_duty_threshold = 0.8   # >80% of recent scans above baseline = mast
        self._carrier_start: dict = {f: None for f in self.scan_freqs}
        self._above_history = {f: deque(maxlen=40) for f in self.scan_freqs}
        self._mast_flags: Set[int] = set()
        self.mast_suppressed_count = 0
        
        # Broadband-noise rejection: a real TETRA burst occupies ONE channel.
        # Vehicle electronics (ignition, alternator, SMPS) produce broadband
        # noise that lights up multiple channels at (nearly) the same moment.
        # If another channel burst recently, treat the current burst as noise.
        self.min_burst_rssi_dbm = min_burst_rssi_dbm
        self.noise_window_s = noise_correlation_window_s
        self._last_burst_time: dict = {f: 0.0 for f in self.scan_freqs}
        self.noise_rejected_count = 0
        
        self.sdr: Optional[RtlSdr] = None
        self.is_connected = False

    def connect(self) -> bool:
        """Connect to RTL-SDR dongle."""
        try:
            self.sdr = RtlSdr()
            self.sdr.sample_rate = self.sample_rate
            self.sdr.center_freq = self.center_freq
            
            if self.gain == "auto":
                self.sdr.gain = "auto"
            else:
                self.sdr.gain = int(self.gain)
            
            self.is_connected = True
            logger.info(f"SDR connected: {self.center_freq/1e6:.1f} MHz, {self.sample_rate/1e6:.1f} MS/s")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SDR: {e}")
            return False

    def read_samples(self, num_samples: int = 16384) -> Optional[np.ndarray]:
        """Read samples from SDR."""
        if not self.is_connected or self.sdr is None:
            return None
        
        try:
            samples = self.sdr.read_samples(num_samples)
            return samples
        except Exception as e:
            logger.error(f"Error reading samples: {e}")
            return None

    def get_rssi(self, samples: np.ndarray) -> float:
        """
        Calculate RSSI (Received Signal Strength Indicator) from samples.
        
        Args:
            samples: Complex IQ samples from SDR
            
        Returns:
            RSSI in dBm
        """
        # Calculate power
        power = np.mean(np.abs(samples) ** 2)
        
        # Convert to dBm (assuming 50 ohm impedance)
        rssi_dbm = 10 * np.log10(power) - 30
        
        return rssi_dbm

    def estimate_distance(self, rssi_dbm: float,
                         ref_distance_m: float = 3.0,
                         ref_rssi_dbm: float = -36.4,
                         path_loss_exponent: float = 3.0) -> float:
        """
        Estimate distance from RSSI, anchored to a measured reference point.
        
        Anchor: C2000 mobile radio (2 W) at 3 m measured -36.4 dBm during a
        test ride (ambulance alongside, 2026-09-26 20:09). The RTL-SDR RSSI
        is uncalibrated (depends on gain setting), so absolute path-loss
        formulas are misleading; we scale relative to the anchor instead.
        
        Formula: d = ref_d * 10 ^ ((ref_rssi - rssi) / (10 * n))
        
        Args:
            rssi_dbm: Received signal strength (pipeline units)
            ref_distance_m: Distance of the calibration anchor in meters
            ref_rssi_dbm: RSSI measured at the anchor distance
            path_loss_exponent: n (2 = free space, 3+ = obstructed; needs
                                more anchor points to pin down precisely)
            
        Returns:
            Estimated distance in meters (min 1 m)
        """
        if rssi_dbm >= ref_rssi_dbm + 20:
            return 0.5  # extremely close / receiver saturated
        
        distance = ref_distance_m * 10 ** (
            (ref_rssi_dbm - rssi_dbm) / (10 * path_loss_exponent))
        return max(distance, 1.0)  # At least 1 meter

    def scan_frequency(self, freq_hz: int, duration_s: float = 1.0) -> Tuple[float, bool]:
        """
        Scan a specific frequency and detect if signal is present.
        
        Args:
            freq_hz: Frequency to scan in Hz
            duration_s: Scan duration in seconds
            
        Returns:
            Tuple of (rssi_dbm, signal_detected)
        """
        if not self.is_connected or self.sdr is None:
            return -100.0, False
        
        try:
            self.sdr.center_freq = freq_hz
            num_samples = min(16384, int(self.sample_rate * duration_s))
            samples = self.sdr.read_samples(num_samples)
            
            rssi = self.get_rssi(samples)
            
            # Signal detection threshold (configurable via settings.json)
            signal_detected = rssi > self.detection_threshold_dbm and \
                freq_hz not in self._mast_flags
            
            return rssi, signal_detected
        except Exception as e:
            logger.error(f"Error scanning frequency: {e}")
            return -100.0, False

    def scan_next(self) -> Tuple[float, bool, int]:
        """
        Scan the next frequency round-robin with adaptive baseline detection.
        
        Each frequency keeps a rolling noise baseline (median of recent reads).
        A signal counts as detected when the current RSSI exceeds
        baseline + detection_margin_db — so passing transmitters stand out
        while constant beacons and noise floors do not.
        
        Returns:
            Tuple of (rssi_dbm, signal_detected, scanned_freq_hz)
        """
        if not self.is_connected or self.sdr is None:
            return -100.0, False, 0
        
        freq = self.scan_freqs[self._scan_idx % len(self.scan_freqs)]
        self._scan_idx += 1
        
        try:
            self.sdr.center_freq = freq
            samples = self.sdr.read_samples(16384)
            rssi = self.get_rssi(samples)
            
            base = self._baselines[freq]
            base.append(rssi)
            
            if len(base) < 4:
                return rssi, False, freq  # baseline still warming up
            
            baseline = float(np.median(base))
            is_above = rssi > baseline + self.detection_margin_db
            
            # --- Mast filter: carrier streak + duty cycle tracking ---
            now = time.monotonic()
            hist = self._above_history[freq]
            hist.append(is_above)
            
            if is_above:
                if self._carrier_start[freq] is None:
                    self._carrier_start[freq] = now
                streak_s = now - self._carrier_start[freq]
            else:
                self._carrier_start[freq] = None
                streak_s = 0.0
            
            if len(hist) >= 10:
                duty = sum(hist) / len(hist)
                if duty >= self.mast_duty_threshold and freq not in self._mast_flags:
                    self._mast_flags.add(freq)
                    logger.info(f"Mast filter ON: {freq/1e6:.3f} MHz "
                                f"duty cycle {duty:.0%} -> suppressed (base station)")
                elif duty < 0.3 and freq in self._mast_flags:
                    self._mast_flags.discard(freq)
                    logger.info(f"Mast filter OFF: {freq/1e6:.3f} MHz "
                                f"duty cycle {duty:.0%} -> mobile bursts possible again")
            
            mast_suspect = streak_s >= self.mast_hold_s or freq in self._mast_flags
            
            if is_above and mast_suspect:
                self.mast_suppressed_count += 1
                signal_detected = False
            elif is_above:
                # Stamp this above-baseline event, then apply noise rules
                self._last_burst_time[freq] = now
                
                recent_other = [f2 for f2, t2 in self._last_burst_time.items()
                                if f2 != freq and now - t2 <= self.noise_window_s]
                if recent_other:
                    # Multiple channels active at once -> broadband noise
                    self.noise_rejected_count += 1
                    signal_detected = False
                elif rssi < self.min_burst_rssi_dbm:
                    # Too weak to stand out above vehicle noise floor
                    self.noise_rejected_count += 1
                    signal_detected = False
                else:
                    signal_detected = True
            else:
                signal_detected = False
            
            return rssi, signal_detected, freq
        except Exception as e:
            logger.error(f"Error scanning {freq/1e6:.3f} MHz: {e}")
            return -100.0, False, freq

    def disconnect(self):
        """Disconnect from SDR."""
        if self.sdr:
            self.sdr.close()
            self.is_connected = False
            logger.info("SDR disconnected")

    def __del__(self):
        """Cleanup on deletion."""
        self.disconnect()
