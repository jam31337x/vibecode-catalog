# Match Stream Deck brightness to the MacBook screen

Deck LEDs track the laptop display at **85% of Mac brightness** (15% dimmer).

Sources: `tools/streamdeck-brightness-sync/`

Official path: [HID Set Backlight Brightness](https://docs.elgato.com/streamdeck/hid/general) (feature report `0x03`/`0x08`). Plugin SDK has no brightness API.

## Setup

```bash
cd tools/streamdeck-brightness-sync
./install.sh
```

Requires `pip3 install streamdeck` and Swift.

1. LaunchAgent `com.jam.streamdeck-brightness-sync` starts automatically.
2. Change Mac brightness — Deck follows at 85% of Mac (HID; brief Stream Deck restart only if HID is exclusive).
3. Optional status key shows Mac `%` only.

Logs: `~/Library/Logs/streamdeck-brightness-sync.log`
