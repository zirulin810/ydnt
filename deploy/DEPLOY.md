# YDNT Deployment Guide

YDNT runs as two separate services in GCP project `halogen-parser-500207-k8`, region `us-east1`. Deploy them separately; after changing `app/`, redeploy the agent, and after changing `submission_frontend/`, redeploy the dashboard.

| Service | What | Where |
|---|---|---|
| Agent (`app/`) | ADK workflow | Vertex AI Agent Runtime, reasoning engine `6427164433839030272` (display name `ydnt`) |
| Dashboard (`submission_frontend/`) | FastAPI web UI that calls the agent | Cloud Run service `ydnt-dashboard` |

---

## 1. Prerequisites

```bash
gcloud config set project halogen-parser-500207-k8
gcloud auth application-default login
uv run pytest tests/unit tests/integration
```

---

## 2. Deploy the Agent (Agent Runtime)

`agents-cli deploy` updates the existing reasoning engine with the same display name, so the ID stays the same. Environment variables and instance settings are replaced on every deploy, so always pass the full set:

```bash
agents-cli deploy --min-instances 0 --update-env-vars "YOUTUBE_API_KEY=...,GEMINI_API_KEY=..."
```

`--min-instances 0` lets the agent scale to zero when idle. Without it, `agents-cli` defaults to 1 and keeps an instance (1 vCPU, 4 GiB) running and billed around the clock. The trade-off is a slower first run after an idle period.

| Variable | Used for |
|---|---|
| `YOUTUBE_API_KEY` | YouTube search, channel stats, and video length |
| `GEMINI_API_KEY` | AI Studio key for the one-minute video sample in the coverage check (free tier) |

All other Gemini calls use Vertex AI through the service account and the `global` endpoint (`GEMINI_LOCATION`, default `global`), which avoids most `429 RESOURCE_EXHAUSTED` errors from a single busy region.

---

## 3. Deploy the Dashboard (Cloud Run)

```bash
gcloud run deploy ydnt-dashboard --source submission_frontend --region us-east1
```

The dashboard only talks to the Agent Runtime, so it does not need the agent's code or any API keys. It deletes each Agent Runtime session once the run completes or fails (the report stays in the dashboard's memory), and deletes sessions abandoned at a human-in-the-loop pause after 24 hours. Its environment variables are `AGENT_RUNTIME_ID`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`, and they are kept across deploys.

---

## 4. Check What Is Deployed

Agent last update time (UTC):
```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" https://us-east1-aiplatform.googleapis.com/v1/projects/62925246430/locations/us-east1/reasoningEngines/6427164433839030272
```

Dashboard revision serving traffic:
```bash
gcloud run services describe ydnt-dashboard --region us-east1 --format="value(status.latestReadyRevisionName)"
```
