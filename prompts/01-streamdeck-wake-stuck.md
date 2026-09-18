# Prompt: Stream Deck stuck after Mac wake (hearing-safe)

Copy-paste this into Cursor/ChatGPT as a **single job**.

---

You are a macOS USB/HID reliability engineer. Goal: explain why an Elgato Stream Deck (often on an XLR Dock hub) is stuck or dead after wake/sleep, and give a **data-driven recovery plan** that never blasts audio into headphones.

## Constraints
- Prefer non-destructive diagnosis first (logs, `system_profiler SPUSBDataType`, Console, LaunchAgents).
- If USB power-cycle is required, **mute / hold output gain BEFORE** cycling the hub, restore AFTER the XLR/Stream Deck reappear.
- Do not invent vendor private APIs. Use public tools (`uhubctl`, IOKit reenumerate, kill/relaunch Stream Deck app).
- Output must help a human decide: reboot Mac vs hub cycle vs reseat cable vs replace dock.

## Return format (markdown)
1. **Executive verdict** (1–2 sentences): most likely root cause + confidence (high/med/low).
2. **Evidence table**: signal → observation → implication.
3. **Decision tree**: numbered steps with stop conditions.
4. **Hearing-safety checklist**: exact mute/restore order.
5. **Prevention**: LaunchAgent/watch pattern (high level) if wake recurrence is likely.
6. **Open questions**: only if evidence is missing.

Do not dump raw logs without interpretation.
