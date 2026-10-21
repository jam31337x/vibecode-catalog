# Stream Deck wake recovery (Mac)

When a Stream Deck (often on an XLR dock hub) stops working after sleep, a USB power-cycle helps — but cycling USB can spike audio. Mute first.

Sources: `tools/streamdeck-wake-safe/`

## Hearing safety (`audio_protect.py`)

Run the listener in the background (`audio-protect run`). It saves mic gain and watches XLR Dock + Boom outputs.

- **Before USB cycle:** `hold-mute` (used by `streamdeck-reset.zsh`).
- **When the dock reappears:** outputs go to **20%**, mic gain unchanged, ~**2.5s** guard while hardware settles.
- **After reset:** `restore` sets **20%** and unmutes if you were holding mute.
- **Jump clamp:** if CoreAudio output jumps **≥ +10%** in one poll vs the last accepted level, clamp back to **20%** (Wave Link too). Gradual knob moves under +10% are intentional. **1.5s** cooldown after a clamp. Detection runs on the poll loop, not HAL listeners.

Optional: `save` / `status` for mic gain and live levels.

## Order

1. `hold-mute` (or ensure the listener is running and will mute on hold).
2. Power-cycle the hub port that feeds the Deck / dock (`uhubctl` or the C helpers).
3. Wait until the Stream Deck shows up again in USB/HID.
4. Open the Elgato Stream Deck app.
5. `restore` if needed; raise volume gradually from **20%**.

Point the LaunchAgent example at your own `$HOME` paths before installing it.
