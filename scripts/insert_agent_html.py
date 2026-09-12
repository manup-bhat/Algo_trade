"""Insert Builder and Agent HTML tab panels into dashboard.html."""
import pathlib

DASHBOARD = pathlib.Path("app/static/dashboard.html")

BUILDER_AGENT_HTML = (
    '\n'
    '    <!-- Phase 3: Builder Tab Panel -->\n'
    '    <div class="tab-panel" id="tab-builder" style="overflow:hidden;flex-direction:row;gap:0;">\n'
    '      <div id="builder-palette" style="width:200px;min-width:160px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0;">\n'
    '        <div style="padding:10px 12px 6px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;">\n'
    '          <span style="font-size:11px;font-weight:700;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">Palette <span id="builder-palette-count" style="color:var(--text-muted);font-weight:400;"></span></span>\n'
    '          <button id="btn-builder-reload-palette" title="Reload" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:13px;padding:2px 4px;">&#8635;</button>\n'
    '        </div>\n'
    '        <div id="builder-palette-content" style="flex:1;overflow-y:auto;font-size:12px;"><div style="padding:16px;color:var(--text-muted);font-size:12px;text-align:center;">Click Builder tab to load...</div></div>\n'
    '      </div>\n'
    '      <div style="flex:1;display:flex;flex-direction:column;overflow:hidden;">\n'
    '        <div style="padding:8px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-wrap:wrap;">\n'
    '          <input id="builder-strategy-id" type="text" placeholder="Strategy ID" style="font-size:12px;padding:5px 10px;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);width:160px;"/>\n'
    '          <button id="btn-builder-validate" class="btn btn-ghost btn-sm">Validate</button>\n'
    '          <button id="btn-builder-backtest" class="btn btn-ghost btn-sm">Backtest</button>\n'
    '          <button id="btn-builder-save" class="btn btn-primary btn-sm">Save Strategy</button>\n'
    '          <button id="btn-builder-clear" class="btn btn-ghost btn-sm" style="margin-left:auto;color:var(--text-muted);">Clear</button>\n'
    '        </div>\n'
    '        <div id="builder-canvas" ondragover="event.preventDefault()" ondrop="_builderOnDrop(event)"\n'
    '             style="flex:1;position:relative;overflow:auto;background:radial-gradient(circle at 50% 50%,rgba(255,255,255,0.02) 1px,transparent 1px) 0 0/28px 28px;min-height:300px;">\n'
    '          <div id="builder-canvas-hint" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none;opacity:0.4;">\n'
    '            <div style="font-size:32px;margin-bottom:8px;">&#x2B21;</div>\n'
    '            <div style="font-size:13px;color:var(--text-muted);">Drag nodes from the palette</div>\n'
    '          </div>\n'
    '        </div>\n'
    '      </div>\n'
    '      <div style="width:260px;min-width:200px;border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0;">\n'
    '        <div style="padding:8px 12px;border-bottom:1px solid var(--border);font-size:11px;font-weight:700;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">Results</div>\n'
    '        <div id="builder-result-panel" style="flex:0 0 auto;padding:12px;font-size:12px;color:var(--text-muted);border-bottom:1px solid var(--border);min-height:80px;max-height:200px;overflow-y:auto;"><em>Run Validate or Backtest</em></div>\n'
    '        <div style="padding:6px 12px 4px;font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.4px;display:flex;justify-content:space-between;align-items:center;">IR Graph <button onclick="_builderCopyIR()" title="Copy JSON" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:11px;padding:0;">[copy]</button></div>\n'
    '        <pre id="builder-ir-preview" style="flex:0 0 auto;margin:0;padding:8px 12px;font-size:10px;font-family:var(--mono);color:var(--text-muted);background:var(--bg-deep);max-height:120px;overflow:auto;border-bottom:1px solid var(--border);">{}</pre>\n'
    '        <div style="padding:6px 12px 4px;font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.4px;">UI Panel Types <span id="builder-panel-type-count"></span></div>\n'
    '        <div id="builder-panel-list" style="flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:6px;"></div>\n'
    '      </div>\n'
    '    </div><!-- /tab-builder -->\n'
    '\n'
    '    <!-- Phase 4: Agent Tab Panel -->\n'
    '    <div class="tab-panel" id="tab-agent" style="overflow:hidden;flex-direction:column;">\n'
    '      <div style="padding:12px 20px 10px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-wrap:wrap;flex-shrink:0;">\n'
    '        <div>\n'
    '          <div style="font-size:14px;font-weight:700;color:var(--text-primary);">Agentic Strategy Loop</div>\n'
    '          <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">Propose to Backtest to Approve to Paper to Live. Capital is always human-set.</div>\n'
    '        </div>\n'
    '        <div style="margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">\n'
    '          <span style="font-size:11px;color:var(--text-muted);">Pending:</span>\n'
    '          <span id="agent-pending-count" style="font-size:14px;font-weight:700;color:var(--amber);font-family:var(--mono);">--</span>\n'
    '          <button class="btn btn-ghost btn-sm" onclick="loadAgentProposals()">Refresh</button>\n'
    '        </div>\n'
    '      </div>\n'
    '      <div id="agent-status-pills" style="padding:8px 20px;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--border);flex-shrink:0;min-height:36px;"></div>\n'
    '      <div style="flex:1;overflow-y:auto;">\n'
    '        <table style="width:100%;border-collapse:collapse;font-size:12px;">\n'
    '          <thead style="position:sticky;top:0;background:var(--bg-card);z-index:1;">\n'
    '            <tr style="border-bottom:1px solid var(--border);">\n'
    '              <th style="padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:600;font-size:11px;">ID</th>\n'
    '              <th style="padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:600;font-size:11px;">Strategy</th>\n'
    '              <th style="padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:600;font-size:11px;">Status</th>\n'
    '              <th style="padding:8px 12px;text-align:right;color:var(--text-muted);font-weight:600;font-size:11px;">Win%</th>\n'
    '              <th style="padding:8px 12px;text-align:right;color:var(--text-muted);font-weight:600;font-size:11px;">Sharpe</th>\n'
    '              <th style="padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:600;font-size:11px;">Summary</th>\n'
    '              <th style="padding:8px 12px;text-align:center;color:var(--text-muted);font-weight:600;font-size:11px;">Actions</th>\n'
    '            </tr>\n'
    '          </thead>\n'
    '          <tbody id="agent-proposals-tbody">\n'
    '            <tr><td colspan="7" style="padding:24px;text-align:center;color:var(--text-muted);">Click Refresh to load proposals</td></tr>\n'
    '          </tbody>\n'
    '        </table>\n'
    '      </div>\n'
    '      <div id="agent-action-result" style="flex-shrink:0;padding:10px 20px;border-top:1px solid var(--border);font-size:12px;color:var(--text-muted);min-height:32px;"></div>\n'
    '    </div><!-- /tab-agent -->\n'
)

# Add nav tabs for Builder and Agent
BUILDER_NAV = '      <button class="nav-tab" data-tab="builder" id="tab-btn-builder" title="Visual Strategy Builder">Builder</button>\n'
AGENT_NAV   = '      <button class="nav-tab" data-tab="agent" id="tab-btn-agent" title="Agentic Strategy Loop"><span>Agent</span><span id="badge-agent-pending" style="font-size:10px;font-weight:700;color:var(--amber);margin-left:4px;"></span></button>\n'

with open(DASHBOARD, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

# 1. Insert HTML panels before drawer-header (line 2751, 0-indexed 2750)
insert_panel_idx = None
for i, l in enumerate(lines):
    if '<!-- Exit Reasons' in l and 'anlz-bottom-grid' in lines[i+1]:
        insert_panel_idx = i
        break

if insert_panel_idx is None:
    # fallback: insert before drawer-header
    for i, l in enumerate(lines):
        if 'drawer-header' in l and '<div' in l:
            insert_panel_idx = i
            break

print(f"Inserting HTML panels before line {insert_panel_idx+1}")
lines = lines[:insert_panel_idx] + [BUILDER_AGENT_HTML] + lines[insert_panel_idx:]

# 2. Add nav tabs for Builder and Agent after the existing Builder nav button (already in HTML at ~line 2010)
# Re-find it since we shifted lines
builder_nav_idx = None
for i, l in enumerate(lines):
    if 'tab-btn-builder' in l and 'nav-tab' in l and 'button' in l:
        builder_nav_idx = i
        break

if builder_nav_idx is None:
    print("Builder nav tab already present — adding Agent nav only")
    for i, l in enumerate(lines):
        if 'data-tab="settings"' in l and 'nav-tab' in l:
            # Insert Builder+Agent after settings
            lines = lines[:i+1] + [BUILDER_NAV, AGENT_NAV] + lines[i+1:]
            print(f"Inserted Builder+Agent nav after settings tab at line {i+1}")
            break
else:
    # Insert Agent nav right after builder nav button (find the closing </button> tag)
    close_idx = builder_nav_idx
    for j in range(builder_nav_idx, builder_nav_idx+5):
        if '</button>' in lines[j]:
            close_idx = j
            break
    lines = lines[:close_idx+1] + [AGENT_NAV] + lines[close_idx+1:]
    print(f"Inserted Agent nav tab after line {close_idx+1}")

with open(DASHBOARD, "w", encoding="utf-8", errors="replace") as f:
    f.writelines(lines)

print(f"Done. Total lines: {len(lines)}")
