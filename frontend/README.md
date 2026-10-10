# MonsoonOps

**Live demo:** https://main.d2yk6tlyjiizsh.amplifyapp.com

Sachet tells the city. MonsoonOps tells each person in your building what to do, and proves it was done.

MonsoonOps is a rain-readiness ledger for apartment complexes with basement parking. It turns a heavy-rain forecast into role-specific tasks, requires proof for the critical ones, escalates anything that is ignored, and shows a readiness score.

Built for Environmental Hacks 2026 (Heat and Water track, Bharat Builds Tour stop 2).

## The problem

When heavy rain is hours away, nobody in an apartment complex owns the next 30 minutes. Cars stay in the basement, the pump is untested, drains are blocked, and residents do not know what to do. Rainwater harvesting pits are often blocked too, so rain runs off instead of recharging groundwater.

## What it does

- **Trigger:** a rules engine compares the forecast with the site profile and sets the site to Normal, Watch or High, with a visible reason. Thresholds follow IMD's heavy (64.5 mm) and very heavy (115.6 mm) classes. A low-lying site or one with flood history steps up one level.
- **Assign:** tasks fan out by role from templates (admin, security, maintenance, resident). Each resident gets one task for their own vehicle.
- **Prove:** critical tasks need evidence. A photo goes straight to a private S3 bucket and the server checks the file exists. A test log is stored the same way. A check-in task needs a different person to confirm it.
- **Escalate:** at 3 hours left, unacknowledged tasks are escalated. At 1 hour left, open critical tasks turn the site red. At the rain window, the readiness score is locked.
- **Vehicles:** a priority screen orders cars by lowest basement level first, then low-lying bays, with a move-to slot for each.
- **Score:** readiness is the share of critical tasks that are verified done.

## What is simulated

This demo runs in simulated mode. The rain scenario (90 mm forecast) is started with a labeled button and the building, residents and vehicles are synthetic. A time-warp control moves the clock forward so escalation is visible in seconds. Nothing shown here is a real-world result. Live forecast data, SACHET alerts, email notifications and login are not built.

## Architecture

```
Browser (React, hosted on AWS Amplify)
        |
        v
API Gateway (HTTP API)  -->  Lambda (Python 3.12)  -->  DynamoDB (single table)
        |
        +-- presigned upload links  -->  S3 (private evidence bucket)
```

AWS services used: Amplify Hosting, API Gateway, Lambda, DynamoDB, S3, IAM.

Design choices:

- **One Lambda with a small router** keeps deployment to a single command.
- **One DynamoDB table** with `pk` and `sk` keys. Items that belong together share a partition key, so one query returns all tasks of an incident.
- **A rules table, not machine learning,** so every trigger can be explained to a facility manager and cannot fail mid-demo.
- **Presigned S3 uploads** mean photos never pass through Lambda and no AWS keys exist in the frontend.
- **The clock is an offset** stored on the incident. Time-warp only changes the offset, so real mode and demo mode run the same code.
- **Conditional writes** stop a task being completed twice, even if two people tap at once.

## API

| Method and path | Purpose |
| --- | --- |
| GET /site/{id} | Site profile |
| POST /incident/simulate | Start the labeled heavy-rain scenario |
| GET /incident/{id}/tasks?role= | Task list for a role |
| GET /incident/{id}/status | Risk level, escalation stage, time left |
| GET /incident/{id}/score | Readiness score and counts |
| GET /incident/{id}/vehicles | Vehicles in priority order |
| POST /incident/{id}/task/{taskId}/ack | Acknowledge a task |
| POST /incident/{id}/task/{taskId}/upload-url | Presigned S3 upload link |
| POST /incident/{id}/task/{taskId}/complete | Complete a task with its proof |
| POST /demo/time-warp | Move the demo clock forward |

`latest` can be used in place of an incident id.

## Run it

Backend and frontend are already deployed. To work on it locally:

```
cd frontend
npm install
npm run dev
```

To reload the demo building: `python seed/seed.py`

## Privacy

All names are synthetic. Vehicles are stored as a flat number and the last four digits of a plate, never a full registration number.

## Safety

MonsoonOps is a preparedness aid. It does not predict floods and never claims that a basement will flood at a given time.

## Repository layout

- `backend/api`: Lambda code (`app.py`, `rules.py`)
- `frontend`: React app
- `infra`: IAM policies and helper scripts
- `seed`: demo building data