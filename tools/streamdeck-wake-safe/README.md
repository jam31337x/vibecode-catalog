# streamdeck-wake-safe

Mac helpers for a flaky Elgato Stream Deck after sleep/wake. Audio is muted around the USB cycle so headphones don’t get a blast when the XLR dock reappears.

## Files

| File | Role |
|------|------|
| `streamdeck-wake-watch.swift` | Background watcher (compile; run from a LaunchAgent) |
| `streamdeck-reset.zsh` | Quit Stream Deck app → cycle hub → relaunch → restore audio |
| `recover-streamdeck.c` | USB power / reset via IOKit |
| `usb-reenumerate.c` | Force reenumerate |
| `audio_protect.py` | Mute around USB reset; clamp reconnect and output jumps |
| `com.example.streamdeck-wake-reset.plist.example` | LaunchAgent template — edit paths |

## `audio_protect.py`

Background listener (Elgato Wave Link + CoreAudio). Keeps mic gain; caps **main outputs** at **20%** when the XLR Dock reconnects or CoreAudio jumps unexpectedly.

**On XLR Dock reconnect / USB reset:** mute-first if `hold-mute` is set, force XLR Dock and Boom outputs to **20%**, keep mic gain, then hold that level for ~**2.5s** so a late hardware spike cannot blast headphones.

**Unexpected output jump:** on each poll (not HAL volume callbacks — avoids fighting Stream Deck / re-entrancy), if XLR Dock and/or Boom rises **≥ +10%** vs the last accepted sample, clamp outputs back to **20%** (CoreAudio + Wave Link). Smaller knob steps update the baseline. **1.5s** cooldown after a jump clamp to avoid thrash.

**CLI** (install as `audio-protect` on your `PATH`):

`run` · `save` · `status` · `hold-mute` · `restore`

`hold-mute` before the USB cycle; `restore` after the dock is back (`streamdeck-reset.zsh` uses both).

## Build / install

Compile the Swift and C files for your Mac. Put binaries on your `PATH` (for example `~/.local/bin`). Adjust the plist to match. You need permission to control the USB hub (`uhubctl` or the IOKit tools).

Licensed with the rest of this repository (Prosperity).
