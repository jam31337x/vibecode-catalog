# Stream Deck ↔ Mac brightness sync

Keeps Stream Deck key LED brightness matched to the MacBook **main display**, at **75% of Mac** (25% dimmer). Example: Mac 100% → Deck 75%; Mac 80% → Deck 60%.

## Official docs (brightness)

| Source | Brightness API? |
| --- | --- |
| [Plugin SDK / websocket](https://docs.elgato.com/streamdeck/sdk/references/websocket/plugin/) | **None** — no `setBrightness` (removed from modern SDK) |
| [HID API — Set Backlight Brightness](https://docs.elgato.com/streamdeck/hid/general) | **Yes** — Feature Report `0x03` / command `0x08`, value `0–100` |

There is **no documented way** to set key brightness through Stream Deck.app or the plugin websocket while the app holds the device. HID requires opening the USB device; on macOS that fails with exclusive access when Stream Deck.app is running. This tool tries HID first (no restart); if blocked, it briefly quits → HID → relaunches.

## How it works

LaunchAgent `com.jam.streamdeck-brightness-sync` polls Mac brightness via `bin/mac-brightness` (DisplayServices). On change (debounced ~0.85s):

1. Map `deck = round(mac × 0.75)`  
2. Try HID feature report (official path)  
3. If exclusive: quit Stream Deck.app → HID + write `map_dev_brightness` → relaunch  

## Install

```bash
cd tools/streamdeck-brightness-sync
bash install.sh
```

Needs: macOS, `python3` + `pip3 install streamdeck`, Swift (`swiftc`).

No Stream Deck key required. Optional status plugin only shows Mac `%`.

## Logs

`~/Library/Logs/streamdeck-brightness-sync.log`

## Uninstall

```bash
launchctl bootout "gui/$(id -u)/com.jam.streamdeck-brightness-sync"
rm -f ~/Library/LaunchAgents/com.jam.streamdeck-brightness-sync.plist
rm -rf ~/.local/share/streamdeck-brightness-sync
```
