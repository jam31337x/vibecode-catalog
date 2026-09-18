#!/bin/zsh
set -euo pipefail

# Power-cycle the USB hub port that feeds the Stream Deck Plus
# (it sits on the XLR Dock's ganged hub; that hub cannot be reset per-port).

UHUBCTL=/opt/homebrew/bin/uhubctl
LOG="$HOME/Library/Logs/streamdeck-wake-reset.log"

log() {
  local line
  line="$(date -u +"%Y-%m-%dT%H:%M:%SZ") $*"
  print -- "$line" | tee -a "$LOG" >&2
}

find_parent_port() {
  "$UHUBCTL" | python3 -c '
import sys, re
hub = None
for line in sys.stdin:
    m = re.search(r"Current status for hub (\S+)", line)
    if m:
        hub = m.group(1)
        continue
    m = re.search(r"Port (\d+):.*\[1a40:0101", line, re.I)
    if m and hub:
        print(hub, m.group(1))
        break
'
}

killall "Stream Deck" >/dev/null 2>&1 || true
sleep 1

PROTECT="$HOME/.local/bin/audio-protect"

if [[ ! -x $UHUBCTL ]]; then
  log "uhubctl missing — relaunching Stream Deck only"
  open -ga "Elgato Stream Deck"
  exit 1
fi

pair="$(find_parent_port || true)"
if [[ -z ${pair} ]]; then
  log "could not find parent hub for Stream Deck (1a40:0101)"
  open -ga "Elgato Stream Deck"
  exit 1
fi

hub="${pair%% *}"
port="${pair##* }"
if [[ -x $PROTECT ]]; then
  log "audio-protect hold-mute (ear safety before USB cycle)"
  "$PROTECT" hold-mute >/dev/null 2>&1 || true
fi
log "USB power-cycle hub $hub port $port (Stream Deck + XLR Dock hub)"
"$UHUBCTL" -l "$hub" -p "$port" -a off >/dev/null
sleep 2
"$UHUBCTL" -l "$hub" -p "$port" -a on >/dev/null

reappeared=0
for _ in {1..20}; do
  if hidutil list 2>/dev/null | grep -q "Stream Deck Plus"; then
    reappeared=1
    break
  fi
  sleep 0.4
done

if [[ $reappeared -eq 1 ]]; then
  log "Stream Deck Plus HID is back"
else
  log "HID did not reappear within timeout"
fi

open -ga "Elgato Stream Deck"
log "Stream Deck app launched"

if [[ -x $PROTECT ]]; then
  # XLR Dock enumerates after the hub comes back; restore saved gain/output.
  for _ in {1..25}; do
    if "$PROTECT" status 2>/dev/null | grep -q '"xlr_id": [^n]'; then
      break
    fi
    sleep 0.2
  done
  log "audio-protect restore saved gain/output"
  "$PROTECT" restore >/dev/null 2>&1 || true
fi
