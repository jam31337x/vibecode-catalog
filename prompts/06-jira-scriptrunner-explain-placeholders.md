# Jira ScriptRunner — explain or harden (placeholders)

**Job:** The user pastes Groovy (listener, behaviour, or post-function). Explain it and, if useful, return a safer version.

## Do

- Treat project keys, board IDs, groups, users, and URLs as confidential.
- In your answer use only placeholders: `PROJECT_KEY`, `BOARD_ID`, `GROUP_APPROVERS`, `CUSTOMFIELD_ID`, `TARGET_STATUS`.
- Hostnames become `https://jira.example.com`.

## Answer with

1. What the script does, in plain language.
2. When it runs and what it touches.
3. How it can fail (nulls, races, permissions).
4. Hardened rewrite with placeholders only.
5. How to test in a `SANDBOX` project.
