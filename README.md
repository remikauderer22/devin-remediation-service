# Devin Remediation Service

An event-driven automation service that uses the [Devin API](https://docs.devin.ai/api-reference/overview) to autonomously remediate security vulnerabilities in Apache Superset, with built-in observability into session status, outcomes, and estimated engineering time saved.

## The Problem
Security scanners are good at identifying vulnerabilities. What they're not good at is remediating them. Remediation still requires engineers to read advisories, understand how a dependency is used within a codebase, implement a fix, validate the change, and open a pull request. This project explores whether Devin can autonomously perform that entire workflow.

## How It Works
1. A background scheduler runs every 60 seconds and checks for any known issues that haven't been remediated yet
2. When it finds one (or when triggered manually via the `/remediate/{issue_id}` endpoint), it creates a Devin session with a detailed, context-aware prompt
3. Devin autonomously reads the codebase, understands the advisory, implements the fix, runs the test suite, and opens a pull request
4. A polling loop checks each active session every 30 seconds and updates the database when Devin completes, capturing the PR link
5. A dashboard at `/dashboard/view` shows real-time status of all sessions, success rates, and estimated engineering hours saved

## Architecture
```
GitHub Issue → Scheduler/API Trigger → Devin Session → PR Opened
                                            ↓
                                    Status Polling Loop
                                            ↓
                                    SQLite Database
                                            ↓
                                    Dashboard (/dashboard/view)
```
## Setup & Running Locally

### Prerequisites
- Python 3.11+
- A [Devin API key](https://app.devin.ai/org/settings/devin-api)

### Install dependencies
```bash
pip install -r requirements.txt
```

### Set your Devin API key
```bash
export DEVIN_API_KEY="your_key_here"
```

### Run the service
```bash
uvicorn main:app --reload
```

The service will start on `http://localhost:8000`.

## Running with Docker

### Build the image
```bash
docker build -t devin-remediation-service .
```

### Run the container
```bash
docker run -p 8000:8000 -e DEVIN_API_KEY="your_key_here" devin-remediation-service
```

## Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/issues` | GET | List all configured issues |
| `/remediate/{issue_id}` | POST | Manually trigger remediation for an issue (`flask`, `cryptography`, `pyjwt`) |
| `/dashboard` | GET | Raw JSON observability data |
| `/dashboard/view` | GET | Visual dashboard showing session status, PRs, and estimated hours saved |

## Superset Fork
The target repository is [remikauderer22/superset](https://github.com/remikauderer22/superset), a fork of Apache Superset. Three security vulnerabilities were identified via `pip-audit`, filed as issues, and remediated by Devin:

- [Issue #4](https://github.com/remikauderer22/superset/issues/4) → [PR #1](https://github.com/remikauderer22/superset/pull/1): Flask CVE-2026-27205
- [Issue #5](https://github.com/remikauderer22/superset/issues/5) → [PR #3](https://github.com/remikauderer22/superset/pull/3): cryptography GHSA-537c-gmf6-5ccf  
- [Issue #6](https://github.com/remikauderer22/superset/issues/6) → [PR #2](https://github.com/remikauderer22/superset/pull/2): PyJWT CVE-2026-48524

## Notes
- The scheduler interval is set to 60 seconds for demo purposes; a production deployment would use a longer interval (hourly or daily)
- `estimated_hours_saved` is based on manual effort estimates set per issue at filing time, not measured data
- Flask was initially remediated via a direct API call during development before the orchestration layer was finalized; cryptography and PyJWT were triggered through the live service
- Docker requires macOS 14.0+ locally; tested successfully via GitHub Codespaces on Ubuntu