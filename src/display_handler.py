"""Display handler for terminal, LCD, and HDMI output."""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class DisplayHandler:
    """Manages display output (terminal, LCD, HDMI)."""
    
    def __init__(self, display_type: str = "terminal", width: int = 640, height: int = 480):
        """
        Initialize display handler.
        
        Args:
            display_type: 'terminal', 'spi', 'hdmi'
            width: Display width
            height: Display height
        """
        self.display_type = display_type
        self.width = width
        self.height = height
        self.is_active = False
        self.fb_bpp = 16
        self.fb_path = "/dev/fb1"
        
        if display_type == "terminal":
            self.is_active = True
        elif display_type == "hdmi":
            self.is_active = True
        elif display_type == "fb":
            # Direct framebuffer output (e.g. ILI9340 TFT on /dev/fb1).
            # No X server needed - works headless and under systemd.
            try:
                with open("/sys/class/graphics/fb1/virtual_size") as f:
                    w, h = f.read().strip().split(",")
                    self.width, self.height = int(w), int(h)
                with open("/sys/class/graphics/fb1/bits_per_pixel") as f:
                    self.fb_bpp = int(f.read().strip())
                self.is_active = True
                logger.info(f"Framebuffer display: {self.fb_path} "
                            f"{self.width}x{self.height}@{self.fb_bpp}bpp")
            except Exception as e:
                logger.error(f"Failed to initialize framebuffer display: {e}")
                self.is_active = False
        elif display_type == "spi":
            try:
                # Import RPi.GPIO and SPI display libraries
                self.is_active = True
                logger.info("SPI display initialized")
            except Exception as e:
                logger.error(f"Failed to initialize SPI display: {e}")
                self.is_active = False

    def render_frame(self, camera_frame: Optional[np.ndarray], 
                    distance_m: float,
                    indicators: int,
                    alarm_active: bool,
                    motion_detected: bool,
                    last_detection: Optional[dict] = None,
                    noise_warning: bool = False,
                    track: Optional[dict] = None,
                    clock_synced: bool = True,
                    clock_unsynced_s: float = 0.0) -> Optional[np.ndarray]:
        """
        Render display frame with all information.
        
        Args:
            camera_frame: Video frame (BGR)
            distance_m: Distance in meters (9999 = no signal)
            indicators: Number of indicator lights (0-6)
            alarm_active: Is alarm currently active
            motion_detected: Is motion detected
            last_detection: Optional dict describing the last accepted burst
            
        Returns:
            Rendered frame or None
        """
        if camera_frame is None:
            # Create blank frame if no camera
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        else:
            frame = cv2.resize(camera_frame, (self.width, self.height))
        
        # Draw overlay info
        self._draw_info_overlay(frame, distance_m, indicators, alarm_active,
                                motion_detected, last_detection, noise_warning,
                                track, clock_synced, clock_unsynced_s)
        
        return frame

    def _draw_info_overlay(self, frame: np.ndarray, distance_m: float, 
                          indicators: int, alarm_active: bool, motion_detected: bool,
                          last_detection: Optional[dict] = None,
                          noise_warning: bool = False,
                          track: Optional[dict] = None,
                          clock_synced: bool = True,
                          clock_unsynced_s: float = 0.0):
        """
        Draw information overlay on frame.
        
        Layout is scaled for small displays (320x240 framebuffer);
        all positions/fonts scale with the display width.
        
        Args:
            frame: Target frame to draw on
            distance_m: Distance value (9999 = no signal)
            indicators: Number of lights
            alarm_active: Alarm state
            motion_detected: Motion state
            last_detection: Optional dict with the most recent accepted burst
                            (freq_mhz, rssi_dbm, distance_m, time)
        """
        s = max(self.width / 320.0, 0.5)  # layout scale, designed for 320px width
        font = cv2.FONT_HERSHEY_SIMPLEX
        white = (255, 255, 255)
        gray = (140, 140, 140)
        small_scale = 0.42 * s
        thick = max(1, int(round(s)))
        
        # Line 1 (top-left): clock + sync indicator.
        # SYNC in green = NTP verified, safe to switch the hotspot off.
        # KLOK! in red = unsynced >60s, enable hotspot to fix.
        cv2.putText(frame, datetime.now().strftime("%H:%M:%S"),
                    (8, int(20 * s)), font, small_scale, white, thick)
        if clock_synced:
            cv2.putText(frame, "SYNC", (int(62 * s), int(20 * s)),
                        font, small_scale, (0, 255, 0), thick)
        elif clock_unsynced_s > 60:
            cv2.putText(frame, "KLOK!", (int(62 * s), int(20 * s)),
                        font, small_scale, (0, 0, 255), thick)
        
        # Line 2: motion status directly UNDER the clock (no overlap)
        motion_color = (0, 255, 0) if motion_detected else gray
        cv2.putText(frame, "Motion" if motion_detected else "Clear",
                    (8, int(40 * s)), font, small_scale, motion_color, thick)
        
        # Center: distance (big, horizontally centered) or "Geen signaal"
        signal_valid = 0 < distance_m < 9999
        if signal_valid:
            distance_text = f"{distance_m:.0f}m"
            distance_color = (0, 0, 255) if alarm_active else (0, 255, 255)
        else:
            distance_text = "Geen signaal"
            distance_color = gray
        distance_scale = 1.1 * min(s, 1.8)
        (text_w, _), _ = cv2.getTextSize(distance_text, font, distance_scale, 3)
        distance_x = max(4, (self.width - text_w) // 2)
        distance_y = int(self.height * 0.55)
        cv2.putText(frame, distance_text, (distance_x, distance_y),
                    font, distance_scale, distance_color, 3)
        
        # Persistent "last detection" line above the indicator lights
        if last_detection:
            last_text = (f"Laatst: {last_detection['distance_m']:.0f}m @ "
                         f"{last_detection['freq_mhz']:.3f} MHz "
                         f"{last_detection['time']}")
            (lw, _), _ = cv2.getTextSize(last_text, font, small_scale, thick)
            last_x = max(8, (self.width - lw) // 2)
            last_y = self.height - int(72 * s)
            cv2.putText(frame, last_text, (last_x, last_y),
                        font, small_scale, (0, 215, 255), thick)
        
        # Broadband-noise warning: vehicle electronics are drowning the RF
        # input; detections are unreliable while this shows
        if noise_warning:
            cv2.putText(frame, "RUIS - storing in auto", (8, int(60 * s)),
                        font, small_scale, (0, 165, 255), thick)
        
        # Vehicle track line: burst count + approach/retreat trend for the
        # nearest active radio (Blueye-style trend, no content decoded)
        if track:
            trend = track.get('trend', '')
            # Same traffic-light language as the lamps: red = close,
            # green = moving away, gray = stable
            if trend == 'dichterbij':
                track_color = (0, 0, 255)
            elif trend == 'verder':
                track_color = (0, 255, 0)
            else:
                track_color = (200, 200, 200)
            track_text = f"Voertuig: {track['bursts']}x"
            if trend:
                track_text += f" {trend}"
            (tw, _), _ = cv2.getTextSize(track_text, font, small_scale, thick)
            track_x = max(8, (self.width - tw) // 2)
            track_y = self.height - int(52 * s)
            cv2.putText(frame, track_text, (track_x, track_y),
                        font, small_scale, track_color, thick)
        
        # Indicator lights (bottom, centered)
        self._draw_indicator_lights(frame, indicators)        # Alarm status: top-right (free since motion moved under the clock)
        if alarm_active:
            alarm_scale = 0.8 * s
            (aw, _), _ = cv2.getTextSize("ALARM!", font, alarm_scale, 2)
            cv2.putText(frame, "ALARM!", (self.width - aw - 8, int(20 * s)),
                        font, alarm_scale, (0, 0, 255), 2)

    def _draw_indicator_lights(self, frame: np.ndarray, indicators: int, y_pos: Optional[int] = None):
        """
        Draw indicator light circles on frame.
        
        Args:
            frame: Target frame
            indicators: Number of lights to show (0-6)
            y_pos: Y position (default: bottom)
        """
        if y_pos is None:
            y_pos = self.height - int(25 * (self.width / 320.0))
        
        light_radius = int(11 * (self.width / 320.0))
        spacing = int(25 * (self.width / 320.0))
        start_x = self.width // 2 - 3 * spacing
        
        # Traffic-light scheme: green = far, orange = nearing, red = close
        for i in range(6):
            x = start_x + i * spacing
            if i < indicators:
                if i < 2:
                    color = (0, 255, 0)      # ver weg: groen
                elif i < 4:
                    color = (0, 165, 255)    # nabij komend: oranje
                else:
                    color = (0, 0, 255)      # dichtbij: rood
            else:
                color = (100, 100, 100)      # uit
            cv2.circle(frame, (x, y_pos), light_radius, color, -1)
            cv2.circle(frame, (x, y_pos), light_radius, (255, 255, 255), 2)

    def display_frame(self, frame: np.ndarray):
        """
        Display frame on configured display.
        
        Args:
            frame: Frame to display
        """
        if self.display_type == "terminal" or self.display_type == "hdmi":
            cv2.imshow("Sentinel Radar", frame)
            cv2.waitKey(1)  # 1ms delay for event processing
        elif self.display_type == "fb":
            # Render directly to the framebuffer as RGB565 (16bpp)
            try:
                if (frame.shape[1], frame.shape[0]) != (self.width, self.height):
                    frame = cv2.resize(frame, (self.width, self.height))
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                r = (rgb[:, :, 0].astype(np.uint16) >> 3) << 11
                g = (rgb[:, :, 1].astype(np.uint16) >> 2) << 5
                b = (rgb[:, :, 2].astype(np.uint16) >> 3)
                buf = (r | g | b).astype("<u2").tobytes()
                with open(self.fb_path, "wb") as f:
                    f.write(buf)
            except Exception as e:
                logger.error(f"Error writing to framebuffer: {e}")
        elif self.display_type == "spi":
            # Convert and send to SPI display
            try:
                # This would depend on your specific SPI display library
                pass
            except Exception as e:
                logger.error(f"Error displaying on SPI: {e}")

    def close(self):
        """Close display."""
        if self.display_type in ["terminal", "hdmi"]:
            cv2.destroyAllWindows()
