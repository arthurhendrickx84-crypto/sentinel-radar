"""SDR (Software Defined Radio) handler for police frequency scanning."""

import numpy as np
from rtlsdr import RtlSdr
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class SDRHandler:
    """Manages RTL-SDR dongle for frequency scanning and signal detection."""

    def __init__(self, center_freq: int, sample_rate: int = 2400000, gain: str = "auto"):
        """
        Initialize SDR handler.
        
        Args:
            center_freq: Center frequency in Hz
            sample_rate: Sample rate in Hz
            gain: Gain setting ('auto' or dB value)
        """
        self.center_freq = center_freq
        self.sample_rate = sample_rate
        self.gain = gain
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

    def estimate_distance(self, rssi_dbm: float, tx_power_dbm: float = 30, 
                         path_loss_exponent: float = 2.0) -> float:
        """
        Estimate distance from RSSI using path loss model.
        
        Formula: Distance = 10 ^ ((TxPower - RSSI) / (20 * N))
        
        Args:
            rssi_dbm: Received signal strength in dBm
            tx_power_dbm: Transmitter power in dBm
            path_loss_exponent: Path loss exponent (2.0 for free space)
            
        Returns:
            Estimated distance in meters
        """
        if rssi_dbm >= tx_power_dbm:
            return 0.1  # Very close
        
        distance = 10 ** ((tx_power_dbm - rssi_dbm) / (20 * path_loss_exponent))
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
            
            # Simple threshold: if RSSI > -80 dBm, consider signal detected
            signal_detected = rssi > -40
            
            return rssi, signal_detected
        except Exception as e:
            logger.error(f"Error scanning frequency: {e}")
            return -100.0, False

    def disconnect(self):
        """Disconnect from SDR."""
        if self.sdr:
            self.sdr.close()
            self.is_connected = False
            logger.info("SDR disconnected")

    def __del__(self):
        """Cleanup on deletion."""
        self.disconnect()
