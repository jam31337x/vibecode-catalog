# Stream Deck stuck after Mac wake

**Job:** Figure out why an Elgato Stream Deck (often on an XLR Dock hub) is dead or stuck after sleep/wake, and give a recovery plan that does not blast audio into headphones.

## Do

- Start with logs and USB inventory (`system_profiler SPUSBDataType`, Console, LaunchAgents).
- If a USB power-cycle is needed: mute / hold output gain **before** cycling the hub; restore **after** the Deck (and XLR, if any) are back.
- Stick to normal tools: `uhubctl`, IOKit reenumerate, quit/relaunch Stream Deck.app.

## Answer with

1. **Verdict** — likely cause, confidence high/medium/low (2 sentences max).
2. **Evidence** — table: signal → what you saw → what it means.
3. **Steps** — numbered; stop when fixed.
4. **Hearing safety** — exact mute → cycle → restore order.
5. **Prevention** — only if this will keep happening (e.g. a small LaunchAgent).
6. **Missing info** — only if you cannot decide without it.

Skip raw log dumps unless a short excerpt proves the point.
