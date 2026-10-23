# Stream Deck ↔ Mac brightness sync

Keeps Stream Deck key LED brightness locked to a calibrated point on the MacBook main display, scaled linearly, with a hard cap.

## Calibration (current)

Measured manual Stream Deck+ brightness **42%**, locked to **Mac 75%**:

| Mac | Deck |
| --- | --- |
| 0% | 0% |
| 50% | 28% |
| 75% | **42%** (anchor) |
| 100% | **55%** (cap; raw would be 56%) |

Config: `config.json` → `~/.local/share/streamdeck-brightness-sync/config.json`

```json
{
  "anchor_mac_pct": 75,
  "anchor_deck_pct": 42,
  "max_deck_pct": 55
}
```

Formula: `deck = min(max_deck, round(mac × anchor_deck / anchor_mac))`

## Official docs

| Source | Brightness API? |
| --- | --- |
| [Plugin SDK](https://docs.elgato.com/streamdeck/sdk/references/websocket/plugin/) | None |
| [HID Set Backlight Brightness](https://docs.elgato.com/streamdeck/hid/general) | Feature report `0x03` / `0x08`, 0–100 |

Tries HID first; brief Stream Deck quit/relaunch only if a deck is plugged in but HID is exclusive. **If the Stream Deck is unplugged, the daemon idles and does not restart Stream Deck.app.**

## Install

```bash
cd tools/streamdeck-brightness-sync
bash install.sh
```

Needs: macOS, `python3` + `pip3 install streamdeck`, Swift (`swiftc`).

Logs: `~/Library/Logs/streamdeck-brightness-sync.log`
