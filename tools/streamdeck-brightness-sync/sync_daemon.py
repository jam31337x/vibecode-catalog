#!/usr/bin/env python3
"""
Mirror Mac main-display brightness onto Stream Deck key LEDs.

Stream Deck software 6+/7 removed the plugin `setBrightness` API, and while the
official app is open it holds exclusive HID access — so live LED updates require
a brief quit → HID feature-report → prefs → relaunch cycle.

Elgato removed setBrightness; prefs-only updates do not drive the hardware.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

POLL_MS = 400
MIN_DELTA = 1
# Wait until Mac brightness stops moving before applying (avoids restart spam).
DEBOUNCE_S = 0.85
# Ignore Mac readings right after we relaunch Stream Deck.
COOLDOWN_S = 4.0
APP_NAME = "Stream Deck"
APP_BUNDLE = "Elgato Stream Deck"

HERE = Path(__file__).resolve().parent
HELPER = HERE / "bin" / "mac-brightness"
APPLY = HERE / "apply_brightness.py"
LOG = Path.home() / "Library" / "Logs" / "streamdeck-brightness-sync.log"


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z") + " " + msg
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def read_mac_brightness() -> int | None:
    if not HELPER.is_file():
        return None
    try:
        r = subprocess.run(
            [str(HELPER)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        n = int(str(r.stdout).strip())
    except ValueError:
        return None
    return max(0, min(100, n))


def streamdeck_running() -> list[int]:
    r = subprocess.run(
        ["pgrep", "-x", APP_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return []
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def quit_streamdeck(timeout_s: float = 6.0) -> None:
    if not streamdeck_running():
        return
    subprocess.run(
        ["osascript", "-e", f'tell application "{APP_NAME}" to quit'],
        capture_output=True,
        check=False,
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not streamdeck_running():
            return
        time.sleep(0.1)
    for pid in streamdeck_running():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.4)
    for pid in streamdeck_running():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(0.2)


def launch_streamdeck() -> None:
    subprocess.Popen(
        ["open", "-a", APP_BUNDLE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def apply(pct: int) -> None:
    was_running = bool(streamdeck_running())
    if was_running:
        log(f"apply {pct}% — quitting Stream Deck for HID access")
        quit_streamdeck()
    else:
        log(f"apply {pct}% — Stream Deck not running, HID direct")

    r = subprocess.run(
        [sys.executable, str(APPLY), str(pct)],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        log(f"apply failed: {r.stderr.strip() or r.stdout.strip()}")
        if was_running:
            launch_streamdeck()
        raise RuntimeError(r.stderr.strip() or "apply failed")

    log(f"HID+prefs ok: {r.stdout.strip()}")
    if was_running:
        launch_streamdeck()
        # Wait until app is back so we don't immediately re-trigger.
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if streamdeck_running():
                break
            time.sleep(0.1)


def main() -> int:
    log("daemon start")
    if not HELPER.is_file():
        log(f"missing helper: {HELPER}")
        return 1
    if not APPLY.is_file():
        log(f"missing apply script: {APPLY}")
        return 1

    last_applied = -1
    pending: int | None = None
    pending_since = 0.0
    cooldown_until = 0.0

    while True:
        now = time.time()
        pct = read_mac_brightness()
        if pct is None:
            time.sleep(POLL_MS / 1000.0)
            continue

        if now < cooldown_until:
            last_applied = pct
            pending = None
            time.sleep(POLL_MS / 1000.0)
            continue

        if last_applied >= 0 and abs(pct - last_applied) < MIN_DELTA:
            pending = None
            time.sleep(POLL_MS / 1000.0)
            continue

        if pending is None or pct != pending:
            pending = pct
            pending_since = now
            time.sleep(POLL_MS / 1000.0)
            continue

        if now - pending_since < DEBOUNCE_S:
            time.sleep(POLL_MS / 1000.0)
            continue

        try:
            apply(pending)
            last_applied = pending
            pending = None
            cooldown_until = time.time() + COOLDOWN_S
        except Exception as exc:  # noqa: BLE001
            log(f"apply error: {exc}")
            cooldown_until = time.time() + 2.0

        time.sleep(POLL_MS / 1000.0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
