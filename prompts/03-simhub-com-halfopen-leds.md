# SimHub: COM half-open, factory LEDs

**Job:** Explain and fix this pattern: game still running, SimHub was soft-restarted, wheel/CM LEDs show stock/factory colors, serial looks open but nothing useful comes back (half-open). Soft reset of the wheel port is blocked while the game holds the device.

## Do

- Do not recommend another SimHub restart as the fix.
- Prefer: leave the game up, **power-cycle the wheel base**, wait for identify, confirm Deck owns the LEDs again.
- Keep “confirmed once” identity separate from “alive right now” health.

## Answer with

1. **Verdict** and confidence.
2. **Why a soft SimHub restart fails** here (mechanism).
3. **Recovery steps** with stop conditions.
4. **How to verify** — which log lines or port-status fields mean LEDs are owned again.
5. **Rules for next time** — five short bullets.
