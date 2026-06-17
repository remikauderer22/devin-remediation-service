import os
import sqlite3
import requests
import asyncio
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI()

DEVIN_API_KEY = os.environ.get("DEVIN_API_KEY")
DEVIN_API_URL = "https://api.devin.ai/v1/sessions"
DB_PATH = "sessions.db"

ISSUES = {
    "flask": {
        "title": "Upgrade Flask to fix CVE-2026-27205",
        "repo": "remikauderer22/superset",
        "prompt": "In the repository remikauderer22/superset, create a new branch called fix/flask-cve-2026-27205 (do not work on master/main directly). On that branch, upgrade the installed Flask version to 3.1.3 or later to remediate CVE-2026-27205, a session cache-poisoning issue (GHSA-68rp-wp8r-4726). Verify the existing test suite still passes. Open a pull request into master with a clear description. Do not merge it yourself.",
        "estimated_hours": 1.5,
    },
    "cryptography": {
        "title": "Upgrade cryptography to fix bundled OpenSSL vulnerability",
        "repo": "remikauderer22/superset",
        "prompt": "In the repository remikauderer22/superset, create a new branch called fix/cryptography-ghsa-537c (do not work on master/main directly). The cryptography package is pinned at >=42.0.4, <47.0.0 in pyproject.toml, but the fix for GHSA-537c-gmf6-5ccf (a high-severity vulnerability from a bundled OpenSSL version) requires cryptography >=48.0.1. Raise the version ceiling in pyproject.toml to allow this, and upgrade the installed version. Note: there's an unrelated mypy override comment near the cryptography dependency referencing a different issue from version 44.0.3 - do not assume it's related to this version cap. Verify the test suite still passes. Open a pull request into master explaining that the root cause is a bundled OpenSSL issue, not cryptography's own code. Do not merge it yourself.",
        "estimated_hours": 3.0,
    },
    "pyjwt": {
        "title": "Upgrade PyJWT to fix unbounded JWKS request vulnerability",
        "repo": "remikauderer22/superset",
        "prompt": "In the repository remikauderer22/superset, create a new branch called fix/pyjwt-cve-2026-48524 (do not work on master/main directly). Upgrade PyJWT to 2.13.0 or later to fix CVE-2026-48524, where PyJWKClient.get_signing_key() makes unbounded HTTP requests for unrecognized kid values with no rate limiting. A repo-wide search confirms Superset's own code does not call PyJWKClient directly, so this should not require first-party code changes beyond the dependency bump. Verify the test suite still passes. Open a pull request into master with a clear description. Do not merge it yourself.",
        "estimated_hours": 2.0,
    },
    "demo": {
        "title": "[DEMO] Example issue for scheduler demonstration",
        "repo": "remikauderer22/superset",
        "prompt": "In the repository remikauderer22/superset, just reply confirming you received this prompt. Do not make any code changes, branches, or pull requests — this is a demo of the scheduling system only, not a real remediation task.",
        "estimated_hours": 0.0,
    },
}

def init_db():
    """Creates the sessions table if it doesn't already exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            devin_session_id TEXT PRIMARY KEY,
            issue_id TEXT,
            issue_title TEXT,
            status TEXT,
            devin_session_url TEXT,
            estimated_hours REAL,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_session(devin_session_id, issue_id, issue_title, devin_session_url, estimated_hours):
    """Records a newly created session in the database with status 'running'."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO sessions (devin_session_id, issue_id, issue_title, status, devin_session_url, estimated_hours, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (devin_session_id, issue_id, issue_title, "running", devin_session_url, estimated_hours, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

def get_triggered_issue_ids():
    """Returns the set of issue_ids that already have at least one session."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT DISTINCT issue_id FROM sessions").fetchall()
    conn.close()
    return {row[0] for row in rows}

async def scheduled_remediation_loop():
    """Background loop: periodically checks for untriggered issues and remediates them."""
    while True:
        await asyncio.sleep(60)  # check every 60 seconds (short for demo purposes)
        triggered = get_triggered_issue_ids()
        for issue_id, issue in ISSUES.items():
            if issue_id not in triggered:
                print(f"[scheduler] Found untriggered issue '{issue_id}' — starting remediation")
                devin_response = start_devin_session(issue["prompt"])
                save_session(
                    devin_session_id=devin_response["session_id"],
                    issue_id=issue_id,
                    issue_title=issue["title"],
                    devin_session_url=devin_response["url"],
                    estimated_hours=issue["estimated_hours"],
                )

def start_devin_session(prompt: str) -> dict:
    """Calls the Devin API to create a new session. Returns Devin's response."""
    response = requests.post(
        DEVIN_API_URL,
        headers={
            "Authorization": f"Bearer {DEVIN_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"prompt": prompt},
    )
    response.raise_for_status()
    return response.json()

def get_devin_session_status(devin_session_id: str) -> dict:
    """Asks Devin's API for the current status of an existing session."""
    response = requests.get(
        f"{DEVIN_API_URL}/{devin_session_id}",
        headers={"Authorization": f"Bearer {DEVIN_API_KEY}"},
    )
    response.raise_for_status()
    return response.json()

def update_session_status(devin_session_id: str, status: str, pr_url: str = None):
    """Updates a session's status (and optionally its PR URL) in the database."""
    conn = sqlite3.connect(DB_PATH)
    if pr_url:
        conn.execute(
            "UPDATE sessions SET status = ?, pr_url = ? WHERE devin_session_id = ?",
            (status, pr_url, devin_session_id),
        )
    else:
        conn.execute(
            "UPDATE sessions SET status = ? WHERE devin_session_id = ?",
            (status, devin_session_id),
        )
    conn.commit()
    conn.close()

def get_dashboard_data():
    """Computes summary stats across all sessions for the observability dashboard."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT issue_id, issue_title, status, devin_session_url, pr_url, estimated_hours, created_at FROM sessions"
    ).fetchall()
    conn.close()

    sessions = []
    total_hours_saved = 0.0
    status_counts = {}

    for row in rows:
        issue_id, issue_title, status, session_url, pr_url, estimated_hours, created_at = row
        sessions.append({
            "issue_id": issue_id,
            "issue_title": issue_title,
            "status": status,
            "session_url": session_url,
            "pr_url": pr_url,
            "estimated_hours": estimated_hours,
            "created_at": created_at,
        })
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "completed":
            total_hours_saved += estimated_hours

    return {
        "total_sessions": len(sessions),
        "status_counts": status_counts,
        "estimated_hours_saved": total_hours_saved,
        "note": "estimated_hours_saved is based on manual-effort estimates set per issue at filing time, not measured data",
        "sessions": sessions,
    }

async def status_polling_loop():
    """Background loop: periodically checks all 'running' sessions and updates their status."""
    while True:
        await asyncio.sleep(30)  # check every 30 seconds
        conn = sqlite3.connect(DB_PATH)
        running = conn.execute(
            "SELECT devin_session_id FROM sessions WHERE status = 'running'"
        ).fetchall()
        conn.close()

        for (devin_session_id,) in running:
            try:
                devin_data = get_devin_session_status(devin_session_id)
                pr_url = None
                if devin_data.get("pull_request"):
                    pr_url = devin_data["pull_request"].get("url")

                if pr_url:
                    new_status = "completed"
                elif devin_data.get("status_enum") == "blocked":
                    new_status = "blocked"
                else:
                    new_status = devin_data.get("status_enum", "running")

                update_session_status(devin_session_id, new_status, pr_url)
                print(f"[polling] {devin_session_id} -> {new_status}" + (f" (PR: {pr_url})" if pr_url else ""))
            except Exception as e:
                print(f"[polling] Error checking {devin_session_id}: {e}")

@app.on_event("startup")
async def on_startup():
    init_db()
    asyncio.create_task(scheduled_remediation_loop())
    asyncio.create_task(status_polling_loop())

@app.get("/")
def root():
    return {"status": "Devin remediation service is running"}

@app.get("/issues")
def list_issues():
    return ISSUES

@app.get("/test-status/{devin_session_id}")
def test_status(devin_session_id: str):
    return get_devin_session_status(devin_session_id)

@app.get("/dashboard/view", response_class=HTMLResponse)
def dashboard_view():
    data = get_dashboard_data()

    rows_html = ""
    for s in data["sessions"]:
        pr_link = f'<a href="{s["pr_url"]}" target="_blank">View PR</a>' if s["pr_url"] else "—"
        rows_html += f"""
        <tr>
            <td>{s["issue_title"]}</td>
            <td><span class="status {s["status"]}">{s["status"]}</span></td>
            <td>{s["estimated_hours"]}</td>
            <td>{pr_link}</td>
        </tr>
        """

    html = f"""
    <html>
    <head>
        <title>Devin Remediation Dashboard</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; color: #1a1a1a; }}
            h1 {{ font-size: 22px; }}
            .summary {{ display: flex; gap: 24px; margin: 24px 0; }}
            .stat {{ background: #f5f5f5; padding: 16px 20px; border-radius: 8px; }}
            .stat .number {{ font-size: 28px; font-weight: 600; }}
            .stat .label {{ font-size: 13px; color: #666; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
            th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
            .status {{ padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
            .status.completed {{ background: #d4edda; color: #155724; }}
            .status.blocked {{ background: #fff3cd; color: #856404; }}
            .status.running {{ background: #d1ecf1; color: #0c5460; }}
            .note {{ font-size: 12px; color: #888; margin-top: 16px; }}
        </style>
    </head>
    <body>
        <h1>Devin Remediation Dashboard</h1>
        <div class="summary">
            <div class="stat"><div class="number">{data["total_sessions"]}</div><div class="label">Total Sessions</div></div>
            <div class="stat"><div class="number">{data["status_counts"].get("completed", 0)}</div><div class="label">Completed</div></div>
            <div class="stat"><div class="number">{data["estimated_hours_saved"]}</div><div class="label">Est. Hours Saved</div></div>
        </div>
        <table>
            <tr><th>Issue</th><th>Status</th><th>Est. Hours</th><th>Pull Request</th></tr>
            {rows_html}
        </table>
        <div class="note">{data["note"]}</div>
    </body>
    </html>
    """
    return html

@app.post("/remediate/{issue_id}")
def remediate(issue_id: str):
    if issue_id not in ISSUES:
        raise HTTPException(status_code=404, detail=f"No issue found with id '{issue_id}'")

    issue = ISSUES[issue_id]
    devin_response = start_devin_session(issue["prompt"])

    save_session(
        devin_session_id=devin_response["session_id"],
        issue_id=issue_id,
        issue_title=issue["title"],
        devin_session_url=devin_response["url"],
        estimated_hours=issue["estimated_hours"],
    )

    return {
        "issue_id": issue_id,
        "issue_title": issue["title"],
        "devin_session_id": devin_response["session_id"],
        "devin_session_url": devin_response["url"],
    }