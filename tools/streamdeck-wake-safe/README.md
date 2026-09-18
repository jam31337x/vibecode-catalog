# streamdeck-wake-safe

Mac helpers for a flaky Elgato Stream Deck after sleep/wake. Audio is muted around the USB cycle so headphones don’t get a blast when the XLR dock reappears.

## Files

| File | Role |
|------|------|
| `streamdeck-wake-watch.swift` | Background watcher (compile; run from a LaunchAgent) |
| `streamdeck-reset.zsh` | Quit Stream Deck app → cycle hub → relaunch → restore audio |
| `recover-streamdeck.c` | USB power / reset via IOKit |
| `usb-reenumerate.c` | Force reenumerate |
| `audio_protect.py` | Hold mute and restore levels |
| `com.example.streamdeck-wake-reset.plist.example` | LaunchAgent template — edit paths |

## Build / install

Compile the Swift and C files for your Mac. Put binaries on your `PATH` (for example `~/.local/bin`). Adjust the plist to match. You need permission to control the USB hub (`uhubctl` or the IOKit tools).

Licensed with the rest of this repository (Prosperity).
