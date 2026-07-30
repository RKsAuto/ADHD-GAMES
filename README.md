# ADHD-Cognitive-Games
I have developed some cognitive games based on research papers that measure different behavioural traits related to ADHD. The games are developed to collect data for training a classification model for characterising the ADHD traits in young adults.

## Getting the data

Deploy once (Render, via `render.yaml`, with `MONGO_URI` set). After that the export endpoints always serve the **live** database contents — no redeploy is ever needed to get fresh data:

- `https://<your-render-url>/api/export/xlsx` — downloads a ready-to-use Excel sheet: one row per participant, one column per metric.
- `https://<your-render-url>/api/export` — full JSON dump, including the raw per-trial arrays (`rawResults`), for pandas / sklearn.
- `https://<your-render-url>/api/status` — health check: confirms DB connection and shows how many participants have been saved.

To keep participant data private, set an `EXPORT_KEY` environment variable on the server; the export endpoints then require `?key=<EXPORT_KEY>` on the URL (e.g. `/api/export/xlsx?key=mysecret`). If `EXPORT_KEY` is unset, exports are open.

## Keeping the server awake (free tier)

Render's free tier spins the service down after ~15 minutes without traffic, making the next request slow (~30–60 s cold start). The `.github/workflows/keep-alive.yml` workflow pings `/api/status` every 10 minutes to prevent that, and its run history doubles as uptime monitoring — a red run means the server or database was unreachable.

One-time setup after deploying:
1. In the GitHub repo: **Settings → Secrets and variables → Actions → Variables** → add `RENDER_URL` = your deployed URL (e.g. `https://adhd-cognitive-games.onrender.com`).
2. Scheduled workflows only run on the repository's **default branch**, so make sure this file is on it.

Note: GitHub disables cron workflows after 60 days without repository activity — any commit re-enables them. Keeping one service awake 24/7 fits within Render's free 750 instance-hours/month.
