#!/usr/bin/env python3
"""
Mirror Mac main-display brightness onto Stream Deck key LEDs.

Calibration (config.json): at Mac ANCHOR_MAC%, Deck = ANCHOR_DECK%.
Linear across the scale, hard-capped at MAX_DECK%.

Official Elgato docs (https://docs.elgato.com/streamdeck/hid/general):
  Set Backlight Brightness = HID Feature Report ID 0x03, Command 0x08, value 0–100.
Plugin SDK has no setBrightness. HID is exclusive while Stream Deck.app runs —
try HID first; quit/relaunch only if open fails.
"""
from __future__ import annotations

import json
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
APP_NAME = "Stream Deck"
APP_BUNDLE = "Elgato Stream Deck"

# Defaults: locked manual Deck 42% @ Mac 75%, cap 55%.
DEFAULT_ANCHOR_MAC = 75
DEFAULT_ANCHOR_DECK = 42
DEFAULT_MAX_DECK = 55

HERE = Path(__file__).resolve().parent
HELPER = HERE / "bin" / "mac-brightness"
APPLY = HERE / "apply_brightness.py"
CONFIG = HERE / "config.json"
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


def load_config() -> tuple[int, int, int]:
    anchor_mac = DEFAULT_ANCHOR_MAC
    anchor_deck = DEFAULT_ANCHOR_DECK
    max_deck = DEFAULT_MAX_DECK
    if CONFIG.is_file():
        try:
            raw = json.loads(CONFIG.read_text(encoding="utf-8"))
            anchor_mac = int(raw.get("anchor_mac_pct", anchor_mac))
            anchor_deck = int(raw.get("anchor_deck_pct", anchor_deck))
            max_deck = int(raw.get("max_deck_pct", max_deck))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            log(f"config read failed, using defaults: {exc}")
    anchor_mac = max(1, min(100, anchor_mac))
    anchor_deck = max(0, min(100, anchor_deck))
    max_deck = max(0, min(100, max_deck))
    return anchor_mac, anchor_deck, max_deck


def map_mac_to_deck(mac_pct: int, anchor_mac: int, anchor_deck: int, max_deck: int) -> int:
    """Linear map locked so Mac anchor_mac% → Deck anchor_deck%, capped at max_deck."""
    scale = anchor_deck / float(anchor_mac)
    return max(0, min(max_deck, int(round(mac_pct * scale))))


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


def apply(mac_pct: int, anchor_mac: int, anchor_deck: int, max_deck: int) -> None:
    deck_pct = map_mac_to_deck(mac_pct, anchor_mac, anchor_deck, max_deck)
    scale = anchor_deck / float(anchor_mac)
    log(
        f"mac {mac_pct}% → deck {deck_pct}% "
        f"(lock {anchor_deck}%@{anchor_mac}% mac, ×{scale:.4f}, cap {max_deck}%)"
    )

    r = run_apply(deck_pct)
    if r.returncode == 0:
        log(f"HID ok (no restart): {r.stdout.strip()}")
        return

    err = (r.stderr or r.stdout or "").strip()
    was_running = bool(streamdeck_running())
    if not was_running:
        log(f"apply failed (app not running): {err}")
        raise RuntimeError(err or "apply failed")

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

    anchor_mac, anchor_deck, max_deck = load_config()
    log(
        f"calibration: Mac {anchor_mac}% → Deck {anchor_deck}%, "
        f"cap {max_deck}% (scale {anchor_deck / float(anchor_mac):.4f})"
    )

    last_deck = -1
    pending_mac: int | None = None
    pending_since = 0.0
    cooldown_until = 0.0
    last_config_load = 0.0

    while True:
        now = time.time()
        if now - last_config_load >= 30.0:
            anchor_mac, anchor_deck, max_deck = load_config()
            last_config_load = now

        mac = read_mac_brightness()
        if mac is None:
            time.sleep(POLL_MS / 1000.0)
            continue

        deck = map_mac_to_deck(mac, anchor_mac, anchor_deck, max_deck)

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
            apply(pending_mac, anchor_mac, anchor_deck, max_deck)
            last_deck = map_mac_to_deck(pending_mac, anchor_mac, anchor_deck, max_deck)
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
