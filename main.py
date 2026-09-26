#!/usr/bin/env python3
"""Sentinel Radar - Main application."""

import sys
import logging
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import cv2

from src.sdr_handler import SDRHandler
from src.camera_handler import CameraHandler
from src.motion_detector import MotionDetector
from src.alert_system import AlertSystem
from src.display_handler import DisplayHandler
from src.sound_alert import SoundAlert
from src.csv_logger import CSVLogger
from src.vehicle_tracker import VehicleTracker
from src.telegram_alert import TelegramAlert

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SentinelRadar:
    """Main Sentinel Radar application."""
    
    def __init__(self, config_file: str = "config/settings.json", 
                 frequencies_file: str = "config/frequencies.json"):
        """
        Initialize Sentinel Radar.
        
        Args:
            config_file: Path to settings JSON
            frequencies_file: Path to frequencies JSON
        """
        self.config = self._load_config(config_file)
        self.frequencies_db = self._load_frequencies(frequencies_file)
        
        # Components
        self.sdr: Optional[SDRHandler] = None
        self.camera: Optional[CameraHandler] = None
        self.motion_detector: Optional[MotionDetector] = None
        self.alert_system: Optional[AlertSystem] = None
        self.display: Optional[DisplayHandler] = None
        self.sound_alert: Optional[SoundAlert] = None
        self.csv: Optional[CSVLogger] = None
        self.tracker: Optional[VehicleTracker] = None
        self.telegram: Optional[TelegramAlert] = None
        
        self.running = False
        self.last_alert_level = -1  # Track alert level changes for INFO logging
        self._sync_check_time = 0.0
        self._sync_ok = True       # NTP-sync status, refreshed every 30 s
        self._unsynced_since = 0.0 # When the clock became unsynced
        self.last_distance_m = 9999.0   # Last valid distance, held between scans
        self.last_detect_time = 0.0     # Timestamp of last successful detection
        self.signal_hold_s = 5.0        # Keep detection alive this long without new signal
        self.last_detection_info = None # Last accepted burst, for the persistent display line
        self.last_track = {}            # Nearest vehicle track summary for display

    def _load_config(self, config_file: str) -> dict:
        """Load configuration from JSON."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def _load_frequencies(self, frequencies_file: str) -> dict:
        """Load frequency database."""
        try:
            with open(frequencies_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading frequencies: {e}")
            return {}

    def initialize(self, country: str = "nl", debug: bool = False):
        """Initialize all components."""
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
        
        logger.info(f"Initializing Sentinel Radar for {country}...")
        
        # Load country frequencies
        if country not in self.frequencies_db['countries']:
            logger.error(f"Country {country} not supported")
            return False
        
        country_config = self.frequencies_db['countries'][country]
        primary_freq = country_config['frequencies'][0]['center_freq']
        
        # Initialize SDR
        logger.info("Initializing SDR...")
        self.sdr = SDRHandler(
            center_freq=primary_freq,
            sample_rate=self.config['sdr']['sample_rate'],
            gain=self.config['sdr']['gain'],
            detection_threshold_dbm=self.config['sdr'].get('detection_threshold_dbm', -40.0),
            scan_frequencies=self.config['sdr'].get('scan_frequencies'),
            detection_margin_db=self.config['sdr'].get('detection_margin_db', 6.0),
            min_burst_rssi_dbm=self.config['sdr'].get('min_burst_rssi_dbm', -52.0)
        )
        
        if not self.sdr.connect():
            logger.error("Failed to connect to SDR")
            return False
        
        # Initialize camera
        logger.info("Initializing camera...")
        self.camera = CameraHandler(
            device_id=self.config['camera']['device_id'],
            width=self.config['camera']['width'],
            height=self.config['camera']['height'],
            fps=self.config['camera']['fps']
        )
        
        if not self.camera.connect():
            logger.warning("Camera not available, continuing without video")
        
        # Initialize motion detector
        self.motion_detector = MotionDetector(
            threshold=self.config['camera']['motion_threshold']
        )
        
        # Initialize alert system
        self.alert_system = AlertSystem(self.config['alerts']['distance_levels'])
        
        # Initialize display
        self.display = DisplayHandler(
            display_type=self.config['display']['type'],
            width=self.config['display']['width'],
            height=self.config['display']['height']
        )
        
        # Initialize sound alert (aplay-based, no pyaudio needed)
        snd = self.config.get('sound', {})
        self.sound_alert = SoundAlert(
            alert_file=snd.get('alert_file', 'data/sounds/alert.wav'),
            volume=snd.get('volume', 0.8),
            device=snd.get('device')
        )
        
        # Initialize CSV ride logger
        log_cfg = self.config.get('logging', {})
        self.csv = CSVLogger(
            log_dir=log_cfg.get('csv_dir', '~/radar_logs'),
            enabled=log_cfg.get('csv_enabled', True),
            log_all_scans=log_cfg.get('log_all_scans', False)
        )
        
        # Initialize vehicle tracker (Blueye-style approach/retreat trends)
        self.tracker = VehicleTracker()
        
        # Telegram alerts (orange/red -> iPhone notification -> CarPlay banner)
        tg = self.config.get('telegram', {})
        self.telegram = TelegramAlert(
            bot_token=tg.get('bot_token', ''),
            chat_id=tg.get('chat_id', ''),
            orange_cooldown_s=tg.get('orange_cooldown_s', 25.0),
            red_cooldown_s=tg.get('red_cooldown_s', 8.0),
            enabled=tg.get('enabled', True)
        )
        
        logger.info("Initialization complete")
        return True

    def run(self):
        """Main application loop."""
        self.running = True
        frame_count = 0
        scan_interval = 0.25  # Scan every 250ms (round-robin over scan frequencies)
        max_distance_m = float(self.config['alerts'].get('distance_threshold_m', 500))
        last_scan_time = time.time()
        last_rejected = 0        # noise-rejection counter, for the display warning
        noise_flag_until = 0.0   # show noise warning until this time
        
        logger.info("Starting main loop...")
        
        try:
            while self.running:
                current_time = time.time()
                
                # Refresh NTP sync status every 30 s (hotspot can go off
                # again once SYNC shows green on the display)
                if current_time - self._sync_check_time >= 30:
                    try:
                        import subprocess
                        r = subprocess.run(
                            ['timedatectl', 'show', '--value', '--property=NTPSynchronized'],
                            capture_output=True, text=True, timeout=2)
                        self._sync_ok = (r.stdout.strip() == 'yes')
                    except Exception:
                        self._sync_ok = True  # assume ok on probe failure
                    if not self._sync_ok and self._unsynced_since == 0.0:
                        self._unsynced_since = current_time
                    elif self._sync_ok:
                        self._unsynced_since = 0.0
                    self._sync_check_time = current_time

                # Read camera frame
                frame = None
                motion_detected = False
                
                if self.camera and self.camera.is_connected:
                    frame = self.camera.read_frame()
                    
                    if frame is not None and self.motion_detector:
                        motion_detected, mask, contours = self.motion_detector.detect(frame)
                        if motion_detected:
                            frame = self.motion_detector.draw_contours(frame)
                
                # Scan RF periodically; hold the last valid distance between
                # scans so display and alerts don't flicker on and off
                if current_time - last_scan_time >= scan_interval and self.sdr:
                    rssi, signal_detected, scanned_freq = self.sdr.scan_next()

                    if self.sdr.noise_rejected_count > last_rejected:
                        last_rejected = self.sdr.noise_rejected_count
                        noise_flag_until = current_time + 5.0

                    if self.csv:
                        self.csv.log_scan(scanned_freq, rssi)

                    if signal_detected:
                        self.last_distance_m = self.sdr.estimate_distance(
                            rssi,
                            path_loss_exponent=3.0
                        )
                        # Only accept mobile transmitters within max range;
                        # anything "farther" is noise or a slipping carrier
                        if self.last_distance_m > max_distance_m:
                            self.last_distance_m = 9999.0
                        self.last_detect_time = current_time
                        self.last_detection_info = {
                            'freq_mhz': scanned_freq / 1e6,
                            'rssi_dbm': rssi,
                            'distance_m': self.last_distance_m,
                            'time': datetime.now().strftime('%H:%M:%S')
                        }
                        track_now = (self.tracker.feed(
                            scanned_freq, rssi, self.last_distance_m)
                            if self.tracker else {})
                        logger.info(f"Signal burst: {rssi:.1f} dBm @ "
                                    f"{scanned_freq/1e6:.3f} MHz -> "
                                    f"~{self.last_distance_m:.0f}m")
                        if self.csv:
                            self.csv.log_burst(
                                scanned_freq, rssi, self.last_distance_m,
                                accepted=self.last_distance_m <= max_distance_m,
                                extra_info=(f"{track_now['bursts']}x {track_now['trend']}"
                                            if track_now else ""))
                    elif current_time - self.last_detect_time > self.signal_hold_s:
                        # No signal for longer than the hold window: reset
                        self.last_distance_m = 9999.0
                    
                    last_scan_time = current_time
                
                distance_m = self.last_distance_m
                if self.tracker:
                    self.last_track = self.tracker.summary(current_time)
                
                # Update alert system
                if self.alert_system:
                    status = self.alert_system.update(distance_m)
                    
                    # Play sound if needed (honors config['sound']['enabled'])
                    if status['sound_alert'] and self.sound_alert and \
                            self.config.get('sound', {}).get('enabled', True):
                        self.sound_alert.play(duration_s=1.4)
                    
                    # Log alert level changes at INFO level (keeps a useful
                    # history without per-frame debug spam)
                    current_level = status['indicators']
                    if current_level != self.last_alert_level:
                        logger.info(f"Alert level change: {self.last_alert_level} -> "
                                    f"{current_level} indicators "
                                    f"(distance {status['distance_m']:.0f}m, "
                                    f"sound_alarm: {self.alert_system.should_sound_alarm()})")
                        self.last_alert_level = current_level
                        if self.csv:
                            self.csv.log_alert(current_level,
                                               status['distance_m'],
                                               self.alert_system.should_sound_alarm())
                        # Telegram notification at orange/red (cooldown inside)
                        if self.telegram and current_level >= 3:
                            trend = self.last_track.get('trend', '')
                            bursts = self.last_track.get('bursts', 0)
                            freq = (self.last_detection_info['freq_mhz']
                                    if self.last_detection_info else 0.0)
                            self.telegram.alert(current_level,
                                                status['distance_m'],
                                                trend=trend,
                                                freq_mhz=freq,
                                                bursts=bursts)
                
                # Render and display frame
                if self.display and self.alert_system:
                    display_frame = self.display.render_frame(
                        camera_frame=frame,
                        distance_m=distance_m,
                        indicators=self.alert_system.current_level.indicators if self.alert_system.current_level else 0,
                        alarm_active=self.alert_system.should_sound_alarm(),
                        motion_detected=motion_detected,
                        last_detection=self.last_detection_info,
                        noise_warning=(current_time < noise_flag_until),
                        track=self.last_track,
                        clock_synced=self._sync_ok,
                        clock_unsynced_s=(current_time - self._unsynced_since
                                          if self._unsynced_since else 0.0)
                    )
                    
                    if display_frame is not None:
                        self.display.display_frame(display_frame)
                
                # Check for exit key
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # q or ESC
                    logger.info("User requested exit")
                    self.running = False
                
                frame_count += 1
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources."""
        logger.info("Cleaning up...")
        
        if self.csv:
            self.csv.close()
        if self.sdr:
            self.sdr.disconnect()
        if self.camera:
            self.camera.disconnect()
        if self.display:
            self.display.close()
        if self.sound_alert:
            self.sound_alert.stop()
        if self.telegram:
            self.telegram.stop()
        
        logger.info("Cleanup complete")


@click.command()
@click.option('--country', default='nl', help='Country code (nl, de, be)')
@click.option('--distance-threshold', default=500, help='Alert distance in meters')
@click.option('--camera', default=0, help='Camera device ID')
@click.option('--display', default='terminal', help='Display type (terminal, hdmi, spi)')
@click.option('--debug', is_flag=True, help='Enable debug logging')
def main(country: str, distance_threshold: int, camera: int, display: str, debug: bool):
    """
    Sentinel Radar - RF-based Police Proximity Alert System
    """
    logger.info(f"Starting Sentinel Radar v0.1.0")
    logger.info(f"Config: country={country}, threshold={distance_threshold}m, "
              f"camera={camera}, display={display}")
    
    # Initialize application
    radar = SentinelRadar()
    
    if not radar.initialize(country=country, debug=debug):
        logger.error("Failed to initialize")
        sys.exit(1)
    
    # Run main loop
    radar.run()


if __name__ == "__main__":
    main()
