# AGENT OPERATIONAL GUIDELINES & PROTOCOLS

## 1. Operating Principles
1. **Strict Step-by-Step Gating**:
   - The project is divided into 9 sequential steps.
   - On initial execution, implement **Step 1 only**.
   - NEVER proceed to subsequent steps without explicit user authorization.
2. **Honesty & Verification**:
   - Run automated tests and terminal verification before reporting completion.
   - Never fabricate test runs, stream states, or playback capabilities.
   - Report actual terminal output and exit codes.
3. **Workspace Discipline**:
   - Inspect existing files before editing or overwriting.
   - Preserve working code and avoid disruptive rewrites.
4. **Security & Media Safeguards**:
   - Never proxy media streams through the Flask server.
   - Enforce SSRF validation for external URLs.
   - Exclude sensitive `.env`, logs, local databases (`.db`), and virtual environments (`.venv`) from version control.

---

## 2. Step Completion Report Format
After completing each development step, the agent MUST produce a structured report containing:

1. **Completed**: Specific features, models, endpoints, or UI elements built.
2. **Files changed**: Absolute or relative list of files created, updated, or removed.
3. **Validation**: Terminal commands executed (e.g., `pytest`, `python run.py`, curl checks) and their actual output.
4. **Known issues**: Any remaining limitations, defects, or technical debt.
5. **Next step**: Summary of the next planned step according to `global_live_tv_master_prompt.md`.

*Wait for explicit user approval before executing the next step.*
