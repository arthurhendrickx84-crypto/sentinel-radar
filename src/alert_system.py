"""Alert and indicator system for proximity warnings."""

import logging
from typing import List, Dict, Optional
import json

logger = logging.getLogger(__name__)


class AlertLevel:
    """Represents an alert level with distance and indicator count."""
    
    def __init__(self, distance_m: float, indicators: int, sound: bool = False):
        self.distance_m = distance_m
        self.indicators = indicators
        self.sound = sound
    
    def __repr__(self):
        return f"AlertLevel({self.distance_m}m, {self.indicators} lights, sound={self.sound})"


class AlertSystem:
    """Manages alert levels and generates visual/audio warnings."""
    
    def __init__(self, alert_levels: List[Dict]):
        """
        Initialize alert system.
        
        Args:
            alert_levels: List of alert level configs with distance_m, indicators, sound
        """
        self.alert_levels = [
            AlertLevel(
                distance_m=level['distance_m'],
                indicators=level['indicators'],
                sound=level.get('sound', False)
            )
            for level in sorted(alert_levels, key=lambda x: x['distance_m'], reverse=True)
        ]
        self.current_level: Optional[AlertLevel] = None
        self.last_distance: Optional[float] = None

    def get_alert_level(self, distance_m: float) -> Optional[AlertLevel]:
        """
        Get alert level for given distance.
        
        Args:
            distance_m: Distance in meters
            
        Returns:
            AlertLevel object or None if distance > max threshold
        """
        for level in self.alert_levels:
            if distance_m <= level.distance_m:
                return level
        
        return None

    def update(self, distance_m: float) -> Dict:
        """
        Update alert system with new distance.
        
        Args:
            distance_m: Distance in meters
            
        Returns:
            Alert status dict with current level, indicators, and actions
        """
        self.last_distance = distance_m
        new_level = self.get_alert_level(distance_m)
        
        status = {
            'distance_m': distance_m,
            'alert_active': new_level is not None,
            'level': None,
            'indicators': 0,
            'sound_alert': False,
            'level_changed': False
        }
        
        if new_level:
            status['level'] = f"{new_level.distance_m}m"
            status['indicators'] = new_level.indicators
            status['sound_alert'] = new_level.sound
            status['level_changed'] = (self.current_level != new_level)
        
        self.current_level = new_level
        return status

    def get_indicator_display(self) -> str:
        """
        Get text representation of indicator lights.
        
        Returns:
            String like '● ● ● ○ ○ ○' (filled and empty circles)
        """
        if not self.current_level:
            return "○ ○ ○ ○ ○ ○"
        
        filled = "● " * self.current_level.indicators
        empty = "○ " * (6 - self.current_level.indicators)
        return (filled + empty).strip()

    def should_sound_alarm(self) -> bool:
        """
        Check if audio alarm should be triggered.
        
        Returns:
            True if current level has sound enabled
        """
        return self.current_level is not None and self.current_level.sound

    def get_status_text(self) -> str:
        """
        Get human-readable status text.
        
        Returns:
            Status description string
        """
        if not self.current_level:
            return "No police detected"
        
        distance = self.last_distance or 0
        lights = self.current_level.indicators
        alarm = "🔔 ALARM!" if self.current_level.sound else ""
        
        return f"Police at {distance:.0f}m | {lights} lights {alarm}"
