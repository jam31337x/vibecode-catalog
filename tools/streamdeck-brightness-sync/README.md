# Stream Deck ↔ Mac brightness sync

Keeps Stream Deck key LED brightness matched 1:1 to the MacBook **main display** brightness (Mac 75% → Deck 75%).

## Why v1.0 did not move the LEDs

Elgato Stream Deck **7.x removed** the plugin WebSocket `setBrightness` API. Updating `map_dev_brightness` in prefs does **not** change live LEDs. While Stream Deck.app is open it holds **exclusive HID**, so nothing else can send the brightness feature report.

## How v1.1 works

LaunchAgent `com.jam.streamdeck-brightness-sync` polls Mac brightness via `bin/mac-brightness` (DisplayServices). When it changes (debounced ~0.85s):

1. Quit Stream Deck.app briefly  
2. Set brightness over USB HID (`apply_brightness.py` + Python `streamdeck`)  
3. Write `map_dev_brightness` so the app restores the same level on launch  
4. Relaunch Stream Deck.app  

Expect a short Stream Deck restart when you change Mac brightness.

## Install

```bash
cd tools/streamdeck-brightness-sync
bash install.sh
```

Needs: macOS, `python3` with `pip3 install streamdeck`, Swift (`swiftc`), and a Stream Deck supported by python-elgato-streamdeck.

Sync runs as a LaunchAgent — **no Stream Deck key required**.

Optional status plugin `com.jam.brightness-sync` only shows Mac `%` on a key; it does not drive LEDs.

## Logs

`~/Library/Logs/streamdeck-brightness-sync.log`

## Uninstall

```bash
launchctl bootout "gui/$(id -u)/com.jam.streamdeck-brightness-sync"
rm -f ~/Library/LaunchAgents/com.jam.streamdeck-brightness-sync.plist
rm -rf ~/.local/share/streamdeck-brightness-sync
```
