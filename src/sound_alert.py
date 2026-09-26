"""Sound alert system.

Uses aplay (ALSA utility present on Raspberry Pi OS) as the primary
playback path so no Python audio dependencies (pyaudio) are required.
Falls back to pyaudio when aplay is unavailable.
"""

import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SoundAlert:
    """Manages audio alerts."""

    def __init__(self, alert_file: str = "data/sounds/alert.wav",
                 volume: float = 0.8, device: Optional[str] = None):
        """
        Args:
            alert_file: Path to alert sound file
            volume: 0.0-1.0 (passed to aplay when supported)
            device: ALSA device, e.g. 'default:CARD=Headphones'.
                    None = ALSA default.
        """
        self.alert_file = Path(alert_file)
        self.volume = max(0.0, min(1.0, volume))
        self.device = device
        self.is_playing = False
        self.play_thread: Optional[threading.Thread] = None
        self._aplay = shutil.which("aplay")
        self._warned_missing = False

        if not self.alert_file.exists():
            logger.warning(f"Alert sound file not found: {self.alert_file} "
                           f"(alarm will stay silent)")
            self._warned_missing = True
        elif self._aplay:
            logger.info(f"Sound alert ready: {self.alert_file} via aplay"
                        + (f" ({self.device})" if self.device else ""))
        else:
            logger.info("Sound alert ready via pyaudio fallback")

    def play(self, duration_s: float = 2.0):
        """Play the alert sound without blocking the main loop."""
        if self.is_playing:
            return
        if not self.alert_file.exists():
            if not self._warned_missing:
                logger.warning(f"Alert sound missing: {self.alert_file}")
                self._warned_missing = True
            return

        self.play_thread = threading.Thread(
            target=self._play_audio,
            args=(duration_s,),
            daemon=True
        )
        self.play_thread.start()

    def _play_audio(self, duration_s: float):
        """Playback worker: aplay first, pyaudio as fallback."""
        self.is_playing = True
        try:
            if self._aplay:
                cmd = [self._aplay, "-q"]
                if self.device:
                    cmd += ["-D", self.device]
                if self.volume < 0.99:
                    # aplay supports a softvol percentage via --volume
                    # (alsa-utils >= 1.2); ignore silently if unsupported
                    cmd += ["--volume", str(int(self.volume * 100))]
                cmd.append(str(self.alert_file))
                proc = subprocess.run(
                    cmd, capture_output=True, timeout=duration_s + 5)
                if proc.returncode != 0:
                    logger.error(f"aplay failed: "
                                 f"{proc.stderr.decode(errors='replace')[:200]}")
            else:
                self._play_pyaudio(duration_s)
        except Exception as e:
            logger.error(f"Error playing sound: {e}")
        finally:
            self.is_playing = False

    def _play_pyaudio(self, duration_s: float):
        """Legacy pyaudio playback path."""
        try:
            import wave
            import time
            import pyaudio

            start_time = time.time()
            with wave.open(str(self.alert_file), 'rb') as wav_file:
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
        except ImportError:
            logger.warning("Neither aplay nor pyaudio available - no sound")
        except Exception as e:
            logger.error(f"pyaudio playback error: {e}")

    def stop(self):
        """Stop playing sound."""
        self.is_playing = False
        if self.play_thread:
            self.play_thread.join(timeout=1.0)
