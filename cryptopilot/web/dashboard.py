"""Dashboard HTML page — served by FastAPI, polls health APIs for live status."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>CryptoPilot — Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
  h1 { font-size: 1.5rem; margin-bottom: 20px; color: #38bdf8; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; }
  .card { background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155; }
  .card h2 { font-size: 1rem; color: #94a3b8; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
  .badge-ok { background: #065f46; color: #6ee7b7; }
  .badge-warn { background: #78350f; color: #fbbf24; }
  .badge-err { background: #7f1d1d; color: #fca5a5; }
  .badge-info { background: #1e3a5f; color: #93c5fd; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #334155; }
  th { color: #94a3b8; font-weight: 600; }
  .pnl-pos { color: #4ade80; }
  .pnl-neg { color: #f87171; }
  .meta { font-size: 0.75rem; color: #64748b; margin-top: 12px; }
  .loading { color: #64748b; font-style: italic; }
  .error { color: #f87171; }
</style>
</head>
<body>
<h1>CryptoPilot Dashboard</h1>

<div class="grid">
  <!-- System Status -->
  <div class="card">
    <h2>System Status</h2>
    <div id="status">Loading...</div>
  </div>

  <!-- Positions -->
  <div class="card">
    <h2>Open Positions</h2>
    <div id="positions">Loading...</div>
  </div>

  <!-- Strategies -->
  <div class="card">
    <h2>Strategies</h2>
    <div id="strategies">Loading...</div>
  </div>

  <!-- Performance -->
  <div class="card">
    <h2>Performance</h2>
    <div id="report">Loading...</div>
  </div>

  <!-- Circuit Breaker -->
  <div class="card">
    <h2>Circuit Breaker</h2>
    <div id="circuit">Loading...</div>
  </div>

  <!-- Margin -->
  <div class="card">
    <h2>保证金监控</h2>
    <div id="margin">Loading...</div>
  </div>

  <!-- Candidate Pool -->
  <div class="card">
    <h2>候选池 (Top-10)</h2>
    <div id="candidates">Loading...</div>
  </div>

  <!-- Recent Scan Signals -->
  <div class="card">
    <h2>扫描信号</h2>
    <div id="scan_signals">暂无信号</div>
  </div>
</div>

<p class="meta" id="timestamp"></p>

<script>
async function load() {
  try {
    // System status
    let r = await fetch('/health');
    let d = await r.json();
    document.getElementById('status').innerHTML =
      '<p>Status: <span class="badge ' + (d.status === 'ok' ? 'badge-ok' : 'badge-err') + '">' + d.status.toUpperCase() + '</span></p>' +
      '<p>WebSocket: <span class="badge ' + (d.websocket_connected ? 'badge-ok' : 'badge-err') + '">' + (d.websocket_connected ? 'CONNECTED' : 'DISCONNECTED') + '</span></p>' +
      '<p>Version: ' + d.version + '</p>';

    // Positions
    r = await fetch('/health/positions');
    d = await r.json();
    if (d.error) {
      document.getElementById('positions').innerHTML = '<p class="error">' + d.error + '</p>';
    } else {
      let html = '<p>Count: <span class="badge badge-info">' + d.count + '</span></p>';
      if (d.positions && d.positions.length > 0) {
        html += '<table><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Mark</th><th>PNL</th></tr>';
        d.positions.forEach(p => {
          let pnl = parseFloat(p.unrealized_pnl || 0);
          html += '<tr>' +
            '<td>' + p.symbol + '</td>' +
            '<td>' + (p.side || '') + '</td>' +
            '<td>' + (p.qty || 0) + '</td>' +
            '<td>' + (p.entry_price || 0) + '</td>' +
            '<td>' + (p.mark_price || 0) + '</td>' +
            '<td class="' + (pnl >= 0 ? 'pnl-pos' : 'pnl-neg') + '">' + pnl.toFixed(2) + '</td>' +
            '</tr>';
        });
        html += '</table>';
      } else {
        html += '<p>No open positions</p>';
      }
      document.getElementById('positions').innerHTML = html;
    }

    // Strategies
    r = await fetch('/health/strategies');
    d = await r.json();
    if (d.error) {
      document.getElementById('strategies').innerHTML = '<p class="error">' + d.error + '</p>';
    } else {
      let html = '<p>Active: <span class="badge badge-info">' + d.active + '</span> / Total: ' + d.total + '</p>';
      if (d.strategies && d.strategies.length > 0) {
        html += '<table><tr><th>ID</th><th>Symbol</th><th>Status</th><th>Pos</th></tr>';
        d.strategies.forEach(s => {
          let status = s.paused ? 'PAUSED' : (s.enabled ? 'RUNNING' : 'STOPPED');
          let cls = status === 'RUNNING' ? 'badge-ok' : (status === 'PAUSED' ? 'badge-warn' : 'badge-err');
          html += '<tr>' +
            '<td style="max-width:120px;overflow:hidden">' + s.strategy_id + '</td>' +
            '<td>' + s.symbol + '</td>' +
            '<td><span class="badge ' + cls + '">' + status + '</span></td>' +
            '<td>' + (s.has_position ? '<span class="badge badge-info">YES</span>' : '-') + '</td>' +
            '</tr>';
        });
        html += '</table>';
      }
      document.getElementById('strategies').innerHTML = html;
    }

    // Performance
    try {
      r = await fetch('/health/report/summary');
      d = await r.json();
      if (!d.error) {
        let pnl = d.total_pnl || 0;
        document.getElementById('report').innerHTML =
          '<p>Trades: <strong>' + d.total_trades + '</strong></p>' +
          '<p>Win Rate: <strong>' + d.win_rate + '%</strong></p>' +
          '<p>Total PnL: <span class="' + (pnl >= 0 ? 'pnl-pos' : 'pnl-neg') + '"><strong>$' + d.total_pnl + '</strong></span></p>' +
          '<p>Max DD: <strong>' + d.max_drawdown_pct + '%</strong></p>' +
          '<p>Sharpe: <strong>' + d.sharpe_ratio + '</strong></p>';
      }
    } catch(e) {}

    // Circuit breaker
    r = await fetch('/health/circuit');
    d = await r.json();
    if (!d.error) {
      document.getElementById('circuit').innerHTML =
        '<p>Tripped: <span class="badge ' + (d.tripped ? 'badge-err' : 'badge-ok') + '">' + (d.tripped ? 'YES' : 'NO') + '</span></p>' +
        '<p>Daily PnL: $' + (d.daily_pnl || 0).toFixed(2) + '</p>';
    }

    // Margin
    try {
      r = await fetch('/health/margin');
      d = await r.json();
      if (!d.error) {
        document.getElementById('margin').innerHTML =
          '<p>运行中: <span class="badge ' + (d.running ? 'badge-ok' : 'badge-err') + '">' + (d.running ? '是' : '否') + '</span></p>' +
          '<p>警告阈值: ' + (d.warning_threshold * 100).toFixed(0) + '%</p>' +
          '<p>危急阈值: ' + (d.critical_threshold * 100).toFixed(0) + '%</p>';
      }
    } catch(e) {}

    // Candidates
    try {
      r = await fetch('/health/candidates');
      d = await r.json();
      if (!d.error && d.candidates && d.candidates.length > 0) {
        let html = '<table><tr><th>币种</th><th>价格</th><th>涨跌</th><th>量比</th><th>OI变化</th><th>评分</th></tr>';
        d.candidates.slice(0, 10).forEach(c => {
          let changeColor = c.change_24h >= 0 ? 'pnl-pos' : 'pnl-neg';
          html += '<tr>' +
            '<td><strong>' + c.symbol + '</strong></td>' +
            '<td>' + c.price + '</td>' +
            '<td class="' + changeColor + '">' + c.change_24h + '%</td>' +
            '<td>' + c.volume_ratio + 'x</td>' +
            '<td>' + c.oi_change + '%</td>' +
            '<td><span class="badge badge-info">' + c.score + '</span></td>' +
            '</tr>';
        });
        html += '</table>';
        document.getElementById('candidates').innerHTML = html;
      } else {
        document.getElementById('candidates').innerHTML = '<p>暂无候选</p>';
      }
    } catch(e) {
      document.getElementById('candidates').innerHTML = '<p class="error">候选池加载失败</p>';
    }

    document.getElementById('timestamp').textContent = 'Updated: ' + new Date().toLocaleString();
  } catch(e) {
    console.error(e);
  }
}

load();
setInterval(load, 15000);
</script>
</body>
</html>"""


def add_dashboard_route(app: FastAPI) -> None:
    """Add the dashboard route to a FastAPI app."""

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML
