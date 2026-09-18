# streamdeck-wake-safe

Hearing-safe Mac helpers for Elgato Stream Deck USB flakiness after sleep/wake.

| File | Role |
|------|------|
| `streamdeck-wake-watch.swift` | Background watcher (build to a binary; LaunchAgent KeepAlive) |
| `streamdeck-reset.zsh` | Kill app → hub power cycle → relaunch → restore audio |
| `recover-streamdeck.c` / `usb-reenumerate.c` | Low-level USB power/reenumerate |
| `audio_protect.py` | Hold-mute / restore around USB cycles |
| `com.example.streamdeck-wake-reset.plist.example` | LaunchAgent template |

Build notes are intentionally minimal — adapt to your codesign/setup. Licensed under Prosperity (commercial trial then paid).
