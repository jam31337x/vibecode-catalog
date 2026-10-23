#!/usr/bin/env python3
"""
Mirror Mac main-display brightness onto Stream Deck key LEDs at 75% of Mac
(i.e. 25% dimmer: Mac 100 → Deck 75).

Official Elgato docs (https://docs.elgato.com/streamdeck/hid/general):
  Set Backlight Brightness = HID Feature Report ID 0x03, Command 0x08, value 0–100.
Official Plugin SDK (docs.elgato.com/streamdeck/sdk): no setBrightness / device
brightness command — confirmed absent from websocket plugin reference.

While Stream Deck.app holds the device, macOS returns exclusive-access on HID open.
We try HID first (no restart); only if that fails do we briefly quit → HID → relaunch.
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
DEBOUNCE_S = 0.85
COOLDOWN_S = 4.0
# Deck LEDs at 75% of Mac brightness (25% less).
MAC_TO_DECK_SCALE = 0.75
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


def map_mac_to_deck(mac_pct: int) -> int:
    """Mac % → Deck % (25% dimmer, clamped 0–100)."""
    return max(0, min(100, int(round(mac_pct * MAC_TO_DECK_SCALE))))


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


def run_apply(deck_pct: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(APPLY), str(deck_pct)],
        capture_output=True,
        text=True,
        check=False,
    )


def apply(mac_pct: int) -> None:
    deck_pct = map_mac_to_deck(mac_pct)
    log(f"mac {mac_pct}% → deck {deck_pct}% (×{MAC_TO_DECK_SCALE} / 25% dimmer)")

    # Official HID path first — no restart if the device can be opened.
    r = run_apply(deck_pct)
    if r.returncode == 0:
        log(f"HID ok (no restart): {r.stdout.strip()}")
        return

    err = (r.stderr or r.stdout or "").strip()
    was_running = bool(streamdeck_running())
    if not was_running:
        log(f"apply failed (app not running): {err}")
        raise RuntimeError(err or "apply failed")

    # Plugin SDK has no brightness API; Stream Deck.app holds exclusive HID.
    log(f"HID blocked ({err or 'exclusive'}) — quit/relaunch fallback")
    quit_streamdeck()
    r = run_apply(deck_pct)
    if r.returncode != 0:
        log(f"apply failed after quit: {r.stderr.strip() or r.stdout.strip()}")
        launch_streamdeck()
        raise RuntimeError(r.stderr.strip() or "apply failed")

    log(f"HID+prefs ok: {r.stdout.strip()}")
    launch_streamdeck()
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

    last_deck = -1
    pending_mac: int | None = None
    pending_since = 0.0
    cooldown_until = 0.0

    while True:
        now = time.time()
        mac = read_mac_brightness()
        if mac is None:
            time.sleep(POLL_MS / 1000.0)
            continue

        deck = map_mac_to_deck(mac)

        # After relaunch, ignore churn briefly — but do not forget the target.
        if now < cooldown_until:
            time.sleep(POLL_MS / 1000.0)
            continue

        if last_deck >= 0 and abs(deck - last_deck) < MIN_DELTA:
            pending_mac = None
            time.sleep(POLL_MS / 1000.0)
            continue

        if pending_mac is None or mac != pending_mac:
            pending_mac = mac
            pending_since = now
            time.sleep(POLL_MS / 1000.0)
            continue

        if now - pending_since < DEBOUNCE_S:
            time.sleep(POLL_MS / 1000.0)
            continue

        try:
            apply(pending_mac)
            last_deck = map_mac_to_deck(pending_mac)
            pending_mac = None
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
