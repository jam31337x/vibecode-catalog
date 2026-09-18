# Stream Deck wake-safe recovery (Mac)

See sources under `tools/streamdeck-wake-safe/`.

Typical flow:
1. `audio_protect.py hold-mute` (or equivalent) before USB work
2. Power-cycle the hub port feeding the Stream Deck / XLR dock (`uhubctl` or IOKit helper)
3. Wait for HID “Stream Deck” to reappear
4. Relaunch Elgato Stream Deck.app
5. `audio_protect.py restore`

Install the LaunchAgent example only after rewriting paths for your `$HOME`.
