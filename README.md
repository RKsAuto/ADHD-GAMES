---
title: ADHD Cognitive Games
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

<!-- The block above is Hugging Face Spaces configuration; it makes a Space
     build the Dockerfile and serve the app. GitHub renders it as a table and
     it is otherwise harmless — leave it in place if you deploy to Spaces. -->

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

## PVT protocol notes

Follows the standard Dinges & Powell PVT: stimulus at random **2–10 s** intervals, response window of **10 s**, responses under 100 ms counted as false starts. Outcome measures per the literature:

- **Mean RRT** (`pvt_meanRRT`) — mean reciprocal reaction time in responses/second, computed as the mean of 1/RT (*not* the reciprocal of the mean, which is what de-weights the long right tail). Higher = better performance; e.g. 250 ms → 4.0.
- **Lapses** (`pvt_lapses_gt500ms`) — responses slower than 500 ms.
- **No responses** (`pvt_noResponses`) — no press within the 10 s window, reported separately from lapses.

Per-round values are exported too (`pvt_b1_rrt`, `pvt_b1_lapses`, `pvt_b1_noResp`, …).

## Free hosted alternative: Vercel

Vercel runs the app as a serverless function. That structurally avoids the failure that suspends the other free tiers: there is no long-running instance accumulating compute hours, so there is no hour or CPU quota to exceed — and no idle sleep, so no cold-start penalty for participants.

```bash
npm i -g vercel
vercel        # first deploy, answer the prompts
vercel --prod # promote it
```

Or import the GitHub repo at [vercel.com/new](https://vercel.com/new) — `vercel.json` and `api/index.py` are already in the repo, so no build configuration is needed.

Then add **Environment Variables** in the project settings (Production scope): `MONGO_URI` and `EXPORT_KEY`, and redeploy so they take effect.

> **`MONGO_URI` is mandatory on Vercel.** The app directory is read-only and only `/tmp` is writable, and `/tmp` does not survive between invocations — so MongoDB is the only store. The entry point points `LOCAL_DATA_DIR` at `/tmp` and turns the self-ping off automatically. Free Hobby projects are for non-commercial use, which covers academic research.

Share the deployment URL the same way as any other host:

```
https://<project>.vercel.app/test_list.html    ← participants
https://<project>.vercel.app/admin.html        ← experimenter
```

## Free hosted alternative: Hugging Face Spaces

A `Dockerfile` is included, so any Docker-based host can run this. Hugging Face Spaces is the practical free one — no credit card, no monthly hour limit.

> **Note:** free-tier limits on Render are enforced per *account*, not per service or repository, so re-deploying the same code from a differently-named repo into the same account does not reset them.

1. Create a **Space** → SDK **Docker** → blank template.
2. Push this code to the Space's git remote. Its `README.md` must start with Space frontmatter:
   ```yaml
   ---
   title: ADHD Cognitive Games
   sdk: docker
   app_port: 7860
   ---
   ```
3. In **Settings → Variables and secrets**, add `MONGO_URI` and `EXPORT_KEY` as **secrets** (not variables) so they stay out of the public repo.

**`MONGO_URI` is mandatory here.** As on Render, the container's filesystem is ephemeral — a restart wipes `local_data.json`, so MongoDB is the only durable store. Free Spaces also sleep after ~48 h idle and wake on the next request (~30 s), and the repo is public unless you make the Space private.

### Sharing the link with a whole class

Share the **direct app URL**, not the `huggingface.co/spaces/...` page:

```
https://<your-username>-<space-name>.hf.space/test_list.html      ← participants
https://<your-username>-<space-name>.hf.space/admin.html          ← you
```

The `huggingface.co/spaces/...` page wraps the app in an iframe, which adds Hugging Face chrome and — more importantly — **swallows keyboard input until the participant clicks inside the frame**. These tests are driven by Space / F / J, so send the direct `.hf.space` link.

Everyone uses the same link at the same time; each browser keeps its own participant session, so there is no cross-contamination. A simulated class of 40 participants arriving simultaneously — loading pages, saving results and downloading their own sheets — completed in well under a second of server time, so the server is not the constraint.

Before a session: the Space must be **public** (otherwise participants need a Hugging Face account), and open the link yourself a few minutes early to wake it if it has been idle.

## Self-hosting on a Raspberry Pi (recommended long term)

The app is light — the games run in the browser and the server only serves static files and writes small records — so any Pi handles it comfortably. Self-hosting removes the free-tier hour limit and suspension risk entirely.

```bash
git clone <repo> && cd ADHD-GAMES
./deploy/pi-setup.sh          # asks for MONGO_URI, EXPORT_KEY, optional tunnel token
```

That installs a virtualenv and enables two systemd services that start on boot and restart after crashes or power cuts:

| Service | Role |
|---|---|
| `adhd-games` | gunicorn bound to `127.0.0.1` — never exposed directly |
| `adhd-tunnel` | `cloudflared`, publishing it to the internet over HTTPS |

The tunnel needs **no port forwarding, no static IP and no router changes**, and works behind CGNAT. Only this app is published — not the rest of your network, and not SSH.

```bash
./deploy/tunnel-url.sh                       # current public links
sudo systemctl status adhd-games adhd-tunnel # health
sudo journalctl -u adhd-games -f             # logs
git pull && sudo systemctl restart adhd-games # update
```

**Getting a stable URL.** Without a tunnel token you get a free *quick tunnel* whose `*.trycloudflare.com` address changes on every restart — fine for a one-off session, awkward for a permanent link. For a fixed address, either create a named tunnel in the Cloudflare Zero Trust dashboard (needs a domain on Cloudflare) and put its token in `CF_TUNNEL_TOKEN`, or use [Tailscale Funnel](https://tailscale.com/kb/1223/funnel), which gives a permanent `https://<machine>.<tailnet>.ts.net` URL free without owning a domain.

**Before relying on it for a session:** the Pi's power and internet become your uptime. Check that the links work from a phone on mobile data (not just your home WiFi), and reboot the Pi once to confirm both services come back on their own.

## Running a session without hosting (laptop + public tunnel)

If the hosted service is unavailable — e.g. Render's free plan suspends it with *"Free Tier Usage Exceeded"* until the next billing period — you can run the whole session from one machine and still give participants a public link:

```bash
export MONGO_URI="mongodb+srv://..."   # optional; also saves to Atlas
export EXPORT_KEY="yourkey"            # protects the admin dashboard
./run_session.sh
```

It installs dependencies, starts the server, opens a free Cloudflare tunnel (no account needed) and prints the two links to share — `.../test_list.html` for participants and `.../admin.html` for you. Data is written to `local_data.json` on the laptop, and to MongoDB as well when `MONGO_URI` is set. Keep the terminal open for the whole session; Ctrl-C ends it. The URL changes each run, so share it at the start of the session.

## Running a class session

1. Deploy once: Render blueprint (`render.yaml`) with `MONGO_URI` (Atlas) and `EXPORT_KEY` set; add the `RENDER_URL` GitHub variable so the keep-alive workflow keeps the server warm.
2. Share `https://<your-render-url>/test_list.html` with the class. Everyone registers with their real name and picks tests from the menu; simultaneous play is fine.
3. Watch progress live on `/admin.html`. Each student downloads their own results from their completion screen.
4. When everyone is done, click **Download Excel (everyone)** on the dashboard.

## Keeping the server awake (free tier)

Render's free tier spins the service down after ~15 minutes without traffic, making the next request slow (~30–60 s cold start). Two independent mechanisms keep it up — they do different jobs, so keep both:

> ⚠️ **Budget first.** A free plan allows **750 instance-hours per month**, shared across every free service in the account. Keeping one service awake around the clock costs ~744 of them, leaving no margin — exceeding the allowance gets the service **suspended** (it then returns Render's own fast `503 Service Suspended` page). Both mechanisms below therefore run only during a daily window (default `03:00–16:59 UTC` = `08:30–22:29 IST`, about 400 h/month). Widen them only on a paid plan.

**1. Built-in self-ping** (`server.py`). A background thread requests the app's own **public** URL (`/healthz`) every 10 minutes, which passes through Render's router and counts as real traffic. It uses `RENDER_EXTERNAL_URL`, which Render injects automatically — no configuration needed. Tune with `SELF_PING_MINUTES` (`0` disables it), restrict the hours with `SELF_PING_WINDOW_UTC` (`START-END`, e.g. `03-16`; empty means 24/7), or override the target with `SELF_PING_URL`. When neither URL is present (local runs) it disables itself and logs that it did.

*It prevents sleep but cannot cure it: once the service is asleep the thread is asleep too, so something external must wake it.* That is the second mechanism's job.

**2. GitHub Actions cron** (`.github/workflows/keep-alive.yml`). Pings from outside every 10 minutes within the same window, so it can wake a sleeping service, and its run history doubles as uptime monitoring. It probes `/healthz` first and `/api/status` second, so a failure tells you *which* layer broke: a `/healthz` failure means the service itself is not serving (crashed, failed deploy, or suspended), while `/healthz` OK plus `/api/status` 503 means the database is unreachable. Response time is a clue too — this app's own database-down 503 takes ~5 s, so a *fast* 5xx is Render answering rather than the app.

**On session day**, if you want zero cold starts outside the window, either temporarily clear `SELF_PING_WINDOW_UTC` / widen the cron, or move the service to a paid instance for that month. Watch the hours on Render's usage page either way.

One-time setup after deploying:
1. In the GitHub repo: **Settings → Secrets and variables → Actions → Variables** → add `RENDER_URL` = your deployed URL (e.g. `https://adhd-cognitive-games.onrender.com`).
2. Scheduled workflows only run on the repository's **default branch**, so make sure this file is on it.

Note: GitHub disables cron workflows after 60 days without repository activity — any commit re-enables them. Keeping one service awake 24/7 fits within Render's free 750 instance-hours/month.
