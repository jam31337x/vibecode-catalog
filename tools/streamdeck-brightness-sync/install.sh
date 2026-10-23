#!/bin/zsh
# Install Brightness Sync plugin into Elgato Stream Deck (macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_SRC="$ROOT/com.jam.brightness-sync.sdPlugin"
PLUGIN_DST="$HOME/Library/Application Support/com.elgato.StreamDeck/Plugins/com.jam.brightness-sync.sdPlugin"
HELPER_SRC="$ROOT/mac-brightness.swift"
HELPER_DST="$PLUGIN_SRC/bin/mac-brightness"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS only." >&2
  exit 1
fi

if [[ ! -d "/Applications/Elgato Stream Deck.app" ]]; then
  echo "Elgato Stream Deck app not found in /Applications." >&2
  exit 1
fi

echo "Compiling mac-brightness helper…"
mkdir -p "$PLUGIN_SRC/bin"
swiftc -O -o "$HELPER_DST" "$HELPER_SRC"
chmod 755 "$HELPER_DST" "$PLUGIN_SRC/bin/plugin.js"
"$HELPER_DST" >/dev/null

echo "Installing plugin → $PLUGIN_DST"
mkdir -p "$(dirname "$PLUGIN_DST")"
rm -rf "$PLUGIN_DST"
# Prefer ditto to preserve exec bits
ditto "$PLUGIN_SRC" "$PLUGIN_DST"
# Do not ship a stale helper path; recompile into destination too
swiftc -O -o "$PLUGIN_DST/bin/mac-brightness" "$HELPER_SRC"
chmod 755 "$PLUGIN_DST/bin/mac-brightness" "$PLUGIN_DST/bin/plugin.js"

echo "Restarting Stream Deck…"
killall "Stream Deck" 2>/dev/null || true
sleep 1
open -a "Elgato Stream Deck"
sleep 2

echo
echo "Installed."
echo "In Stream Deck software: drag **Brightness Sync** onto a key (can live under a folder)."
echo "Then move the Mac brightness slider — the Deck keys should follow 1:1 (0–100%)."
echo
echo "Mac brightness now: $("$PLUGIN_DST/bin/mac-brightness")%"
