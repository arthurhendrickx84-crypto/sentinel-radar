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
                    motion_detected: bool) -> Optional[np.ndarray]:
        """
        Render display frame with all information.
        
        Args:
            camera_frame: Video frame (BGR)
            distance_m: Distance in meters
            indicators: Number of indicator lights (0-6)
            alarm_active: Is alarm currently active
            motion_detected: Is motion detected
            
        Returns:
            Rendered frame or None
        """
        if camera_frame is None:
            # Create blank frame if no camera
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        else:
            frame = cv2.resize(camera_frame, (self.width, self.height))
        
        # Draw overlay info
        self._draw_info_overlay(frame, distance_m, indicators, alarm_active, motion_detected)
        
        return frame

    def _draw_info_overlay(self, frame: np.ndarray, distance_m: float, 
                          indicators: int, alarm_active: bool, motion_detected: bool):
        """
        Draw information overlay on frame.
        
        Args:
            frame: Target frame to draw on
            distance_m: Distance value
            indicators: Number of lights
            alarm_active: Alarm state
            motion_detected: Motion state
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        font_color = (255, 255, 255)  # White
        thickness = 2
        
        # Top-left: Timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, f"Time: {timestamp}", (10, 30), font, font_scale, font_color, thickness)
        
        # Top-right: Motion indicator
        motion_status = "MOTION" if motion_detected else "Clear"
        motion_color = (0, 255, 0) if motion_detected else (100, 100, 100)
        cv2.putText(frame, f"Motion: {motion_status}", (self.width - 250, 30), 
                   font, font_scale, motion_color, thickness)
        
        # Center: Distance
        if distance_m > 0:
            distance_text = f"Distance: {distance_m:.1f}m"
            distance_color = (0, 0, 255) if alarm_active else (0, 255, 255)
            cv2.putText(frame, distance_text, (self.width // 2 - 150, self.height // 2), 
                       font, 1.2, distance_color, 3)
        
        # Bottom: Indicator lights
        self._draw_indicator_lights(frame, indicators)
        
        # Bottom-right: Alarm status
        if alarm_active:
            cv2.putText(frame, "ALARM!", (self.width - 200, self.height - 30), 
                       font, 1.2, (0, 0, 255), 3)

    def _draw_indicator_lights(self, frame: np.ndarray, indicators: int, y_pos: Optional[int] = None):
        """
        Draw indicator light circles on frame.
        
        Args:
            frame: Target frame
            indicators: Number of lights to show (0-6)
            y_pos: Y position (default: bottom)
        """
        if y_pos is None:
            y_pos = self.height - 50
        
        light_radius = 20
        spacing = 50
        start_x = self.width // 2 - (6 * spacing // 2)
        
        for i in range(6):
            x = start_x + i * spacing
            color = (0, 255, 0) if i < indicators else (100, 100, 100)
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
