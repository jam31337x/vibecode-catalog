# Match Stream Deck brightness to the MacBook screen

Deck LEDs follow Mac brightness with a locked calibration: **Mac 75% → Deck 42%** (manual lock), linear scale, **cap 55%**.

Sources: `tools/streamdeck-brightness-sync/` · config: `config.json`

## Setup

```bash
cd tools/streamdeck-brightness-sync
./install.sh
```

Requires `pip3 install streamdeck` and Swift.

Edit `~/.local/share/streamdeck-brightness-sync/config.json` to change the anchor or cap.

Logs: `~/Library/Logs/streamdeck-brightness-sync.log`
