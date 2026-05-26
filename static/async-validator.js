/**
 * <async-validator> Web Component
 *
 * Submits datasets to POST /api/v0/jobs/validate and polls for results.
 * Falls back gracefully to inline sync display when no job_id is returned
 * (i.e. when checkr is running without Redis).
 *
 * Attributes:
 *   validator-source  — base URL for the validators API, e.g. /validators/api/v0
 *   submit-url        — URL for the submit endpoint (optional, same as sync playground)
 */

const POLL_INTERVAL_MS   = 1500;   // initial poll cadence
const POLL_MAX_MS        = 6000;   // cap for exponential backoff
const POLL_BACKOFF       = 1.4;    // backoff multiplier

class AsyncValidator extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        *, *::before, *::after { box-sizing: border-box; }
        :host {
          display: block;
          font-family: system-ui, sans-serif;
          font-size: 0.95rem;
          padding: 1.25rem;
          background: #f9f9fb;
          border: 1px solid #d0d0d8;
          border-radius: 10px;
          max-width: 960px;
          color: #111;
        }
        h2 { margin: 0 0 .75rem; font-size: 1.05rem; color: #333; }
        textarea {
          width: 100%;
          padding: 8px;
          font-family: monospace;
          font-size: 0.85rem;
          border: 1px solid #ccc;
          border-radius: 5px;
          resize: vertical;
        }
        textarea.input-data { height: 140px; margin-bottom: 10px; }

        /* tabs */
        .tabs { display: flex; gap: 0; margin-bottom: 0; }
        .tabs button {
          padding: 5px 15px;
          font-size: 0.88rem;
          cursor: pointer;
          border: 1px solid #ccc;
          background: #eaeaea;
          color: #555;
          margin: 0;
          border-bottom: none;
          border-radius: 6px 6px 0 0;
        }
        .tabs button.active {
          background: #fff;
          color: #111;
          font-weight: 600;
          border-bottom: 1px solid #fff;
          z-index: 1;
          position: relative;
        }
        .tab-body {
          border: 1px solid #ccc;
          border-radius: 0 6px 6px 6px;
          background: #fff;
          padding: 10px;
          margin-bottom: 10px;
        }
        .url-row { display: flex; gap: 8px; }
        .url-row input {
          flex: 1; padding: 8px;
          font-family: monospace; font-size: 0.88rem;
          border: 1px solid #ccc; border-radius: 4px;
        }

        /* validator list */
        #validator-list { margin-bottom: 10px; }
        .folder { font-size: 0.88rem; color: #555; margin: 10px 0 4px; font-weight: 600; }
        .file label { display: flex; align-items: baseline; gap: 6px; cursor: pointer; }
        .file { margin: 3px 0; }
        .file a { font-size: 0.8rem; color: #666; }
        textarea.opt { min-height: 44px; max-height: 400px; overflow: hidden; resize: none; margin: 4px 0 4px 26px; width: calc(100% - 26px); font-size: 0.82rem; }

        /* action buttons */
        .actions { display: flex; gap: 10px; margin: 10px 0; flex-wrap: wrap; align-items: center; }
        button.primary {
          padding: 8px 20px; font-size: 0.95rem; cursor: pointer;
          background: #2563eb; color: #fff; border: none;
          border-radius: 6px; font-weight: 600;
        }
        button.primary:hover { background: #1d4ed8; }
        button.primary:disabled { background: #93c5fd; cursor: default; }
        button.secondary {
          padding: 7px 16px; font-size: 0.9rem; cursor: pointer;
          background: #fff; color: #333; border: 1px solid #bbb;
          border-radius: 6px;
        }
        button.secondary:hover { background: #f0f0f0; }
        button.danger {
          padding: 7px 16px; font-size: 0.9rem; cursor: pointer;
          background: #fff; color: #dc2626; border: 1px solid #fca5a5;
          border-radius: 6px;
        }
        button.danger:hover { background: #fef2f2; border-color: #f87171; }
        button.danger:disabled { opacity: .45; cursor: default; }

        /* status bar */
        #status-bar {
          display: none;
          align-items: center;
          gap: 10px;
          background: #fff;
          border: 1px solid #d0d0d8;
          border-radius: 8px;
          padding: 10px 14px;
          margin-bottom: 10px;
          flex-wrap: wrap;
        }
        .badge {
          display: inline-block;
          padding: 2px 10px;
          border-radius: 12px;
          font-size: 0.8rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: .04em;
        }
        .badge-queued   { background: #e0e7ff; color: #3730a3; }
        .badge-running  { background: #fef3c7; color: #92400e; }
        .badge-completed{ background: #d1fae5; color: #065f46; }
        .badge-failed    { background: #fee2e2; color: #991b1b; }
        .badge-cancelled { background: #f3f4f6; color: #6b7280; }
        .badge-sync      { background: #f3f4f6; color: #374151; }
        .job-id {
          font-family: monospace; font-size: 0.78rem; color: #555;
          background: #f3f4f6; padding: 2px 8px; border-radius: 4px;
        }
        .progress-wrap {
          display: none;
          flex: 1 1 100%;
          align-items: center;
          gap: 8px;
          min-width: 200px;
        }
        .progress-wrap.visible { display: flex; }
        progress {
          flex: 1; height: 6px;
          accent-color: #2563eb;
        }
        .progress-label { font-size: 0.8rem; color: #555; white-space: nowrap; }

        /* output */
        #output {
          background: #fff;
          border: 1px solid #d0d0d8;
          border-radius: 8px;
          padding: 12px;
          white-space: pre-wrap;
          font-family: monospace;
          font-size: 0.83rem;
          min-height: 60px;
          color: #222;
          overflow-x: auto;
        }
        #output:empty::before { content: "Output will appear here…"; color: #aaa; font-style: italic; }

        /* mode chip */
        .mode-chip {
          font-size: 0.78rem;
          padding: 2px 9px;
          border-radius: 10px;
          font-weight: 500;
          margin-left: auto;
        }
        .mode-async { background: #dbeafe; color: #1e40af; }
        .mode-sync  { background: #f3f4f6; color: #4b5563; }

        a.poll-link { font-size: 0.78rem; color: #2563eb; }
      </style>

      <div class="tabs">
        <button id="tab-paste" class="active">Paste JSON</button>
        <button id="tab-url">Load from URL</button>
      </div>
      <div class="tab-body">
        <textarea class="input-data" id="input" placeholder="Paste JSON dataset here…"></textarea>
        <div class="url-row" id="url-row" style="display:none;">
          <input type="text" id="url-input" placeholder="https://example.com/dataset.json">
          <button class="secondary" id="fetch-url">Fetch</button>
        </div>
      </div>

      <h2>Backend Validators</h2>
      <div id="validator-list">⏳ Loading validators…</div>

      <div class="actions">
        <button class="primary" id="run-btn" disabled>Submit</button>
        <button class="danger" id="cancel-btn" style="display:none;">Cancel</button>
        <button class="secondary" id="clear-btn">Clear</button>
        <span id="mode-chip" class="mode-chip" style="display:none;"></span>
      </div>

      <div id="status-bar">
        <span id="status-badge" class="badge"></span>
        <span id="job-id-display" class="job-id" style="display:none;"></span>
        <a id="poll-link" class="poll-link" style="display:none;" target="_blank">↗ raw JSON</a>
        <div class="progress-wrap" id="progress-wrap">
          <progress id="progress-bar" value="0" max="100"></progress>
          <span class="progress-label" id="progress-label"></span>
        </div>
      </div>

      <div id="output"></div>
    `;
  }

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------
  async connectedCallback() {
    this._base = this.getAttribute('validator-source') || '';
    this._mode = null;      // 'async' | 'sync' — discovered on first submit
    this._activeJobId = null; // job currently being polled

    this._bindUI();

    await this._loadValidators();
  }

  _bindUI() {
    const $ = id => this.shadowRoot.getElementById(id);

    // Tabs
    this._inputMode = 'paste';
    $('tab-paste').addEventListener('click', () => this._switchTab('paste'));
    $('tab-url').addEventListener('click', () => this._switchTab('url'));
    $('fetch-url').addEventListener('click', () => this._fetchUrl());

    // Buttons
    $('run-btn').addEventListener('click', () => this._run());
    $('cancel-btn').addEventListener('click', () => this._cancel());
    $('clear-btn').addEventListener('click', () => this._clearOutput());

    // Default dataset
    $('input').value = JSON.stringify([
      { messages: [
          { role: "user",      content: "How can I reset my password?" },
          { role: "assistant", content: "Click 'Forgot Password' on the login page." }
      ]},
      { messages: [
          { role: "system",    content: "You are a helpful assistant." },
          { role: "user",      content: "Hello!" },
          { role: "assistant", content: "Hi there! How can I help you today?" }
      ]}
    ], null, 2);
  }

  _switchTab(mode) {
    this._inputMode = mode;
    const $ = id => this.shadowRoot.getElementById(id);
    $('tab-paste').classList.toggle('active', mode === 'paste');
    $('tab-url').classList.toggle('active', mode === 'url');
    $('input').style.display    = mode === 'paste' ? '' : 'none';
    $('url-row').style.display  = mode === 'url'   ? 'flex' : 'none';
  }

  async _fetchUrl() {
    const url = this.shadowRoot.getElementById('url-input').value.trim();
    if (!url) return;
    this._setOutput('⏳ Fetching…');
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      JSON.parse(text);
      this.shadowRoot.getElementById('input').value = text;
      this._setOutput('✅ Loaded. Click Submit.');
    } catch (e) {
      this._setOutput(`❌ ${e.message}`);
    }
  }

  // -----------------------------------------------------------------------
  // Load validator list
  // -----------------------------------------------------------------------
  async _loadValidators() {
    const container = this.shadowRoot.getElementById('validator-list');
    try {
      const res = await fetch(`${this._base}/list`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const all = await res.json();
      // Async playground only runs backend validators
      this._validators = all.filter(v => v.type === 'dataset/backend');
      this._renderValidators(container, this._validators);
      this.shadowRoot.getElementById('run-btn').disabled = false;
    } catch (e) {
      container.innerHTML = `<p style="color:red;">❌ Failed to load: ${e}</p>`;
    }
  }

  _renderValidators(container, validators) {
    if (!validators.length) {
      container.innerHTML = '<p style="color:#888;">No backend validators available.</p>';
      return;
    }

    const grouped = {};
    validators.forEach(v => {
      const folder = v.source.split('/').slice(-2, -1)[0] || 'other';
      (grouped[folder] = grouped[folder] || []).push(v);
    });

    container.innerHTML = Object.entries(grouped)
      .sort(([a], [b]) => {
        const n = s => parseInt(s.match(/\d+/)?.[0] ?? '0', 10);
        return n(a) - n(b);
      })
      .map(([folder, items]) => `
        <p class="folder"># ${folder.replaceAll('_', ' ')}</p>
        ${items.map(v => {
          const hasOpts = v.options && Object.keys(v.options).length > 0;
          return `
            <div class="file">
              <label>
                <input type="checkbox" value="${v.source}" ${v.enabled ? 'checked' : ''}>
                🗄️ ${v.description || v.title || v.source.split('/').pop()}
                <a href="${this._base}/raw/${v.source}" target="_blank">[Source]</a>
              </label>
              ${hasOpts ? `
                <textarea class="opt" data-source="${v.source}">${JSON.stringify(v.options, null, 2)}</textarea>
              ` : ''}
            </div>`;
        }).join('')}
      `).join('');

    // Auto-resize option textareas
    container.querySelectorAll('textarea.opt').forEach(ta => {
      const fit = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
      fit();
      ta.addEventListener('input', fit);
    });
  }

  // -----------------------------------------------------------------------
  // Main run
  // -----------------------------------------------------------------------
  async _run() {
    const dataset = this._readDataset();
    if (!dataset) return;

    const gates = this._selectedGates();
    if (!gates.length) { this._setOutput('❌ Select at least one validator.'); return; }

    const options = this._mergedOptions(gates);

    this._setRunning(true);
    this._clearOutput();
    this._hideStatus();

    try {
      const res = await fetch(`${this._base.replace('/api/v0', '')}/api/v0/jobs/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset, gates, options }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const body = await res.json();

      if (body.job_id) {
        // ---- Async mode ------------------------------------------------
        this._activeJobId = body.job_id;
        this._setMode('async');
        this._showStatus('queued', body.job_id);
        await this._poll(body.job_id);
      } else {
        // ---- Sync fallback (no Redis) ----------------------------------
        this._setMode('sync');
        this._showStatus('completed');
        this._renderResult(body);
      }
    } catch (e) {
      this._setOutput(`❌ ${e.message || e}`);
    } finally {
      this._activeJobId = null;
      this._setRunning(false);
    }
  }

  // -----------------------------------------------------------------------
  // Polling
  // -----------------------------------------------------------------------
  async _poll(jobId) {
    let interval = POLL_INTERVAL_MS;
    const pollUrl = `${this._base}/jobs/${jobId}`.replace('/api/v0/jobs', '/api/v0/jobs');

    // Build correct poll URL from base
    const apiBase = this._base; // e.g. /validators/api/v0
    const jobUrl  = `${apiBase}/jobs/${jobId}`;

    while (true) {
      await this._sleep(interval);

      let job;
      try {
        const res = await fetch(jobUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        job = await res.json();
      } catch (e) {
        this._setOutput(`❌ Poll error: ${e.message}`);
        break;
      }

      this._showStatus(job.status, jobId, job.progress);

      if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
        if (job.status === 'failed') {
          this._setOutput(`❌ Job failed:\n${job.error || 'unknown error'}`);
        } else if (job.status === 'cancelled') {
          this._setOutput('🚫 Job was cancelled.');
        } else {
          this._renderResult(job.result);
        }
        break;
      }

      interval = Math.min(interval * POLL_BACKOFF, POLL_MAX_MS);
    }
  }

  // -----------------------------------------------------------------------
  // UI helpers
  // -----------------------------------------------------------------------
  _readDataset() {
    if (this._inputMode === 'url') {
      // Use whatever was loaded into the textarea
      const text = this.shadowRoot.getElementById('input').value.trim();
      if (!text) { this._setOutput('❌ Fetch a URL first.'); return null; }
      try { return JSON.parse(text); } catch { this._setOutput('❌ Invalid JSON in loaded data.'); return null; }
    }
    try {
      return JSON.parse(this.shadowRoot.getElementById('input').value);
    } catch {
      this._setOutput('❌ Invalid JSON');
      return null;
    }
  }

  _selectedGates() {
    return [...this.shadowRoot.querySelectorAll('#validator-list input[type=checkbox]:checked')]
      .map(cb => cb.value);
  }

  _mergedOptions(gates) {
    const merged = {};
    gates.forEach(source => {
      const ta = this.shadowRoot.querySelector(`textarea.opt[data-source="${source}"]`);
      if (ta) {
        try { Object.assign(merged, JSON.parse(ta.value)); } catch {}
      }
    });
    return merged;
  }

  _setRunning(on) {
    this.shadowRoot.getElementById('run-btn').disabled = on;
    this.shadowRoot.getElementById('run-btn').textContent = on ? '⏳ Running…' : 'Submit';
    // Show cancel only while an async job is in flight
    const cancelBtn = this.shadowRoot.getElementById('cancel-btn');
    cancelBtn.style.display = (on && this._mode === 'async') ? '' : 'none';
    cancelBtn.disabled = false;
    cancelBtn.textContent = 'Cancel';
  }

  async _cancel() {
    const jobId = this._activeJobId;
    if (!jobId) return;

    const cancelBtn = this.shadowRoot.getElementById('cancel-btn');
    cancelBtn.disabled = true;
    cancelBtn.textContent = 'Cancelling…';

    try {
      const res = await fetch(`${this._base}/jobs/${jobId}/cancel`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        this._setOutput(`❌ Cancel failed: ${err.detail || res.status}`);
        cancelBtn.disabled = false;
        cancelBtn.textContent = 'Cancel';
      }
      // Poll will detect the 'cancelled' status on next tick and stop itself
    } catch (e) {
      this._setOutput(`❌ Cancel error: ${e.message}`);
      cancelBtn.disabled = false;
      cancelBtn.textContent = 'Cancel';
    }
  }

  _setMode(mode) {
    this._mode = mode;
    const chip = this.shadowRoot.getElementById('mode-chip');
    chip.style.display = '';
    chip.className = `mode-chip mode-${mode}`;
    chip.textContent = mode === 'async' ? '⚡ Async (Redis)' : '🔁 Sync mode';
  }

  _showStatus(status, jobId, progress) {
    const bar   = this.shadowRoot.getElementById('status-bar');
    const badge = this.shadowRoot.getElementById('status-badge');
    const jid   = this.shadowRoot.getElementById('job-id-display');
    const link  = this.shadowRoot.getElementById('poll-link');
    const pw    = this.shadowRoot.getElementById('progress-wrap');
    const pb    = this.shadowRoot.getElementById('progress-bar');
    const pl    = this.shadowRoot.getElementById('progress-label');

    bar.style.display = 'flex';
    badge.textContent = status;
    badge.className   = `badge badge-${status}`;

    if (jobId) {
      jid.style.display = '';
      jid.textContent   = jobId;
      link.style.display = '';
      link.href = `${this._base}/jobs/${jobId}`;
    } else {
      jid.style.display  = 'none';
      link.style.display = 'none';
    }

    // progress is now {gate: {current, total}} — aggregate across all gates
    const gates = Object.values(progress || {});
    const aggCurrent = gates.reduce((s, g) => s + (g.current || 0), 0);
    const aggTotal   = gates.reduce((s, g) => s + (g.total   || 0), 0);

    if (aggTotal > 0) {
      pw.classList.add('visible');
      const pct = Math.round((aggCurrent / aggTotal) * 100);
      pb.value = pct;
      pl.textContent = `${aggCurrent} / ${aggTotal}`;
    } else if (status === 'running') {
      pw.classList.add('visible');
      pb.removeAttribute('value'); // indeterminate
      pl.textContent = '';
    } else {
      pw.classList.remove('visible');
    }
  }

  _hideStatus() {
    this.shadowRoot.getElementById('status-bar').style.display = 'none';
  }

  _setOutput(text) {
    const el = this.shadowRoot.getElementById('output');
    el.innerHTML = '';
    el.textContent = text;
  }

  _clearOutput() {
    this.shadowRoot.getElementById('output').innerHTML = '';
  }

  _renderResult(result) {
    if (!result) { this._setOutput('(no result)'); return; }

    const out = this.shadowRoot.getElementById('output');
    const ok  = result.status === 'ok';
    const icon = ok ? '✅' : '❌';
    const errors = result.errors || [];
    const info   = result.info   || [];
    const gates  = result.validated_gates || [];

    let html = `<b>${icon} ${result.status?.toUpperCase()}</b>`;
    if (gates.length) html += `  <span style="color:#888;font-size:.8em;">[${gates.join(', ')}]</span>`;

    if (errors.length) {
      html += `\n\n<b style="color:#b91c1c;">Errors (${errors.length}):</b>\n`;
      html += errors.map(e => {
        const line = typeof e === 'string' ? e : JSON.stringify(e, null, 2);
        return `  ${line}`;
      }).join('\n');
    }

    if (info.length) {
      html += `\n\n<b style="color:#065f46;">Info (${info.length}):</b>`;
      info.forEach(item => {
        if (item.chart) return; // rendered separately below
        html += `\n  ${typeof item === 'string' ? item : JSON.stringify(item)}`;
      });
    }

    out.innerHTML = `<pre style="margin:0;white-space:pre-wrap;">${html}</pre>`;

    // Vega-Lite charts
    if (typeof vegaEmbed !== 'undefined') {
      info.forEach(item => {
        if (!item.chart) return;
        const div = document.createElement('div');
        div.style.marginTop = '12px';
        out.appendChild(div);
        vegaEmbed(div, item.chart, { actions: false }).catch(e => {
          div.textContent = `Chart error: ${e.message}`;
        });
      });
    }
  }

  _sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  }
}

customElements.define('async-validator', AsyncValidator);
