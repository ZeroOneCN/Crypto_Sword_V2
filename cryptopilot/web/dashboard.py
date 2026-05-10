"""Dashboard HTML page — served by FastAPI, polls health APIs for live status."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CryptoPilot — 驾驶舱</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
  h1 { font-size: 1.5rem; margin-bottom: 20px; color: #38bdf8; display: flex; align-items: center; gap: 12px; }
  h1 small { font-size: 0.7rem; color: #64748b; font-weight: normal; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }
  .grid-wide { grid-template-columns: repeat(auto-fit, minmax(600px, 1fr)); }
  .card { background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155; }
  .card h2 { font-size: 0.9rem; color: #94a3b8; margin-bottom: 10px; letter-spacing: 0.05em; display: flex; justify-content: space-between; align-items: center; }
  .card h2 .hint { font-weight: normal; font-size: 0.75rem; color: #64748b; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
  .badge-ok { background: #065f46; color: #6ee7b7; }
  .badge-warn { background: #78350f; color: #fbbf24; }
  .badge-err { background: #7f1d1d; color: #fca5a5; }
  .badge-info { background: #1e3a5f; color: #93c5fd; }
  .badge-long { background: #064e3b; color: #34d399; }
  .badge-short { background: #7f1d1d; color: #fb7185; }
  .badge-hold { background: #1e293b; color: #64748b; border: 1px solid #334155; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th, td { padding: 5px 8px; text-align: left; border-bottom: 1px solid #1e293b; }
  th { color: #64748b; font-weight: 600; position: sticky; top: 0; background: #1e293b; }
  tr:hover td { background: #0f172a40; }
  .pnl-pos { color: #4ade80; }
  .pnl-neg { color: #f87171; }
  .meta { font-size: 0.7rem; color: #475569; margin-top: 12px; text-align: right; }
  .loading { color: #64748b; font-style: italic; }
  .error { color: #f87171; }
  .factor-bar { display: inline-flex; align-items: center; gap: 2px; }
  .factor-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
  .factor-dot-long { background: #34d399; }
  .factor-dot-short { background: #fb7185; }
  .factor-dot-neutral { background: #475569; }
  .signal-row { border-left: 3px solid transparent; }
  .signal-row.LONG { border-left-color: #34d399; }
  .signal-row.SHORT { border-left-color: #fb7185; }
  .signal-row.HOLD { border-left-color: #475569; }
  .nowrap { white-space: nowrap; }
  .truncate { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  .pulse { animation: pulse 2s ease-in-out infinite; }
  .scroll-table { overflow-x: auto; max-height: 300px; overflow-y: auto; }
  .conn-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 4px; }
  .conn-dot.ok { background: #4ade80; }
  .conn-dot.err { background: #f87171; }
  .conn-dot.warn { background: #fbbf24; }
</style>
</head>
<body>
<h1>
  CryptoPilot 驾驶舱
  <small id="timestamp"></small>
</h1>

<div class="grid" style="grid-template-columns: 1fr 1fr 1fr;">
  <!-- System Status -->
  <div class="card">
    <h2>系统状态</h2>
    <div id="status">Loading...</div>
  </div>

  <!-- Circuit Breaker -->
  <div class="card">
    <h2>风控状态</h2>
    <div id="circuit">Loading...</div>
  </div>

  <!-- Margin -->
  <div class="card">
    <h2>保证金</h2>
    <div id="margin">Loading...</div>
  </div>
</div>

<div class="grid grid-wide">
  <!-- Positions -->
  <div class="card">
    <h2>当前持仓</h2>
    <div id="positions">Loading...</div>
  </div>

  <!-- Performance -->
  <div class="card">
    <h2>交易绩效</h2>
    <div id="report">Loading...</div>
  </div>
</div>

<div class="grid grid-wide">
  <!-- Candidate Pool with Factor Scoring -->
  <div class="card">
    <h2>候选池评分明细 <span class="hint">Top-5 因子投票</span></h2>
    <div id="scoring_detail">Loading...</div>
  </div>

  <!-- Signal Log -->
  <div class="card">
    <h2>信号日志 <span class="hint">最近50条</span></h2>
    <div id="signal_log">暂无信号</div>
  </div>
</div>

<script>
async function load() {
  const ts = document.getElementById('timestamp');
  const now = new Date();
  ts.textContent = '更新: ' + now.toLocaleString() + ' | ' + now.toLocaleTimeString();

  // ---- System Status ----
  try {
    const r = await fetch('/health');
    const d = await r.json();
    const wsDot = d.websocket_connected ? '<span class="conn-dot ok"></span>已连接' : '<span class="conn-dot err"></span>断开';
    document.getElementById('status').innerHTML =
      '<p>状态: <span class="badge ' + (d.status === 'ok' ? 'badge-ok' : 'badge-err') + '">' + d.status.toUpperCase() + '</span></p>' +
      '<p>WebSocket: ' + wsDot + '</p>' +
      '<p>版本: ' + d.version + '</p>';
  } catch(e) {
    document.getElementById('status').innerHTML = '<p class="error">无法连接</p>';
  }

  // ---- Circuit Breaker ----
  try {
    const r = await fetch('/health/circuit');
    const d = await r.json();
    if (!d.error) {
      document.getElementById('circuit').innerHTML =
        '<p>熔断: <span class="badge ' + (d.tripped ? 'badge-err' : 'badge-ok') + '">' + (d.tripped ? '已触发' : '正常') + '</span></p>' +
        '<p>当日盈亏: <span class="' + (d.daily_pnl >= 0 ? 'pnl-pos' : 'pnl-neg') + '">$' + (d.daily_pnl || 0).toFixed(2) + '</span></p>';
    }
  } catch(e) {}

  // ---- Margin ----
  try {
    const r = await fetch('/health/margin');
    const d = await r.json();
    if (!d.error) {
      document.getElementById('margin').innerHTML =
        '<p>监控: <span class="badge ' + (d.running ? 'badge-ok' : 'badge-err') + '">' + (d.running ? '运行中' : '未启动') + '</span></p>' +
        '<p>警告阈值: ' + (d.warning_threshold * 100).toFixed(0) + '%</p>' +
        '<p>危急阈值: ' + (d.critical_threshold * 100).toFixed(0) + '%</p>';
    }
  } catch(e) {}

  // ---- Positions ----
  try {
    const r = await fetch('/health/positions');
    const d = await r.json();
    if (d.error) {
      document.getElementById('positions').innerHTML = '<p class="error">' + d.error + '</p>';
    } else if (d.positions && d.positions.length > 0) {
      let html = '<div class="scroll-table"><table><tr><th>币种</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>未实现盈亏</th></tr>';
      d.positions.forEach(p => {
        const pnl = parseFloat(p.unrealized_pnl || 0);
        const side = (p.side || '').toUpperCase();
        html += '<tr>' +
          '<td><strong>' + p.symbol + '</strong></td>' +
          '<td><span class="badge ' + (side === 'LONG' ? 'badge-long' : 'badge-short') + '">' + side + '</span></td>' +
          '<td>' + (p.qty || 0) + '</td>' +
          '<td>' + (p.entry_price || '-') + '</td>' +
          '<td>' + (p.mark_price || '-') + '</td>' +
          '<td class="' + (pnl >= 0 ? 'pnl-pos' : 'pnl-neg') + '">' + pnl.toFixed(2) + '</td>' +
          '</tr>';
      });
      html += '</table></div>' +
        '<p style="margin-top:6px;">总数: <span class="badge badge-info">' + d.count + '</span></p>';
      document.getElementById('positions').innerHTML = html;
    } else {
      document.getElementById('positions').innerHTML = '<p>无持仓</p>';
    }
  } catch(e) {}

  // ---- Performance ----
  try {
    const r = await fetch('/health/report/summary');
    const d = await r.json();
    if (!d.error) {
      const pnl = d.total_pnl || 0;
      document.getElementById('report').innerHTML =
        '<p>交易次数: <strong>' + d.total_trades + '</strong></p>' +
        '<p>胜率: <strong>' + d.win_rate + '%</strong></p>' +
        '<p>总盈亏: <span class="' + (pnl >= 0 ? 'pnl-pos' : 'pnl-neg') + '"><strong>$' + pnl.toFixed(2) + '</strong></span></p>' +
        '<p>最大回撤: <strong>' + d.max_drawdown_pct + '%</strong></p>' +
        '<p>夏普比率: <strong>' + d.sharpe_ratio + '</strong></p>';
    }
  } catch(e) {}

  // ---- Scoring Detail (候选池 + 因子评分) ----
  try {
    const r = await fetch('/health/scoring-detail');
    const d = await r.json();
    if (!d.error && d.candidates && d.candidates.length > 0) {
      let html = '<div class="scroll-table"><table><tr><th>币种</th><th>涨跌</th><th>扫描分</th><th>因子投票</th></tr>';
      d.candidates.forEach(c => {
        const changeCls = parseFloat(c.change_24h) >= 0 ? 'pnl-pos' : 'pnl-neg';
        let factorsHtml = '<div class="factor-bar">';
        if (c.factors && c.factors.length > 0) {
          c.factors.forEach(f => {
            const dotCls = f.direction === 'LONG' ? 'factor-dot-long' : (f.direction === 'SHORT' ? 'factor-dot-short' : 'factor-dot-neutral');
            factorsHtml += '<span class="factor-dot ' + dotCls + '" title="' + f.name + ': ' + f.direction + ' (' + f.score + '/' + f.weight + ')"></span>';
          });
        }
        factorsHtml += '</div>';
        html += '<tr>' +
          '<td><strong>' + c.symbol + '</strong></td>' +
          '<td class="' + changeCls + '">' + c.change_24h + '%</td>' +
          '<td><span class="badge badge-info">' + c.scanner_score + '</span></td>' +
          '<td>' + factorsHtml + '</td>' +
          '</tr>';
      });
      html += '</table></div>';
      document.getElementById('scoring_detail').innerHTML = html;
    } else {
      document.getElementById('scoring_detail').innerHTML = '<p>暂无候选</p>';
    }
  } catch(e) {
    document.getElementById('scoring_detail').innerHTML = '<p class="error">加载失败</p>';
  }

  // ---- Signal Log ----
  try {
    const r = await fetch('/health/signals');
    const d = await r.json();
    if (!d.error && d.signals && d.signals.length > 0) {
      let html = '<div class="scroll-table"><table><tr><th>时间</th><th>币种</th><th>动作</th><th>评分</th><th>说明</th></tr>';
      const recent = d.signals.slice().reverse().slice(0, 30);
      recent.forEach(s => {
        const act = s.action || '';
        let actLabel = act;
        let actCls = 'badge-hold';
        if (act.includes('LONG')) { actCls = 'badge-long'; }
        else if (act.includes('SHORT')) { actCls = 'badge-short'; }
        const tm = s.time ? new Date(s.time).toLocaleTimeString() : '-';
        html += '<tr class="signal-row ' + (act.includes('LONG') ? 'LONG' : (act.includes('SHORT') ? 'SHORT' : 'HOLD')) + '">' +
          '<td class="nowrap">' + tm + '</td>' +
          '<td><strong>' + s.symbol + '</strong></td>' +
          '<td><span class="badge ' + actCls + '">' + actLabel + '</span></td>' +
          '<td>' + (s.score || '-') + '</td>' +
          '<td class="truncate" title="' + (s.detail || '') + '">' + (s.detail || '-') + '</td>' +
          '</tr>';
      });
      html += '</table></div>';
      document.getElementById('signal_log').innerHTML = html;
    } else {
      document.getElementById('signal_log').innerHTML = '<p>暂无信号 (候选池有币种但评分未达阈值)</p>';
    }
  } catch(e) {
    document.getElementById('signal_log').innerHTML = '<p class="error">信号日志加载失败</p>';
  }
}

load();
setInterval(load, 10000);
</script>
</body>
</html>"""


def add_dashboard_route(app: FastAPI) -> None:
    """Add the dashboard route to a FastAPI app."""

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML
