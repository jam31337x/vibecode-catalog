# streamdeck-brightness-sync

Keeps Elgato Stream Deck **key brightness** matched to the **MacBook main display** brightness, 1:1 (75% Mac → 75% Deck, 0% → 0%).

## How it works

Stream Deck plugin `com.jam.brightness-sync` (Node 24) polls about every **400ms** via a small Swift helper that reads Apple **DisplayServices**. When the Mac level changes by **≥ 1%**, the plugin sends `setBrightness` to Stream Deck software and best-effort updates `map_dev_brightness` in preferences so Settings stays aligned.

## Files

| File | Role |
|------|------|
| `mac-brightness.swift` | Reads main-display brightness (0–100) |
| `install.sh` | Compile helper, install plugin, restart Stream Deck |
| `com.jam.brightness-sync.sdPlugin/` | Plugin (manifest, `bin/plugin.js`, icons) |

## Install

```bash
cd tools/streamdeck-brightness-sync
./install.sh
```

Requires macOS 12+, Elgato Stream Deck app, and Stream Deck hardware. The helper is compiled on your Mac (Apple Silicon or Intel).

After install, in Stream Deck software drag **Brightness Sync** onto a key once (it can live under a folder). The key title shows the current percent. Move the Mac brightness slider — the Deck should follow.

## Notes

- Sync runs while Stream Deck software is running and the plugin is loaded.
- Placing the action once gives a stable UI context; the plugin also applies brightness on device connect using the plugin UUID.
- Not for Windows; not a HID bypass of the Stream Deck app.

Licensed with the rest of this repository (Prosperity).
