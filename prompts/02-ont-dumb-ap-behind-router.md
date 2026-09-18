# ONT / ISP box as dumb AP behind your router

**Job:** Decide if a consumer ONT/router (Huawei EchoLife / HG814x class, etc.) can sit behind your real router as AP or switch, and what blocks LAN-to-LAN traffic.

## Do

- Prefer read-only checks (status pages, config export, MAC tables). No factory reset unless the user asks.
- In the write-up, replace Wi-Fi passwords and ISP logins with `<REDACTED>`.
- Say clearly whether you are talking about bridge mode, AP mode, or LAN isolation / VLAN issues.

## Answer with

1. **Verdict** — works / works with caveats / does not work.
2. **Blockers** — ranked, each with evidence and a fix or workaround.
3. **Settings checklist** — UI paths or field names when known.
4. **Tests** — a short list (ping, DHCP, MAC learning) that proves success.
5. **Rollback** — how to undo without bricking the box.
