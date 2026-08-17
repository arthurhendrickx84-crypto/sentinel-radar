"""Sound alert system."""

import logging
from typing import Optional
import threading

logger = logging.getLogger(__name__)


class SoundAlert:
    """Manages audio alerts."""
    
    def __init__(self, alert_file: str = "data/sounds/alert.wav", volume: float = 0.8):
        """
        Initialize sound alert.
        
        Args:
            alert_file: Path to alert sound file
            volume: Volume level (0.0 - 1.0)
        """
        self.alert_file = alert_file
        self.volume = volume
        self.is_playing = False
        self.play_thread: Optional[threading.Thread] = None

    def play(self, duration_s: float = 2.0):
        """
        Play alert sound.
        
        Args:
            duration_s: Duration to play in seconds
        """
        if self.is_playing:
            return  # Already playing
        
        try:
            import wave
            import pyaudio
            
            # Play in separate thread to not block
            self.play_thread = threading.Thread(
                target=self._play_audio,
                args=(duration_s,),
                daemon=True
            )
            self.play_thread.start()
        
        except ImportError:
            logger.warning("PyAudio not installed, cannot play sound")
        except Exception as e:
            logger.error(f"Error playing sound: {e}")

    def _play_audio(self, duration_s: float):
        """Internal method to play audio."""
        try:
            import wave
            import pyaudio
            import time
            
            self.is_playing = True
            start_time = time.time()
            
            with wave.open(self.alert_file, 'rb') as wav_file:
                p = pyaudio.PyAudio()
                
                stream = p.open(
                    format=p.get_format_from_width(wav_file.getsampwidth()),
                    channels=wav_file.getnchannels(),
                    rate=wav_file.getframerate(),
                    output=True
                )
                
                while time.time() - start_time < duration_s:
                    data = wav_file.readframes(1024)
                    if not data:
                        break
                    stream.write(data)
                
                stream.stop_stream()
                stream.close()
                p.terminate()
        
        except Exception as e:
            logger.error(f"Error in audio playback: {e}")
        
        finally:
            self.is_playing = False

    def stop(self):
        """Stop playing sound."""
        self.is_playing = False
        if self.play_thread:
            self.play_thread.join(timeout=1.0)
