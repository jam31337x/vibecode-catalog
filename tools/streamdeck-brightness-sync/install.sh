#!/usr/bin/env bash
# Install Stream Deck ↔ Mac brightness sync (LaunchAgent + HID apply helper).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${HOME}/.local/share/streamdeck-brightness-sync"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
LABEL="com.jam.streamdeck-brightness-sync"
PLIST_DST="${LAUNCH_AGENTS}/${LABEL}.plist"
PLUGIN_SRC="${ROOT}/com.jam.brightness-sync.sdPlugin"
PLUGIN_DST="${HOME}/Library/Application Support/com.elgato.StreamDeck/Plugins/com.jam.brightness-sync.sdPlugin"

echo "==> Building mac-brightness helper"
mkdir -p "${ROOT}/bin" "${INSTALL_DIR}/bin"
swiftc -O -o "${ROOT}/bin/mac-brightness" "${ROOT}/mac-brightness.swift"

echo "==> Installing files to ${INSTALL_DIR}"
cp -f "${ROOT}/bin/mac-brightness" "${INSTALL_DIR}/bin/mac-brightness"
cp -f "${ROOT}/apply_brightness.py" "${INSTALL_DIR}/apply_brightness.py"
cp -f "${ROOT}/sync_daemon.py" "${INSTALL_DIR}/sync_daemon.py"
chmod +x "${INSTALL_DIR}/bin/mac-brightness" "${INSTALL_DIR}/apply_brightness.py" "${INSTALL_DIR}/sync_daemon.py"

PYTHON="$(command -v python3)"
if ! "${PYTHON}" -c 'from StreamDeck.DeviceManager import DeviceManager' 2>/dev/null; then
  echo "error: Python package 'streamdeck' is required (pip3 install streamdeck)" >&2
  exit 1
fi

echo "==> Installing LaunchAgent ${LABEL}"
mkdir -p "${LAUNCH_AGENTS}"
# shellcheck disable=SC2002
sed \
  -e "s|__PYTHON__|${PYTHON}|g" \
  -e "s|__DAEMON__|${INSTALL_DIR}/sync_daemon.py|g" \
  -e "s|__INSTALL__|${INSTALL_DIR}|g" \
  -e "s|__HOME__|${HOME}|g" \
  "${ROOT}/com.jam.streamdeck-brightness-sync.plist" > "${PLIST_DST}"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_DST}"
launchctl enable "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || launchctl start "${LABEL}" || true

echo "==> Optional status plugin (title only; sync is the LaunchAgent)"
if [[ -d "${PLUGIN_SRC}" ]]; then
  mkdir -p "$(dirname "${PLUGIN_DST}")"
  rsync -a --delete "${PLUGIN_SRC}/" "${PLUGIN_DST}/"
  cp -f "${INSTALL_DIR}/bin/mac-brightness" "${PLUGIN_DST}/bin/mac-brightness"
fi

echo "==> Forcing one apply (Deck = 90% of Mac / 10% dimmer)"
MAC="$("${INSTALL_DIR}/bin/mac-brightness" || true)"
if [[ -n "${MAC}" ]]; then
  DECK="$("${PYTHON}" -c "print(max(0, min(100, round(int('${MAC}') * 0.90))))")"
  echo "    Mac ${MAC}% → Deck ${DECK}%"
  # Try HID first; quit only if needed (Stream Deck.app exclusive access).
  if ! "${PYTHON}" "${INSTALL_DIR}/apply_brightness.py" "${DECK}"; then
    osascript -e 'tell application "Stream Deck" to quit' >/dev/null 2>&1 || true
    for _ in $(seq 1 40); do
      pgrep -x "Stream Deck" >/dev/null || break
      sleep 0.1
    done
    pkill -x "Stream Deck" 2>/dev/null || true
    sleep 0.3
    "${PYTHON}" "${INSTALL_DIR}/apply_brightness.py" "${DECK}" || true
    open -a "Elgato Stream Deck" 2>/dev/null || true
  fi
fi

echo "OK — LaunchAgent ${LABEL} installed."
echo "    Mapping: Deck = 90% of Mac (10% dimmer)."
echo "    Logs: ~/Library/Logs/streamdeck-brightness-sync.log"
echo "    HID first (official docs); Stream Deck restarts only if HID is exclusive."
