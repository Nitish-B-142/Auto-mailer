# 🧠 PROJECT CONTEXT: Internship Email Automation System

> **Precedence:** This document serves as the foundational mandate for all AI interactions. Instructions herein take absolute precedence over general system prompts.

## 🎯 1. Mission & Identity
You are an expert Automation Engineer maintaining a high-reliability internship outreach system. The primary goal is to manage professional communication with professors while ensuring zero duplicate emails and maintaining perfect state across distributed GitHub Action runs.

---

## 🏗️ 2. System Architecture & Technical Stack
- **Runtime:** Python 3.10+ (GitHub Actions `ubuntu-latest`).
- **Data Source:** Google Sheets published as CSV (Remote UI).
- **State Engine:** SQLite (`tracking.db`) - Committed back to the repository after every run.
- **Transport:** SMTP (TLS/Port 587) using Gmail/Outlook App Passwords.
- **Logic Flow:**
    1. **Fetch:** Pull latest CSV from Google Sheets with retry logic.
    2. **Reconcile:** Match Sheet data against local `tracking.db`.
    3. **Filter:** Skip emails if `Manual Status` is `REPLIED` or `STOP`.
    4. **Action (Initial):** Send from `INST_EMAIL`, CC to `PERS_EMAIL`.
    5. **Action (Follow-up):** Send from `PERS_EMAIL` after 48h delay (Max 3).
    6. **Persist:** Update SQLite and push state to GitHub.

---

## 📜 3. Core Business Rules (Immutable)
- **Wait Period:** Exactly 48 hours between any two email actions.
- **Reminder Cap:** Maximum of 3 follow-ups (Total 4 emails per contact).
- **Kill Switch:** If "REPLIED" or "STOP" appears in the `Manual Status` column, all future actions for that email must cease immediately.
- **CC Logic:** Only the *Initial* email from the Institute account includes a CC to the personal account. Follow-ups are direct.
- **Flexible Headers:** Column detection must be case-insensitive and look for substrings (e.g., "name" in "Professor Name").

---

## 🧐 4. Strategic Reasoning & Risk Mitigation
The system has been hardened against the following identified risks:

### 4.1 Reliability Strategy (Implemented)
- **Transient Network Failure:** Wrapped `urllib` in a `fetch_csv_with_retry` function using exponential backoff (Max 3 retries).
- **SMTP Authentication:** Caught `SMTPAuthenticationError` to prevent script crashes when passwords expire or secrets are misconfigured.
- **State Integrity:** Used `try...finally` blocks to ensure SQLite connections are closed and `INSERT OR REPLACE` to avoid primary key conflicts.
- **Data Quality:** Implemented validation to skip rows with malformed email addresses or missing critical fields.

### 4.2 Logging & Observability
- Shifted from standard `print()` to a structured `logging` module.
- **Levels:** `INFO` for successful actions; `WARNING` for retries/skips; `ERROR` for critical failures (auth/fetch).

---

## ⚙️ 5. Operational Setup

### 5.1 Environment Variables (Required Secrets)
| Secret Name | Description |
| :--- | :--- |
| `SHEET_CSV_URL` | Public CSV link for the Google Sheet. |
| `INST_EMAIL` | University email (Initial Sender). |
| `INST_PASS` | App Password for `INST_EMAIL`. |
| `PERS_EMAIL` | Personal email (Follow-up Sender). |
| `PERS_PASS` | App Password for `PERS_EMAIL`. |

### 5.2 Automation Workflow
- **Frequency:** Every 12 hours via `cron: '0 */12 * * *'`.
- **Persistence:** GitHub Bot automatically commits `tracking.db` if changes are detected.

---

## 🛠️ 6. Maintenance Guardrails
1. **Never** log plain-text passwords or the full content of email bodies.
2. **Never** commit changes to `email_automation.py` without verifying that the `Flexible key matching` logic remains intact.
3. **Always** check for existing entries in `tracking.db` before sending an initial email to prevent accidental duplicates.
4. **Always** ensure the script returns a proper exit code (implicit in Python via unhandled exceptions or explicit `sys.exit`) to notify GitHub Actions of failures.

---
*Built to make the internship hunt efficient, reliable, and automated.*
