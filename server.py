from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import os
from io import BytesIO
from datetime import datetime, timezone
from openpyxl import Workbook

# ── App setup ─────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MONGO_URI = os.environ.get('MONGO_URI', '')

# ── DB connection (lazy, cached) ──────────────────────────────────
_collection = None

def get_collection():
    global _collection
    if _collection is not None:
        return _collection
    if not MONGO_URI:
        print('[DB] MONGO_URI not set — data will not be persisted.')
        return None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')          # fail fast if URI is wrong
        _collection = client['adhd_assessment']['participants']
        print('[DB] Connected to MongoDB Atlas.')
        return _collection
    except ServerSelectionTimeoutError as e:
        print(f'[DB] Connection failed: {e}')
        return None

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

        col = get_collection()
        if col is None:
            return jsonify({
                'status':  'error',
                'message': 'Database not configured. Set the MONGO_URI environment variable.'
            }), 503

        result = col.insert_one(document)
        print(f'  → Saved to MongoDB: {result.inserted_id}')
        return jsonify({'status': 'success', 'message': 'Data saved.', 'id': str(result.inserted_id)}), 200

    except Exception as e:
        import traceback
        print(f'\n[CRITICAL ERROR]\n{traceback.format_exc()}')
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Diagnostic endpoints ──────────────────────────────────────────
@app.route('/api/status', methods=['GET'])
def api_status():
    """Quick health check — visit in browser to confirm DB is connected."""
    col = get_collection()
    if col is None:
        return jsonify({'status': 'db_disconnected', 'hint': 'Set MONGO_URI env var'}), 503
    try:
        count = col.count_documents({})
        return jsonify({'status': 'ok', 'participants_saved': count}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


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


@app.route('/api/export', methods=['GET'])
def export_json():
    """
    Download all records as JSON (useful for piping into pandas / sklearn).
    Visit: https://<your-render-url>/api/export
    """
    denied = check_export_key()
    if denied:
        return denied
    col = get_collection()
    if col is None:
        return jsonify({'error': 'No database connection'}), 503
    try:
        docs = list(col.find({}, {'_id': 0}))   # exclude MongoDB internal _id
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


@app.route('/api/export/xlsx', methods=['GET'])
def export_xlsx():
    """
    Download all records as a ready-to-use Excel sheet: one row per
    participant, one column per metric. Always reflects the live database —
    no redeploy needed between exports.
    Visit: https://<your-render-url>/api/export/xlsx
    """
    denied = check_export_key()
    if denied:
        return denied
    col = get_collection()
    if col is None:
        return jsonify({'error': 'No database connection'}), 503
    try:
        # rawResults holds large nested trial arrays — excluded from the
        # sheet; fetch them via /api/export if needed
        docs = list(col.find({}, {'_id': 0, 'rawResults': 0}))
        rows = [flatten_doc(d) for d in docs]

        headers = []
        for r in rows:
            for k in r:
                if k not in headers:
                    headers.append(k)

        wb = Workbook()
        ws = wb.active
        ws.title = 'participants'
        ws.append(headers)
        for r in rows:
            ws.append([r.get(h) for h in headers])

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        fname = f"adhd_data_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            buf,
            as_attachment=True,
            download_name=fname,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Entry point ───────────────────────────────────────────────────
if __name__ == '__main__':
    print('X-PhenoADHD backend — MongoDB edition')
    print(f"MONGO_URI set: {'yes' if MONGO_URI else 'NO — data will not be saved'}")
    print('Connecting to DB...')
    get_collection()
    app.run(host='0.0.0.0', port=5000, debug=True)