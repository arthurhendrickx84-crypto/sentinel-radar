"""Telegram alert notifications.

Sends an alert message to a Telegram bot chat when the traffic-light
system reaches orange or red. Uses only the stdlib (urllib) so no extra
dependencies are needed on the Pi.

Behavior designed for the car:
- Non-blocking: sends happen in a background worker thread
- Cooldowns: repeated alerts at the same level do not spam the chat
- Retry queue: when the hotspot/Bluetooth internet is briefly away,
  pending alerts are retried; stale ones (> retry_window_s) are dropped
"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramAlert:
    """Queues and sends alert messages to a Telegram bot chat."""

    def __init__(self, bot_token: str = "", chat_id: str = "",
                 orange_cooldown_s: float = 25.0,
                 red_cooldown_s: float = 8.0,
                 retry_window_s: float = 120.0,
                 enabled: bool = True):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.orange_cooldown_s = orange_cooldown_s
        self.red_cooldown_s = red_cooldown_s
        self.retry_window_s = retry_window_s
        self.enabled = enabled

        self._queue = []             # pending (ts, text) tuples
        self._lock = threading.Lock()
        self._last_sent = {"orange": 0.0, "red": 0.0}
        self._stop = False
        self._worker = None

        if not enabled:
            logger.info("Telegram alerts disabled")
            return
        if not self.bot_token or not self.chat_id:
            logger.info("Telegram alerts configured but bot_token/chat_id "
                        "not set yet - messages will queue until configured")
        self._worker = threading.Thread(
            target=self._run_worker, daemon=True, name="telegram-alerts")
        self._worker.start()
        logger.info("Telegram alerts ready")

    # ------------------------------------------------------------------
    def alert(self, indicators: int, distance_m: float,
              trend: str = "", freq_mhz: float = 0.0,
              bursts: int = 0) -> None:
        """Queue a notification. indicators 3-4 = orange, 5-6 = red."""
        if not self.enabled:
            return
        if indicators >= 5:
            level = "red"
            icon = "🔴"
        elif indicators >= 3:
            level = "orange"
            icon = "🟠"
        else:
            return  # green: no notification

        cooldown = (self.red_cooldown_s if level == "red"
                    else self.orange_cooldown_s)
        now = time.time()
        if now - self._last_sent[level] < cooldown:
            return  # suppressed by cooldown

        parts = [f"{icon} Sentinel: hulpdienstvoertuig {level}",
                 f"Afstand ~{distance_m:.0f} m"]
        if trend:
            parts.append(f"trend: {trend}")
        if freq_mhz > 0:
            parts.append(f"kanaal {freq_mhz:.3f} MHz")
        if bursts:
            parts.append(f"{bursts}x actief")
        text = "\n".join(parts)

        self._last_sent[level] = now
        with self._lock:
            self._queue.append((now, text))
        logger.info(f"Telegram queued ({level}): {parts[1]}")

    # ------------------------------------------------------------------
    def _run_worker(self):
        """Background loop: flush the queue whenever possible."""
        while not self._stop:
            self._flush()
            time.sleep(1.0)

    def _flush(self):
        if not self.bot_token or not self.chat_id:
            return  # not configured: keep queueing (bounded below)
        now = time.time()
        with self._lock:
            # drop stale messages
            self._queue = [(ts, t) for ts, t in self._queue
                           if now - ts <= self.retry_window_s]
            if not self._queue:
                return
            ts, text = self._queue[0]

        try:
            data = urllib.parse.urlencode({
                "chat_id": self.chat_id,
                "text": text,
                "disable_notification": "false",
            }).encode()
            req = urllib.request.Request(
                API_URL.format(token=self.bot_token), data=data,
                method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = json.loads(resp.read().decode())
            if body.get("ok"):
                with self._lock:
                    self._queue.pop(0)
            else:
                logger.error(f"Telegram API error: {body}")
                with self._lock:
                    self._queue.pop(0)  # permanent API error: drop
        except Exception:
            # No internet right now: leave in queue, retry next cycle
            pass

    def stop(self):
        self._stop = True
        if self._worker:
            self._worker.join(timeout=2.0)
