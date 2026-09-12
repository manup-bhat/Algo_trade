"""Append Agent JS to dashboard.html before </script>."""
import pathlib

DASHBOARD = pathlib.Path("app/static/dashboard.html")

AGENT_JS = r"""
// ── Phase 4: Agentic Strategy Loop ───────────────────────────────────────────

const _PROPOSAL_STATUS_META = {
  pending_backtest: { label: 'Pending BT',   color: 'var(--amber)',  bg: 'rgba(245,158,11,0.12)'  },
  backtest_done:    { label: 'BT Done',      color: 'var(--teal)',   bg: 'rgba(20,184,166,0.12)'  },
  pending_paper:    { label: 'Pending Paper', color: '#3b82f6',      bg: 'rgba(59,130,246,0.12)'  },
  paper_done:       { label: 'Paper Done',    color: '#a78bfa',      bg: 'rgba(167,139,250,0.12)' },
  approved:         { label: 'Approved',      color: 'var(--green)', bg: 'rgba(34,197,94,0.12)'   },
  rejected:         { label: 'Rejected',      color: 'var(--red)',   bg: 'rgba(239,68,68,0.12)'   },
};

function _agentStatusBadge(status) {
  const m = _PROPOSAL_STATUS_META[status] || { label: status, color: 'var(--text-muted)', bg: 'transparent' };
  return `<span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;background:${m.bg};color:${m.color};white-space:nowrap;">${m.label}</span>`;
}

function _agentActionButtons(p) {
  const btns = [];
  if (p.status === 'pending_backtest') {
    btns.push(`<button class="btn btn-ghost btn-sm" onclick="_agentRunBacktest('${p.proposal_id}')" style="font-size:10px;">Run BT</button>`);
    btns.push(`<button class="btn btn-ghost btn-sm" onclick="_agentReject('${p.proposal_id}')" style="font-size:10px;color:var(--red);">Reject</button>`);
  }
  if (p.status === 'backtest_done') {
    btns.push(`<button class="btn btn-primary btn-sm" onclick="_agentApprove('${p.proposal_id}')" style="font-size:10px;">Approve</button>`);
    btns.push(`<button class="btn btn-ghost btn-sm" onclick="_agentReject('${p.proposal_id}')" style="font-size:10px;color:var(--red);">Reject</button>`);
  }
  if (p.status === 'pending_paper') {
    btns.push(`<button class="btn btn-primary btn-sm" onclick="_agentPromotePaper('${p.proposal_id}')" style="font-size:10px;">Start Paper</button>`);
    btns.push(`<button class="btn btn-ghost btn-sm" onclick="_agentReject('${p.proposal_id}')" style="font-size:10px;color:var(--red);">Reject</button>`);
  }
  if (p.status === 'paper_done') {
    btns.push(`<button class="btn btn-primary btn-sm" onclick="_agentPromoteLive('${p.proposal_id}')" style="font-size:10px;">Go Live</button>`);
    btns.push(`<button class="btn btn-ghost btn-sm" onclick="_agentReject('${p.proposal_id}')" style="font-size:10px;color:var(--red);">Reject</button>`);
  }
  if (!btns.length) btns.push(`<span style="font-size:11px;color:var(--text-muted);">—</span>`);
  return `<div style="display:flex;gap:4px;justify-content:center;flex-wrap:wrap;">${btns.join('')}</div>`;
}

async function loadAgentProposals() {
  const tbody = $('#agent-proposals-tbody');
  const pills = $('#agent-status-pills');
  const pending = $('#agent-pending-count');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="padding:20px;text-align:center;color:var(--text-muted);">Loading...</td></tr>';

  try {
    const [listResp, summResp] = await Promise.all([
      fetch('/api/v1/agent/proposals?limit=100'),
      fetch('/api/v1/agent/status-summary'),
    ]);
    const listData = await listResp.json();
    const summData = await summResp.json();
    const proposals = listData.proposals || [];

    // Status pills
    if (pills) {
      pills.innerHTML = Object.entries(summData.by_status || {})
        .filter(([,n]) => n > 0)
        .map(([s, n]) => {
          const m = _PROPOSAL_STATUS_META[s] || {};
          return `<span style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:12px;background:${m.bg||'var(--bg-card)'};color:${m.color||'var(--text-muted)'};">${m.label||s}: ${n}</span>`;
        }).join('');
    }
    if (pending) pending.textContent = summData.pending_action ?? '—';

    if (!proposals.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="padding:24px;text-align:center;color:var(--text-muted);">No proposals yet. Use POST /api/v1/agent/propose to create one.</td></tr>';
      return;
    }

    tbody.innerHTML = proposals.map(p => {
      const m = p.backtest_metrics || {};
      const winRate = m.win_rate_pct != null ? m.win_rate_pct + '%' : '—';
      const sharpe  = m.sharpe_ratio != null ? m.sharpe_ratio : '—';
      const shortId = p.proposal_id ? p.proposal_id.slice(0,8) : '—';
      return `<tr style="border-bottom:1px solid var(--border);transition:background var(--transition);" onmouseenter="this.style.background='var(--bg-card-hover)'" onmouseleave="this.style.background=''">
        <td style="padding:8px 12px;font-family:var(--mono);font-size:11px;color:var(--text-muted);" title="${p.proposal_id}">${shortId}</td>
        <td style="padding:8px 12px;font-weight:600;"><span class="badge badge-blue">${p.strategy_id}</span></td>
        <td style="padding:8px 12px;">${_agentStatusBadge(p.status)}</td>
        <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:var(--text-primary);">${winRate}</td>
        <td style="padding:8px 12px;text-align:right;font-family:var(--mono);color:var(--text-secondary);">${sharpe}</td>
        <td style="padding:8px 12px;color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${p.mutation_summary||''}">${p.mutation_summary || '—'}</td>
        <td style="padding:8px 12px;">${_agentActionButtons(p)}</td>
      </tr>`;
    }).join('');
  } catch(e) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="padding:20px;text-align:center;color:var(--red);">Error: ${e.message}</td></tr>`;
  }
}

function _agentSetResult(html) { const el = $('#agent-action-result'); if (el) el.innerHTML = html; }

async function _agentRunBacktest(proposalId) {
  _agentSetResult('<em style="color:var(--text-muted);">Running backtest...</em>');
  try {
    const r = await fetch(`/api/v1/agent/${proposalId}/backtest`, { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
    const d = await r.json();
    if (r.ok) {
      const m = d.metrics || {};
      _agentSetResult(`<span style="color:var(--green);font-weight:700;">Backtest done</span> | Win: ${m.win_rate_pct}% | Sharpe: ${m.sharpe_ratio} | MaxDD: ${m.max_drawdown_pct}%`);
      loadAgentProposals();
    } else {
      _agentSetResult(`<span style="color:var(--red);">Error: ${d.detail?.message||r.statusText}</span>`);
    }
  } catch(e) { _agentSetResult(`<span style="color:var(--red);">Error: ${e.message}</span>`); }
}

async function _agentApprove(proposalId) {
  _agentSetResult('<em style="color:var(--text-muted);">Approving...</em>');
  try {
    const r = await fetch(`/api/v1/agent/${proposalId}/approve`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({approved_by:'human'}) });
    const d = await r.json();
    if (r.ok) { _agentSetResult(`<span style="color:var(--green);font-weight:700;">Approved for paper trading.</span>`); loadAgentProposals(); }
    else _agentSetResult(`<span style="color:var(--red);">Error: ${d.detail?.message||r.statusText}</span>`);
  } catch(e) { _agentSetResult(`<span style="color:var(--red);">Error: ${e.message}</span>`); }
}

async function _agentReject(proposalId) {
  const reason = prompt('Rejection reason:');
  if (!reason || reason.length < 5) { _agentSetResult('<span style="color:var(--amber);">Rejection cancelled (need 5+ chars).</span>'); return; }
  try {
    const r = await fetch(`/api/v1/agent/${proposalId}/reject`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({reason}) });
    const d = await r.json();
    if (r.ok) { _agentSetResult(`<span style="color:var(--red);font-weight:700;">Rejected.</span>`); loadAgentProposals(); }
    else _agentSetResult(`<span style="color:var(--red);">Error: ${d.detail?.message||r.statusText}</span>`);
  } catch(e) { _agentSetResult(`<span style="color:var(--red);">Error: ${e.message}</span>`); }
}

async function _agentPromotePaper(proposalId) {
  _agentSetResult('<em style="color:var(--text-muted);">Starting paper trading...</em>');
  try {
    const r = await fetch(`/api/v1/agent/${proposalId}/promote-paper`, { method:'POST' });
    const d = await r.json();
    if (r.ok) { _agentSetResult(`<span style="color:var(--teal);font-weight:700;">Paper phase started.</span>`); loadAgentProposals(); }
    else _agentSetResult(`<span style="color:var(--red);">Error: ${d.detail?.message||r.statusText}</span>`);
  } catch(e) { _agentSetResult(`<span style="color:var(--red);">Error: ${e.message}</span>`); }
}

async function _agentPromoteLive(proposalId) {
  if (!confirm('Promote this proposal to LIVE? Capital allocation is unchanged.')) return;
  _agentSetResult('<em style="color:var(--text-muted);">Promoting to live...</em>');
  try {
    const r = await fetch(`/api/v1/agent/${proposalId}/promote-live`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({approved_by:'human'}) });
    const d = await r.json();
    if (r.ok) { _agentSetResult(`<span style="color:var(--green);font-weight:700;">Promoted to live! Manifest updated.</span>`); loadAgentProposals(); }
    else _agentSetResult(`<span style="color:var(--red);">Error: ${d.detail?.message||r.statusText}</span>`);
  } catch(e) { _agentSetResult(`<span style="color:var(--red);">Error: ${e.message}</span>`); }
}

// Load on tab activation
document.querySelectorAll('.nav-tab[data-tab="agent"]').forEach(btn => {
  btn.addEventListener('click', () => loadAgentProposals());
});

// Auto-refresh agent badge every 30s
setInterval(async () => {
  try {
    const r = await fetch('/api/v1/agent/status-summary');
    const d = await r.json();
    const p = d.pending_action ?? 0;
    const badge = $('#badge-agent-pending');
    if (badge) badge.textContent = p > 0 ? String(p) : '';
  } catch {}
}, 30000);

"""

with open(DASHBOARD, encoding="utf-8", errors="replace") as f:
    content = f.read()

# Insert before </script>
insert_marker = "</script>"
idx = content.rfind(insert_marker)
if idx == -1:
    print("ERROR: </script> not found!")
else:
    content = content[:idx] + AGENT_JS + content[idx:]
    with open(DASHBOARD, "w", encoding="utf-8", errors="replace") as f:
        f.write(content)
    print(f"Agent JS appended. Total chars: {len(content)}")
