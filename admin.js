document.addEventListener('DOMContentLoaded', () => {
    const keyInput = document.getElementById('keyInput');
    const banner   = document.getElementById('banner');
    const tbody    = document.getElementById('tbody');
    const sessionSelect = document.getElementById('sessionSelect');

    keyInput.value = sessionStorage.getItem('adminKey') || '';
    let selectedSession = sessionStorage.getItem('adminSession') || '';  // '' = active session
    let activeSessionId = null;

    function key() { return keyInput.value.trim(); }

    function qs(extra) {
        const p = new URLSearchParams();
        if (key()) p.set('key', key());
        Object.entries(extra || {}).forEach(([k, v]) => { if (v) p.set(k, v); });
        const s = p.toString();
        return s ? '?' + s : '';
    }

    // '' means "whatever session is active"; resolve it for API calls
    function currentSession() { return selectedSession || activeSessionId || 'all'; }

    function setBanner(kind, text) {
        banner.className = 'banner' + (kind ? ' ' + kind : '');
        banner.textContent = text || '';
    }

    function mark(done) { return done ? '<span class="done">✓</span>' : '<span class="pend">·</span>'; }

    function fmtTime(iso) {
        if (!iso) return '–';
        const d = new Date(iso);
        return isNaN(d) ? iso : d.toLocaleString();
    }

    async function loadSessions() {
        const resp = await fetch('/api/sessions' + qs());
        if (resp.status === 401) return null;
        const data = await resp.json();
        activeSessionId = data.activeSessionId;

        const opts = (data.sessions || []).map((s, i) => {
            const live = i === 0 ? ' — LIVE' : '';
            return `<option value="${s.sessionId}">${s.label} (${s.participants})${live}</option>`;
        });
        opts.push(`<option value="all">All sessions pooled (${data.total || 0})</option>`);
        sessionSelect.innerHTML = opts.join('');
        sessionSelect.value = currentSession();
        if (!sessionSelect.value && activeSessionId) sessionSelect.value = activeSessionId;

        const isLive = sessionSelect.value === activeSessionId;
        document.getElementById('sessionHint').textContent = isLive
            ? 'This is the live session — new participants are being added here. Downloads below cover this session only.'
            : sessionSelect.value === 'all'
                ? 'Viewing every session pooled together — useful for model training across experiments.'
                : 'Viewing a past session (read-only history). New participants still join the live session.';
        return data;
    }

    async function refresh() {
        sessionStorage.setItem('adminKey', key());
        try {
            const st = await fetch('/api/status').then(r => r.json());
            document.getElementById('storageLine').textContent =
                `storage: ${st.storage || st.status || 'unknown'}`;
        } catch { document.getElementById('storageLine').textContent = 'storage: unreachable'; }

        let sessionData;
        try {
            sessionData = await loadSessions();
            if (sessionData === null) {
                setBanner('error', 'Wrong or missing export key — enter the EXPORT_KEY configured on the server and press Refresh.');
                tbody.innerHTML = '<tr><td colspan="7" class="empty">Locked</td></tr>';
                return;
            }
        } catch {
            setBanner('error', 'Could not reach the server.');
            return;
        }

        const sess = currentSession();
        document.getElementById('xlsxBtn').href = '/api/export/xlsx' + qs({ session: sess });
        document.getElementById('jsonBtn').href = '/api/export' + qs({ session: sess });

        let data;
        try {
            data = await fetch('/api/participants' + qs({ session: sess })).then(r => r.json());
        } catch {
            setBanner('error', 'Could not reach the server.');
            return;
        }

        let warn = data.warning || sessionData.warning || '';
        if (sessionData.unassigned) {
            warn += (warn ? ' · ' : '') +
                `${sessionData.unassigned} record(s) predate sessions — use "All sessions pooled" to include them.`;
        }
        setBanner(warn ? 'warn' : '', warn);

        const ps = data.participants || [];
        document.getElementById('statCount').textContent = data.count ?? ps.length;
        document.getElementById('statComplete').textContent =
            ps.filter(p => p.tests.goNoGo && p.tests.pvt && p.tests.trailMaking && p.tests.dualNBack).length;
        document.getElementById('statPvt').textContent = ps.filter(p => p.tests.pvt).length;

        if (ps.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty">No participants in this session yet — they appear here the moment someone finishes a test.</td></tr>';
            return;
        }
        tbody.innerHTML = ps.map(p => `
            <tr>
                <td>${p.name || '(unnamed)'}<div class="muted">${p.userId}</div></td>
                <td class="muted">${fmtTime(p.savedAt)}</td>
                <td>${mark(p.tests.goNoGo)}</td>
                <td>${mark(p.tests.pvt)}</td>
                <td>${mark(p.tests.trailMaking)}</td>
                <td>${mark(p.tests.dualNBack)}</td>
                <td>${p.pvtAvgRT != null ? p.pvtAvgRT + ' ms' : '–'}</td>
            </tr>`).join('');
    }

    sessionSelect.addEventListener('change', () => {
        selectedSession = sessionSelect.value;
        sessionStorage.setItem('adminSession', selectedSession);
        refresh();
    });

    document.getElementById('newSessionBtn').addEventListener('click', async () => {
        const label = prompt('Name this experiment session (optional):', '');
        if (label === null) return;   // cancelled
        try {
            const resp = await fetch('/api/sessions/new' + qs(), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label })
            });
            if (resp.status === 401) {
                setBanner('error', 'Wrong or missing export key — cannot start a session.');
                return;
            }
            const data = await resp.json();
            selectedSession = '';   // follow the new live session
            sessionStorage.removeItem('adminSession');
            setBanner('warn', `New session started: ${data.session.label}. The table and downloads are fresh — earlier sessions stay available in the dropdown.`);
            refresh();
        } catch {
            setBanner('error', 'Could not start a new session.');
        }
    });

    document.getElementById('refreshBtn').addEventListener('click', refresh);
    keyInput.addEventListener('keydown', e => { if (e.key === 'Enter') refresh(); });
    refresh();
    setInterval(refresh, 15000);
});
