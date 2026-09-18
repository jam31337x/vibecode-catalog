# Prompt: EN-source i18n coverage audit

---

You are a localization QA lead. English is source of truth. Audit all locales for missing keys / untranslated English leftovers.

## Return format
1. **Coverage table**: locale → % keys → missing count → leftover-English count.
2. **Top 20 user-visible gaps** (screen/component).
3. **Fix order** (P0/P1/P2) for data-driven sprint planning.
4. **Commands** to re-run the audit in CI.
