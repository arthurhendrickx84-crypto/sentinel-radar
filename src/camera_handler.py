"""Camera handler for video capture."""

import cv2
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CameraHandler:
    """Handles video capture from camera."""
    
    def __init__(self, device_id: int = 0, width: int = 640, height: int = 480, fps: int = 30):
        """
        Initialize camera handler.
        
        Args:
            device_id: Camera device ID (0 = default/first camera)
            width: Frame width
            height: Frame height
            fps: Target frames per second
        """
        self.device_id = device_id
        self.width = width
        self.height = height
        self.fps = fps
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_connected = False

    def connect(self) -> bool:
        """
        Connect to camera.
        
        Returns:
            True if successful
        """
        try:
            self.cap = cv2.VideoCapture(self.device_id)
            
            if not self.cap.isOpened():
                logger.error(f"Cannot open camera {self.device_id}")
                return False
            
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency
            
            self.is_connected = True
            logger.info(f"Camera {self.device_id} connected: {self.width}x{self.height}@{self.fps}fps")
            return True
        
        except Exception as e:
            logger.error(f"Failed to connect camera: {e}")
            return False

    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read next frame from camera.
        
        Returns:
            Frame (BGR) or None if error
        """
        if not self.is_connected or self.cap is None:
            return None
        
        try:
            ret, frame = self.cap.read()
            if ret:
                return frame
            else:
                logger.error("Failed to read frame")
                return None
        
        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            return None

    def disconnect(self):
        """Disconnect from camera."""
        if self.cap:
            self.cap.release()
            self.is_connected = False
            logger.info("Camera disconnected")

    def __del__(self):
        """Cleanup on deletion."""
        self.disconnect()
