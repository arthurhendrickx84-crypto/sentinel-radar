#!/usr/bin/env python3
"""Sentinel Radar - Main application."""

import sys
import logging
import json
import time
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
        
        self.running = False

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
            gain=self.config['sdr']['gain']
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
        
        # Initialize sound alert
        self.sound_alert = SoundAlert(
            alert_file=self.config['sound']['alert_file'],
            volume=self.config['sound']['volume']
        )
        
        logger.info("Initialization complete")
        return True

    def run(self):
        """Main application loop."""
        self.running = True
        frame_count = 0
        scan_interval = 0.5  # Scan every 500ms
        last_scan_time = time.time()
        
        logger.info("Starting main loop...")
        
        try:
            while self.running:
                current_time = time.time()
                
                # Read camera frame
                frame = None
                motion_detected = False
                
                if self.camera and self.camera.is_connected:
                    frame = self.camera.read_frame()
                    
                    if frame is not None and self.motion_detector:
                        motion_detected, mask, contours = self.motion_detector.detect(frame)
                        if motion_detected:
                            frame = self.motion_detector.draw_contours(frame)
                
                # Scan RF periodically
                distance_m = 0
                if current_time - last_scan_time >= scan_interval and self.sdr:
                    rssi, signal_detected = self.sdr.scan_frequency(
                        self.sdr.center_freq,
                        duration_s=0.1
                    )
                    
                    if signal_detected:
                        distance_m = self.sdr.estimate_distance(
                            rssi,
                            tx_power_dbm=30,
                            path_loss_exponent=2.0
                        )
                    
                    last_scan_time = current_time
                
                # Update alert system
                if self.alert_system:
                    status = self.alert_system.update(distance_m)
                    
                    # Play sound if needed
                    if status['sound_alert'] and self.sound_alert:
                        self.sound_alert.play(duration_s=0.2)
                    
                    # Display info
                    logger.debug(f"Frame {frame_count}: {status['distance_m']:.1f}m, "
                               f"Alert: {status['alert_active']}, "
                               f"Lights: {status['indicators']}")
                
                # Render and display frame
                if self.display and self.alert_system:
                    display_frame = self.display.render_frame(
                        camera_frame=frame,
                        distance_m=distance_m,
                        indicators=self.alert_system.current_level.indicators if self.alert_system.current_level else 0,
                        alarm_active=self.alert_system.should_sound_alarm(),
                        motion_detected=motion_detected
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
        
        if self.sdr:
            self.sdr.disconnect()
        if self.camera:
            self.camera.disconnect()
        if self.display:
            self.display.close()
        if self.sound_alert:
            self.sound_alert.stop()
        
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
