"""Motion detection using OpenCV."""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class MotionDetector:
    """Detects motion in video frames using background subtraction."""

    def __init__(self, threshold: int = 25, min_area: int = 500):
        """
        Initialize motion detector.
        
        Args:
            threshold: Motion detection threshold (0-255)
            min_area: Minimum contour area to consider as motion
        """
        self.threshold = threshold
        self.min_area = min_area
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            detectShadows=False,
            varThreshold=16
        )
        self.motion_detected = False
        self.motion_contours = []

    def detect(self, frame: np.ndarray) -> Tuple[bool, np.ndarray, list]:
        """
        Detect motion in frame.
        
        Args:
            frame: Input frame (BGR)
            
        Returns:
            Tuple of (motion_detected, mask, contours)
        """
        if frame is None:
            return False, None, []
        
        try:
            # Apply background subtraction
            mask = self.bg_subtractor.apply(frame)
            
            # Apply threshold
            _, mask = cv2.threshold(mask, self.threshold, 255, cv2.THRESH_BINARY)
            
            # Morphological operations
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            
            # Find contours
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter contours by area
            significant_contours = [
                c for c in contours if cv2.contourArea(c) > self.min_area
            ]
            
            self.motion_detected = len(significant_contours) > 0
            self.motion_contours = significant_contours
            
            return self.motion_detected, mask, significant_contours
        
        except Exception as e:
            logger.error(f"Motion detection error: {e}")
            return False, None, []

    def draw_contours(self, frame: np.ndarray, color: Tuple[int, int, int] = (0, 255, 0), 
                     thickness: int = 2) -> np.ndarray:
        """
        Draw detected motion contours on frame.
        
        Args:
            frame: Input frame
            color: Contour color (BGR)
            thickness: Line thickness
            
        Returns:
            Frame with drawn contours
        """
        if frame is None or not self.motion_contours:
            return frame
        
        frame_copy = frame.copy()
        cv2.drawContours(frame_copy, self.motion_contours, -1, color, thickness)
        
        return frame_copy

    def get_motion_area(self) -> Tuple[int, int, int, int]:
        """
        Get bounding box of all motion areas.
        
        Returns:
            Tuple of (x, y, width, height) or (0, 0, 0, 0) if no motion
        """
        if not self.motion_contours:
            return 0, 0, 0, 0
        
        # Get bounding rectangle of all contours
        x_min, y_min = float('inf'), float('inf')
        x_max, y_max = 0, 0
        
        for contour in self.motion_contours:
            x, y, w, h = cv2.boundingRect(contour)
            x_min = min(x_min, x)
            y_min = min(y_min, y)
            x_max = max(x_max, x + w)
            y_max = max(y_max, y + h)
        
        if x_min == float('inf'):
            return 0, 0, 0, 0
        
        return x_min, y_min, x_max - x_min, y_max - y_min
