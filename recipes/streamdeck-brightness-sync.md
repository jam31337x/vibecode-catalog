# Match Stream Deck brightness to the MacBook screen

Want the Stream Deck keys to dim and brighten with the laptop display (same percentage)?

Sources: `tools/streamdeck-brightness-sync/`

## Setup

```bash
cd tools/streamdeck-brightness-sync
./install.sh
```

Requires `pip3 install streamdeck` and a Swift toolchain.

1. LaunchAgent `com.jam.streamdeck-brightness-sync` starts automatically.
2. Change Mac display brightness — after a short debounce the Stream Deck app restarts briefly and key LEDs match (Elgato removed `setBrightness`; HID needs exclusive access).
3. Optional: add the **Brightness Sync** status key to show Mac `%` (not required for LED sync).

Logs: `~/Library/Logs/streamdeck-brightness-sync.log`
