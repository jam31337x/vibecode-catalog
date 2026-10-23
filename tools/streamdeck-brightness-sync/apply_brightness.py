#!/usr/bin/env python3
"""Apply absolute key brightness (0–100) via official Stream Deck HID API.

Docs: https://docs.elgato.com/streamdeck/hid/general
  Feature Report ID 0x03, Command 0x08, brightness UINT8 0x00–0x64 (0–100).

The Plugin SDK has no brightness command. Opening HID usually fails while
Stream Deck.app holds exclusive access — caller may quit the app first.
Also writes map_dev_brightness so the app restores the same level on launch.
"""
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys


def set_prefs_brightness(pct: int) -> None:
    raw = subprocess.check_output(["defaults", "export", "com.elgato.StreamDeck", "-"])
    data = plistlib.loads(raw)
    changed = False
    for _k, v in list((data.get("Devices") or {}).items()):
        if isinstance(v, dict) and "map_dev_brightness" in v:
            if int(v.get("map_dev_brightness", -1)) != pct:
                v["map_dev_brightness"] = pct
                changed = True
    if changed:
        subprocess.run(
            ["defaults", "import", "com.elgato.StreamDeck", "-"],
            input=plistlib.dumps(data, fmt=plistlib.FMT_BINARY),
            check=True,
        )


EXIT_NO_DEVICE = 2
EXIT_EXCLUSIVE = 3


def count_hid_decks() -> int:
    from StreamDeck.DeviceManager import DeviceManager

    return len(DeviceManager().enumerate())


def set_hid_brightness(pct: int) -> int:
    from StreamDeck.DeviceManager import DeviceManager

    decks = DeviceManager().enumerate()
    if not decks:
        raise RuntimeError("no Stream Deck HID devices found")
    ok = 0
    errors = []
    for deck in decks:
        try:
            deck.open()
            try:
                deck.set_brightness(pct)
                ok += 1
            finally:
                deck.close()
        except Exception as exc:  # noqa: BLE001 — report per-device
            errors.append(f"{deck.deck_type()}: {exc}")
    if ok == 0:
        raise RuntimeError("; ".join(errors) or "failed to open any deck")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("percent", type=int, nargs="?", default=None, help="0–100")
    ap.add_argument("--prefs-only", action="store_true")
    ap.add_argument(
        "--probe",
        action="store_true",
        help="print HID device count and exit (0=ok with devices, 2=none)",
    )
    args = ap.parse_args()

    if args.probe:
        n = count_hid_decks()
        print(n)
        return 0 if n > 0 else EXIT_NO_DEVICE

    if args.percent is None:
        ap.error("percent required unless --probe")
    pct = max(0, min(100, int(args.percent)))
    set_prefs_brightness(pct)
    if args.prefs_only:
        print(pct)
        return 0
    try:
        n = set_hid_brightness(pct)
    except RuntimeError as exc:
        msg = str(exc)
        print(f"error: {msg}", file=sys.stderr)
        if "no Stream Deck HID devices found" in msg:
            return EXIT_NO_DEVICE
        if "Could not open HID" in msg or "exclusive" in msg.lower():
            return EXIT_EXCLUSIVE
        return 1
    print(f"{pct} ({n} device(s))")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
