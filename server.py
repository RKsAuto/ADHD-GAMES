from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import os
import json
from io import BytesIO
from datetime import datetime, timezone
from openpyxl import Workbook

# ── App setup ─────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MONGO_URI = os.environ.get('MONGO_URI', '')

# When MONGO_URI is not set (local runs / demos), participants are stored in
# this JSON file instead. Do NOT rely on it in cloud deployments — hosts like
# Render wipe the local disk on every restart/redeploy.
LOCAL_DATA_FILE     = os.path.join(BASE_DIR, 'local_data.json')
LOCAL_SESSIONS_FILE = os.path.join(BASE_DIR, 'local_sessions.json')


def _load_json_list(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def load_local_docs():
    return _load_json_list(LOCAL_DATA_FILE)


# ── Experiment sessions ───────────────────────────────────────────
# Each run of the experiment is a "session"; every participant record is
# tagged with its sessionId so the admin can export one session at a time
# (a fresh sheet per experiment) or pool them all for analysis.

def load_sessions():
    """All sessions, newest first."""
    if MONGO_URI:
        col = get_sessions_collection()
        if col is not None:
            return list(col.find({}, {'_id': 0}).sort('createdAt', -1))
    return sorted(_load_json_list(LOCAL_SESSIONS_FILE),
                  key=lambda s: s.get('createdAt', ''), reverse=True)


def create_session(label=''):
    """Start a new session; it immediately becomes the active one."""
    now = datetime.now(timezone.utc)
    # Second-resolution ids stay readable; disambiguate the rare collision
    # (e.g. a double-clicked "Start New Session") so sessions never merge.
    base = 's-' + now.strftime('%Y%m%d-%H%M%S')
    taken = {s.get('sessionId') for s in load_sessions()}
    session_id, n = base, 2
    while session_id in taken:
        session_id, n = f'{base}-{n}', n + 1
    session = {
        'sessionId': session_id,
        'label':     (label or '').strip() or f"Session {now.strftime('%d %b %Y, %H:%M UTC')}",
        'createdAt': now.isoformat(),
    }
    try:
        sessions = _load_json_list(LOCAL_SESSIONS_FILE)
        sessions.append(session)
        with open(LOCAL_SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sessions, f, indent=1)
    except OSError as e:
        print(f'[LOCAL] session write failed: {e}')

    if MONGO_URI:
        col = get_sessions_collection()
        if col is not None:
            col.insert_one(dict(session))
    return session


def active_session():
    """Newest session, creating a first one on demand."""
    sessions = load_sessions()
    return sessions[0] if sessions else create_session()


def store_document(document):
    """
    Persist one participant record (keyed by userId, upsert semantics).
    Always writes the local JSON file; additionally upserts into MongoDB
    when MONGO_URI is configured (MongoDB is the authoritative store, the
    file doubles as an on-box backup). Returns a storage description, or
    None only if every available storage failed.
    """
    # Tag with the session that is active when the FIRST record for this
    # participant lands, so someone who keeps playing across a session
    # boundary stays in the session they started in.
    existing = next((d for d in load_local_docs()
                     if d.get('userId') == document['userId']), None)
    if existing and existing.get('sessionId'):
        document['sessionId']    = existing['sessionId']
        document['sessionLabel'] = existing.get('sessionLabel', '')
    else:
        sess = active_session()
        document['sessionId']    = sess['sessionId']
        document['sessionLabel'] = sess['label']

    local_ok = False
    try:
        docs = [d for d in load_local_docs() if d.get('userId') != document['userId']]
        docs.append(document)
        with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(docs, f, indent=1)
        local_ok = True
    except OSError as e:
        print(f'[LOCAL] write failed: {e}')

    if MONGO_URI:
        col = get_collection()
        if col is not None:
            col.replace_one({'userId': document['userId']}, document, upsert=True)
            return 'MongoDB + local file' if local_ok else 'MongoDB'
        print('[DB] MongoDB unreachable — record kept in local file only')
        return 'local file (MongoDB unreachable)' if local_ok else None
    return 'local file' if local_ok else None


def fetch_documents(include_raw=True, session_id=None):
    """
    Returns (docs, warning). MongoDB is authoritative when configured;
    if it is unreachable, falls back to the local backup file and sets a
    warning string so callers can surface the degraded state.

    session_id: None/'all' returns every session; otherwise only that
    session's participants.
    """
    warning = None
    query = {} if session_id in (None, '', 'all') else {'sessionId': session_id}
    if MONGO_URI:
        col = get_collection()
        if col is not None:
            proj = {'_id': 0} if include_raw else {'_id': 0, 'rawResults': 0}
            return list(col.find(query, proj)), None
        warning = 'MongoDB is configured but unreachable — showing the local backup file, which may be incomplete'
    docs = load_local_docs()
    if query:
        docs = [d for d in docs if d.get('sessionId') == session_id]
    if not include_raw:
        docs = [{k: v for k, v in d.items() if k != 'rawResults'} for d in docs]
    return docs, warning

# ── DB connection (lazy, cached) ──────────────────────────────────
_db = None

def get_db():
    global _db
    if _db is not None:
        return _db
    if not MONGO_URI:
        print(f'[DB] MONGO_URI not set — storing data in {LOCAL_DATA_FILE}')
        return None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')          # fail fast if URI is wrong
        _db = client['adhd_assessment']
        print('[DB] Connected to MongoDB Atlas.')
        return _db
    except ServerSelectionTimeoutError as e:
        print(f'[DB] Connection failed: {e}')
        return None


def get_collection():
    db = get_db()
    return db['participants'] if db is not None else None


def get_sessions_collection():
    db = get_db()
    return db['sessions'] if db is not None else None

# ── Static file serving (Flask serves the whole frontend) ─────────
@app.route('/')
def root():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(BASE_DIR, filename)

# ── Helpers ───────────────────────────────────────────────────────
def num(val, default=None):
    if val is None or val == '':
        return default
    try:
        f = float(val)
        return int(f) if f == int(f) else round(f, 4)
    except (TypeError, ValueError):
        return default

def safe_rate(n, d):
    try:
        nv, dv = float(n), float(d)
        return round(nv / dv, 4) if dv != 0 else None
    except (TypeError, ValueError):
        return None

def median(arr):
    if not arr:
        return None
    try:
        vals = sorted(float(x) for x in arr if x is not None)
        if not vals:
            return None
        n   = len(vals)
        mid = n // 2
        return int(vals[mid]) if n % 2 != 0 else round((vals[mid - 1] + vals[mid]) / 2)
    except (TypeError, ValueError):
        return None

def block_val(rounds, idx, field):
    if isinstance(rounds, list) and idx < len(rounds):
        return num(rounds[idx].get(field))
    return None

def nback_stats(dnb_data, target_block):
    """Return (hits, misses, false_alarms, avg_rt) for one N-back level."""
    hits = misses = fa = rt_total = rt_count = 0
    for t in (dnb_data or []):
        if t.get('block') != target_block:
            continue
        is_target = t.get('isTarget', False)
        responded = t.get('responded', False)
        rt        = t.get('rt')
        if is_target and responded:
            hits += 1
            if rt:
                rt_total += float(rt)
                rt_count += 1
        elif is_target:
            misses += 1
        elif responded:
            fa += 1
    avg_rt = round(rt_total / rt_count, 2) if rt_count else None
    return hits, misses, fa, avg_rt

# ── /save_data ────────────────────────────────────────────────────
@app.route('/save_data', methods=['POST'])
def save_data():
    try:
        data    = request.get_json(force=True, silent=True) or {}
        user    = data.get('user') or {}
        results = user.get('results') or {}
        state   = user.get('stateAssessment') or {}

        print(f"\n[RECEIVED] {user.get('name', 'Unknown')} | {user.get('id', 'Unknown')}")
        for task, val in results.items():
            print(f"  {'✓' if val else '✗'} {task}")

        # Sub-objects
        gng      = results.get('goNoGo')      or {}
        pvt      = results.get('pvt')         or {}
        trail    = results.get('trailMaking') or {}
        dnb_data = results.get('dualNBack') or results.get('dualNback') or []

        gng_rounds  = gng.get('rounds')  or []
        pvt_rounds  = pvt.get('rounds')  or []
        gng_all_rts = gng.get('allRTs')  or []
        pvt_all_rts = pvt.get('allRTs')  or []

        # Derived aggregates
        gng_total_go   = sum(r.get('totalGoTrials',   0) for r in gng_rounds)
        gng_total_nogo = sum(r.get('totalNoGoTrials', 0) for r in gng_rounds)

        trail_a  = num((trail.get('round1') or {}).get('time'))
        trail_b  = num((trail.get('round2') or {}).get('time'))
        ba_ratio = round(trail_b / trail_a, 4) if trail_a and trail_b and trail_a > 0 else None

        d0      = nback_stats(dnb_data, '0-back')
        d1      = nback_stats(dnb_data, '1-back')
        d2      = nback_stats(dnb_data, '2-back')
        d3      = nback_stats(dnb_data, '3-back')
        wm_load = (d2[0] + d3[0]) - d0[0]

        # ── MongoDB document ──────────────────────────────────────
        document = {
            # Identifiers & timestamps
            'userId':           user.get('id', ''),
            'serverTimestamp':  datetime.now(timezone.utc).isoformat(),
            'clientTimestamp':  user.get('testStartTime', ''),

            # Participant
            'participant': {
                'name':       user.get('name', ''),
                'age':        num(user.get('age')),
                'sex':        user.get('sex', ''),
                'adhdStatus': user.get('adhdStatus', ''),
            },

            # State at time of testing
            'stateAssessment': {
                'sleepiness': num(state.get('sleepiness')),
                'feeling':    num(state.get('feeling')),
                'mood':       num(state.get('mood')),
            },

            # Full raw results kept for reanalysis / debugging
            'rawResults': {
                'goNoGo':      gng      or None,
                'pvt':         pvt      or None,
                'trailMaking': trail    or None,
                'dualNBack':   dnb_data or None,
            },

            # Flattened feature metrics
            'metrics': {
                # Go / No-Go
                'gng_totalGoTrials':    gng_total_go   or None,
                'gng_totalNoGoTrials':  gng_total_nogo or None,
                'gng_totalGoHits':      num(gng.get('totalGoHits')),
                'gng_commissionErrors': num(gng.get('totalCommission')),
                'gng_omissionErrors':   num(gng.get('totalOmission')),
                'gng_commissionRate':   safe_rate(gng.get('totalCommission'), gng_total_nogo),
                'gng_omissionRate':     safe_rate(gng.get('totalOmission'),   gng_total_go),
                'gng_avgRT_ms':         num(gng.get('overallAvgRT')),
                'gng_medianRT_ms':      median(gng_all_rts),
                'gng_rtv_ms':           num(gng.get('overallRTV')),
                'gng_temporalDrift':    num(gng.get('temporalDriftIdx')),
                'gng_b1_avgRT':         block_val(gng_rounds, 0, 'avgRT'),
                'gng_b1_rtv':           block_val(gng_rounds, 0, 'rtVariability'),
                'gng_b1_ce':            block_val(gng_rounds, 0, 'commissionErrors'),
                'gng_b1_oe':            block_val(gng_rounds, 0, 'omissionErrors'),
                'gng_b2_avgRT':         block_val(gng_rounds, 1, 'avgRT'),
                'gng_b2_rtv':           block_val(gng_rounds, 1, 'rtVariability'),
                'gng_b2_ce':            block_val(gng_rounds, 1, 'commissionErrors'),
                'gng_b2_oe':            block_val(gng_rounds, 1, 'omissionErrors'),
                'gng_b3_avgRT':         block_val(gng_rounds, 2, 'avgRT'),
                'gng_b3_rtv':           block_val(gng_rounds, 2, 'rtVariability'),
                'gng_b3_ce':            block_val(gng_rounds, 2, 'commissionErrors'),
                'gng_b3_oe':            block_val(gng_rounds, 2, 'omissionErrors'),

                # PVT
                'pvt_avgRT_ms':      num(pvt.get('overallAvgRT')),
                'pvt_medianRT_ms':   median(pvt_all_rts),
                'pvt_rtv_ms':        num(pvt.get('overallRTV')),
                'pvt_lapses':        num(pvt.get('totalLapses')),
                'pvt_falseStarts':   num(pvt.get('totalFalseStarts')),
                'pvt_validAttempts': num(pvt.get('totalValidAttempts')),
                'pvt_temporalDrift': num(pvt.get('temporalDriftIdx')),
                'pvt_b1_avgRT':      block_val(pvt_rounds, 0, 'avgRT'),
                'pvt_b1_rtv':        block_val(pvt_rounds, 0, 'rtVariability'),
                'pvt_b1_lapses':     block_val(pvt_rounds, 0, 'lapses'),
                'pvt_b2_avgRT':      block_val(pvt_rounds, 1, 'avgRT'),
                'pvt_b2_rtv':        block_val(pvt_rounds, 1, 'rtVariability'),
                'pvt_b2_lapses':     block_val(pvt_rounds, 1, 'lapses'),
                'pvt_b3_avgRT':      block_val(pvt_rounds, 2, 'avgRT'),
                'pvt_b3_rtv':        block_val(pvt_rounds, 2, 'rtVariability'),
                'pvt_b3_lapses':     block_val(pvt_rounds, 2, 'lapses'),

                # Trail Making
                'trail_partA_s':      trail_a,
                'trail_partB_s':      trail_b,
                'trail_BA_ratio':     ba_ratio,
                'trail_totalCorrect': num(trail.get('totalCorrect')),
                'trail_totalWrong':   num(trail.get('totalWrong')),

                # Dual N-Back
                'dnb_0back_hits':    d0[0], 'dnb_0back_misses': d0[1],
                'dnb_0back_fa':      d0[2], 'dnb_0back_avgRT':  d0[3],
                'dnb_1back_hits':    d1[0], 'dnb_1back_misses': d1[1],
                'dnb_1back_fa':      d1[2], 'dnb_1back_avgRT':  d1[3],
                'dnb_2back_hits':    d2[0], 'dnb_2back_misses': d2[1],
                'dnb_2back_fa':      d2[2], 'dnb_2back_avgRT':  d2[3],
                'dnb_3back_hits':    d3[0], 'dnb_3back_misses': d3[1],
                'dnb_3back_fa':      d3[2], 'dnb_3back_avgRT':  d3[3],
                'dnb_wm_loadIndex':  wm_load,
            },
        }

        if not document['userId']:
            document['userId'] = f'anon-{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")}'

        storage = store_document(document)
        if storage is None:
            return jsonify({
                'status':  'error',
                'message': 'Could not persist data: database unreachable and local write failed.'
            }), 503

        print(f"  → Saved to {storage}: {document['userId']}")
        return jsonify({'status': 'success', 'message': f'Data saved ({storage}).', 'id': document['userId']}), 200

    except Exception as e:
        import traceback
        print(f'\n[CRITICAL ERROR]\n{traceback.format_exc()}')
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Diagnostic endpoints ──────────────────────────────────────────
@app.route('/api/status', methods=['GET'])
def api_status():
    """Quick health check — visit in browser to confirm storage is working."""
    if MONGO_URI:
        col = get_collection()
        if col is None:
            return jsonify({'status': 'db_disconnected', 'hint': 'MONGO_URI is set but the database is unreachable'}), 503
        try:
            count = col.count_documents({})
            return jsonify({'status': 'ok', 'storage': 'MongoDB (+ local backup file)',
                            'participants_saved': count,
                            'local_backup_records': len(load_local_docs())}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify({'status': 'ok', 'storage': 'local file (MONGO_URI not set)',
                    'participants_saved': len(load_local_docs())}), 200


def check_export_key():
    """
    Optional access control for the export endpoints. If the EXPORT_KEY env
    var is set, requests must include ?key=<EXPORT_KEY>. If it is not set,
    exports stay open (backwards compatible).
    """
    expected = os.environ.get('EXPORT_KEY', '')
    if expected and request.args.get('key') != expected:
        return jsonify({'error': 'Invalid or missing key. Append ?key=<EXPORT_KEY> to the URL.'}), 401
    return None


def session_arg():
    """?session=<id> selects one session; omitted or 'all' means every session."""
    return request.args.get('session', 'all')


@app.route('/api/sessions', methods=['GET'])
def api_sessions_list():
    """
    Sessions newest first, each with its participant count, for the admin
    dashboard's session switcher.
    """
    denied = check_export_key()
    if denied:
        return denied
    try:
        sessions = load_sessions()
        docs, warning = fetch_documents(include_raw=False)
        counts = {}
        for d in docs:
            counts[d.get('sessionId', '')] = counts.get(d.get('sessionId', ''), 0) + 1
        out = [{**s, 'participants': counts.get(s['sessionId'], 0)} for s in sessions]
        # Records saved before sessions existed (or whose session row is gone)
        orphans = sum(c for sid, c in counts.items()
                      if sid not in {s['sessionId'] for s in sessions})
        return jsonify({'sessions': out, 'total': len(docs), 'unassigned': orphans,
                        'activeSessionId': out[0]['sessionId'] if out else None,
                        'warning': warning}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sessions/new', methods=['POST'])
def api_sessions_new():
    """
    Start a new experiment session. Participants who register from now on are
    tagged with it, so the dashboard and its Excel export start empty again.
    Previous sessions stay browsable and re-exportable — nothing is deleted.
    """
    denied = check_export_key()
    if denied:
        return denied
    try:
        payload = request.get_json(force=True, silent=True) or {}
        session = create_session(payload.get('label', ''))
        print(f"[SESSION] started {session['sessionId']} ({session['label']})")
        return jsonify({'status': 'success', 'session': session}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/export', methods=['GET'])
def export_json():
    """
    Download records as JSON (useful for piping into pandas / sklearn).
    Visit: https://<your-render-url>/api/export
    Add ?session=<sessionId> for a single experiment session.
    """
    denied = check_export_key()
    if denied:
        return denied
    try:
        docs, warning = fetch_documents(include_raw=True, session_id=session_arg())
        if warning:
            print(f'[EXPORT] {warning}')
        return jsonify(docs), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def flatten_doc(doc, prefix=''):
    """Flatten nested dicts into dot-notation columns; lists (raw trial
    arrays) are skipped — they stay available via /api/export JSON."""
    flat = {}
    for k, v in doc.items():
        key = f'{prefix}{k}'
        if isinstance(v, dict):
            flat.update(flatten_doc(v, key + '.'))
        elif isinstance(v, list):
            continue
        else:
            flat[key] = v
    return flat


XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


# Shown when an export has no participants yet, so the file still opens as a
# valid (empty) sheet instead of a blank one with no header row at all.
EMPTY_HEADERS = ['userId', 'sessionId', 'sessionLabel', 'serverTimestamp',
                 'participant.name', 'participant.age', 'participant.sex',
                 'participant.adhdStatus']


def build_xlsx(docs):
    """One row per participant, one dot-notation column per metric."""
    rows = [flatten_doc(d) for d in docs]
    headers = []
    for r in rows:
        for k in r:
            if k not in headers:
                headers.append(k)
    if not headers:
        headers = list(EMPTY_HEADERS)
    wb = Workbook()
    ws = wb.active
    ws.title = 'participants'
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@app.route('/api/export/xlsx', methods=['GET'])
def export_xlsx():
    """
    Download records as a ready-to-use Excel sheet: one row per participant,
    one column per metric. Always reflects the live database — no redeploy
    needed between exports.
    Visit: https://<your-render-url>/api/export/xlsx
    Add ?session=<sessionId> for one experiment session's fresh sheet.
    """
    denied = check_export_key()
    if denied:
        return denied
    try:
        # rawResults holds large nested trial arrays — excluded from the
        # sheet; fetch them via /api/export if needed
        session_id = session_arg()
        docs, warning = fetch_documents(include_raw=False, session_id=session_id)
        if warning:
            print(f'[EXPORT] {warning}')
        tag = '' if session_id in ('all', '', None) else f'_{session_id}'
        fname = f"adhd_data{tag}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(build_xlsx(docs), as_attachment=True,
                         download_name=fname, mimetype=XLSX_MIME)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/my/xlsx', methods=['GET'])
def export_my_xlsx():
    """
    Per-participant download: returns an Excel sheet containing only the
    given participant's row. Requires no export key — the participant's own
    userId (known only to their browser session) acts as the access token.
    """
    user_id = request.args.get('userId', '')
    if not user_id:
        return jsonify({'error': 'userId query parameter required'}), 400
    try:
        docs, _ = fetch_documents(include_raw=False)
        mine = [d for d in docs if d.get('userId') == user_id]
        if not mine:
            return jsonify({'error': 'No saved data found for this participant yet'}), 404
        return send_file(build_xlsx(mine), as_attachment=True,
                         download_name='my_results.xlsx', mimetype=XLSX_MIME)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/participants', methods=['GET'])
def api_participants():
    """
    Summary list for the admin dashboard: who has saved data, when, and
    which tests they have completed. Key-protected like the exports.
    Add ?session=<sessionId> to scope it to one experiment session.
    """
    denied = check_export_key()
    if denied:
        return denied
    try:
        docs, warning = fetch_documents(include_raw=True, session_id=session_arg())
        out = []
        for d in docs:
            raw = d.get('rawResults') or {}
            m   = d.get('metrics') or {}
            out.append({
                'userId':  d.get('userId', ''),
                'name':    (d.get('participant') or {}).get('name', ''),
                'savedAt': d.get('serverTimestamp', ''),
                'tests': {
                    'goNoGo':      bool(raw.get('goNoGo')),
                    'pvt':         bool(raw.get('pvt')),
                    'trailMaking': bool(raw.get('trailMaking')),
                    'dualNBack':   bool(raw.get('dualNBack')),
                },
                'pvtAvgRT':     m.get('pvt_avgRT_ms'),
                'sessionId':    d.get('sessionId', ''),
                'sessionLabel': d.get('sessionLabel', ''),
            })
        out.sort(key=lambda r: r.get('savedAt') or '', reverse=True)
        return jsonify({'count': len(out), 'warning': warning, 'participants': out}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Entry point ───────────────────────────────────────────────────
if __name__ == '__main__':
    print('X-PhenoADHD backend')
    print(f"MONGO_URI set: {'yes — using MongoDB' if MONGO_URI else 'no — using local file storage (local_data.json)'}")
    if MONGO_URI:
        print('Connecting to DB...')
        get_collection()
    app.run(host='0.0.0.0', port=5000, debug=True)