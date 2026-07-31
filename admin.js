document.addEventListener('DOMContentLoaded', () => {
    const keyInput = document.getElementById('keyInput');
    const banner   = document.getElementById('banner');
    const tbody    = document.getElementById('tbody');

    keyInput.value = sessionStorage.getItem('adminKey') || '';

    function key()   { return keyInput.value.trim(); }
    function qs()    { return key() ? '?key=' + encodeURIComponent(key()) : ''; }

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

    async function refresh() {
        sessionStorage.setItem('adminKey', key());
        document.getElementById('xlsxBtn').href = '/api/export/xlsx' + qs();
        document.getElementById('jsonBtn').href = '/api/export' + qs();

        try {
            const st = await fetch('/api/status').then(r => r.json());
            document.getElementById('storageLine').textContent =
                `storage: ${st.storage || st.status || 'unknown'}`;
        } catch { document.getElementById('storageLine').textContent = 'storage: unreachable'; }

        let data;
        try {
            const resp = await fetch('/api/participants' + qs());
            if (resp.status === 401) {
                setBanner('error', 'Wrong or missing export key — enter the EXPORT_KEY configured on the server and press Refresh.');
                tbody.innerHTML = '<tr><td colspan="7" class="empty">Locked</td></tr>';
                return;
            }
            data = await resp.json();
        } catch {
            setBanner('error', 'Could not reach the server.');
            return;
        }

        setBanner(data.warning ? 'warn' : '', data.warning || '');

        const ps = data.participants || [];
        document.getElementById('statCount').textContent = data.count ?? ps.length;
        document.getElementById('statComplete').textContent =
            ps.filter(p => p.tests.goNoGo && p.tests.pvt && p.tests.trailMaking && p.tests.dualNBack).length;
        document.getElementById('statPvt').textContent = ps.filter(p => p.tests.pvt).length;

        if (ps.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty">No participants saved yet — data appears here the moment someone finishes a test.</td></tr>';
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

    document.getElementById('refreshBtn').addEventListener('click', refresh);
    keyInput.addEventListener('keydown', e => { if (e.key === 'Enter') refresh(); });
    refresh();
    setInterval(refresh, 15000);
});
