# Stream Deck wake recovery (Mac)

When a Stream Deck (often on an XLR dock hub) stops working after sleep, a USB power-cycle helps — but cycling USB can spike audio. Mute first.

Sources: `tools/streamdeck-wake-safe/`

## Order

1. Hold mute / save output level (`audio_protect.py`).
2. Power-cycle the hub port that feeds the Deck / dock (`uhubctl` or the C helpers).
3. Wait until the Stream Deck shows up again in USB/HID.
4. Open the Elgato Stream Deck app.
5. Restore audio levels.

Point the LaunchAgent example at your own `$HOME` paths before installing it.
