# Match Stream Deck brightness to the MacBook screen

Want the Stream Deck keys to dim and brighten with the laptop display (same percentage)?

Sources: `tools/streamdeck-brightness-sync/`

## Setup

```bash
cd tools/streamdeck-brightness-sync
./install.sh
```

1. Wait for Stream Deck to reopen.
2. Add **Brightness Sync** to a profile (folder is fine).
3. Change Mac display brightness — Deck keys should track 0–100% in lockstep.

The plugin polls the main display via DisplayServices and calls Stream Deck `setBrightness` when the value moves by at least 1%.
