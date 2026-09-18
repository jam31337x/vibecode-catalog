# SimHub Deck (public overview)

Installers are published on **[SimHub-Deck-Releases](https://github.com/jam31337x/SimHub-Deck-Releases)** (source may remain private).

## What it solves
- Stream Deck ↔ SimHub bridge for MOZA-style wheel/CM dash LEDs
- Safety around serial ownership (do not soft-reset wheel COM mid-game)
- Ambient RGBIC helpers and wind/fan tooling in the wider Deck ecosystem

## Ops hard rule
If LEDs go “factory” after a SimHub soft restart mid-session, **power-cycle the wheel base** — do not keep restarting SimHub.
