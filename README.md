# ADHD-Cognitive-Games
I have developed some cognitive games based on research papers that measure different behavioural traits related to ADHD. The games are developed to collect data for training a classification model for characterising the ADHD traits in young adults.

## Run locally

No database or configuration needed — data is stored in a local file automatically.

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt        # Windows: venv\Scripts\pip install -r requirements.txt
venv/bin/python server.py                       # Windows: venv\Scripts\python server.py
```

Then open **http://localhost:5000/test_list.html** in Chrome/Edge:

1. Register a participant — or click **"Just demoing? Continue as guest →"**.
2. You land on the **Choose a Test** page: pick any game (e.g. the PVT — 3 rounds, 10 minutes).
3. Play it; when it ends, the results screen appears and your data is saved automatically.
4. Click **⬇ Download Excel (all data)** on the results screen to get the spreadsheet.

Games need a physical keyboard (Space / F / J). Every game has Skip buttons if you want to move fast. Guest runs are saved under the name "Guest" so they're easy to filter out of real data.

## Getting the data

**Storage is automatic — one-time configuration, no redeploys:**
- Every save is written to a `local_data.json` file next to `server.py`, and **additionally** upserted into MongoDB Atlas when `MONGO_URI` is set. MongoDB is the authoritative store; the file doubles as an on-box backup (and is the sole store for local runs). If MongoDB is briefly unreachable, saves keep landing in the file instead of being lost.
- Each game saves its results to the server the moment it ends (one row per participant, updated as they progress), so nothing is lost if a participant stops early.

**Participants** get a **⬇ Download My Results** button (their own row only) on the PVT results screen and the completion page.

**The experimenter** uses the admin dashboard at `https://<your-render-url>/admin.html`: live auto-refreshing table of who has saved data and which tests each person has completed, plus one-click **Download Excel** and raw JSON. Enter the `EXPORT_KEY` in the dashboard's key box (leave blank if no key is configured).

### Experiment sessions (a fresh sheet per experiment)

Every participant record is tagged with the **session** that was live when they registered. Click **+ Start New Session** on the dashboard before an experiment: the table and its Excel download start empty again, while every earlier session stays browsable and re-exportable from the session dropdown. Nothing is ever deleted.

- The dropdown lists sessions newest first with participant counts; the top one is marked **LIVE** (new participants join it).
- Selecting a past session shows its data read-only and scopes the download buttons to it.
- **All sessions pooled** exports every session together — use it for model training across experiments.
- A participant who is mid-way through when a new session starts stays in the session they began in, so their record never splits.

API endpoints (usable from any browser or script):

- `/api/export/xlsx` — Excel sheet: one row per participant, one column per metric *(key-protected)*.
- `/api/export` — full JSON dump including raw per-trial arrays, for pandas / sklearn *(key-protected)*.
- `/api/my/xlsx?userId=<id>` — one participant's own row (used by the Download My Results button).
- `/api/participants` — summary list powering the dashboard *(key-protected)*.
- `/api/sessions` — session list with counts; `POST /api/sessions/new` starts one *(key-protected)*.
- `/api/status` — health check: storage mode and participant count.

The export and participant endpoints accept `?session=<sessionId>` to scope them to one experiment session; omitting it returns every session pooled.

Set an `EXPORT_KEY` environment variable on the server to lock the all-participant endpoints (they then require `?key=<EXPORT_KEY>`). **Strongly recommended for class sessions** — without it, anyone with the link can download everyone's data.

## Running a class session

1. Deploy once: Render blueprint (`render.yaml`) with `MONGO_URI` (Atlas) and `EXPORT_KEY` set; add the `RENDER_URL` GitHub variable so the keep-alive workflow keeps the server warm.
2. Share `https://<your-render-url>/test_list.html` with the class. Everyone registers with their real name and picks tests from the menu; simultaneous play is fine.
3. Watch progress live on `/admin.html`. Each student downloads their own results from their completion screen.
4. When everyone is done, click **Download Excel (everyone)** on the dashboard.

## Keeping the server awake (free tier)

Render's free tier spins the service down after ~15 minutes without traffic, making the next request slow (~30–60 s cold start). The `.github/workflows/keep-alive.yml` workflow pings `/api/status` every 10 minutes to prevent that, and its run history doubles as uptime monitoring — a red run means the server or database was unreachable.

One-time setup after deploying:
1. In the GitHub repo: **Settings → Secrets and variables → Actions → Variables** → add `RENDER_URL` = your deployed URL (e.g. `https://adhd-cognitive-games.onrender.com`).
2. Scheduled workflows only run on the repository's **default branch**, so make sure this file is on it.

Note: GitHub disables cron workflows after 60 days without repository activity — any commit re-enables them. Keeping one service awake 24/7 fits within Render's free 750 instance-hours/month.
