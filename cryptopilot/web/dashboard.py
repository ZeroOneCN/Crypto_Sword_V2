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
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0b1120; color: #e2e8f0; padding: 16px 20px; min-height: 100vh; }
  h1 { font-size: 1.3rem; margin-bottom: 16px; color: #38bdf8; display: flex; align-items: center; gap: 12px; }
  h1 small { font-size: 0.7rem; color: #475569; font-weight: normal; margin-left: auto; }
  .top-bar { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .stat-card { background: #111c2e; border: 1px solid #1e3a5f; border-radius: 8px; padding: 12px 18px; flex: 1; min-width: 140px; text-align: center; }
  .stat-card .label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
  .stat-card .value { font-size: 1.4rem; font-weight: 700; }
  .stat-card .sub { font-size: 0.7rem; color: #64748b; margin-top: 2px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 14px; margin-bottom: 14px; }
  .grid-3 { grid-template-columns: 1fr 1fr 1fr; }
  .card { background: #111c2e; border-radius: 8px; padding: 14px; border: 1px solid #1e293b; }
  .card h2 { font-size: 0.82rem; color: #94a3b8; margin-bottom: 10px; letter-spacing: 0.04em; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 8px; }
  .card h2 .hint { font-weight: normal; font-size: 0.7rem; color: #475569; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.68rem; font-weight: 600; }
  .badge-ok { background: #065f46; color: #6ee7b7; }
  .badge-warn { background: #78350f; color: #fbbf24; }
  .badge-err { background: #7f1d1d; color: #fca5a5; }
  .badge-info { background: #1e3a5f; color: #93c5fd; }
  .badge-long { background: #064e3b; color: #34d399; }
  .badge-short { background: #7f1d1d; color: #fb7185; }
  .badge-hold { background: #1e293b; color: #64748b; border: 1px solid #334155; }
  .badge-purple { background: #4a1942; color: #e879f9; }
  table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
  th, td { padding: 5px 7px; text-align: left; border-bottom: 1px solid #1a2332; }
  th { color: #64748b; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; }
  tr:hover td { background: #0f172a60; }
  .pnl-pos { color: #4ade80; }
  .pnl-neg { color: #f87171; }
  .zero { color: #64748b; }
  .footer { display: flex; justify-content: space-between; align-items: center; font-size: 0.68rem; color: #334155; margin-top: 8px; }
  .footer .refresh { color: #38bdf8; cursor: pointer; }
  .error { color: #f87171; font-size: 0.8rem; }
  .factor-bar { display: inline-flex; align-items: center; gap: 1px; }
  .factor-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
  .factor-dot-long { background: #34d399; }
  .factor-dot-short { background: #fb7185; }
  .factor-dot-neutral { background: #334155; }
  .signal-row { border-left: 3px solid transparent; }
  .signal-row.LONG { border-left-color: #34d399; }
  .signal-row.SHORT { border-left-color: #fb7185; }
  .signal-row.HOLD { border-left-color: #475569; }
  .nowrap { white-space: nowrap; }
  .truncate { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .scroll-table { overflow-x: auto; max-height: 280px; overflow-y: auto; }
  .conn-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 4px; }
  .conn-dot.ok { background: #4ade80; }
  .conn-dot.err { background: #f87171; }
  .conn-dot.warn { background: #fbbf24; }
  .conn-dot.pulse { animation: pulse 2s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  .value-big { font-size: 1.1rem; font-weight: 700; }
  .inline-stat { display: flex; justify-content: space-between; padding: 3px 0; font-size: 0.8rem; }
  .inline-stat span:last-child { font-weight: 600; }
</style>
</head>
<body>
<h1>
  CryptoPilot 驾驶舱
  <small id="timestamp">Loading...</small>
</h1>

<!-- Row 1: Account Stats Bar -->
<div class="top-bar" id="account_bar">
  <div class="stat-card"><div class="label">总余额</div><div class="value" style="color:#e2e8f0">--</div><div class="sub">USDT</div></div>
  <div class="stat-card"><div class="label">可用余额</div><div class="value" style="color:#93c5fd">--</div><div class="sub">可开仓</div></div>
  <div class="stat-card"><div class="label">未实现盈亏</div><div class="value" id="stat_upnl">--</div><div class="sub">浮动</div></div>
  <div class="stat-card"><div class="label">保证金率</div><div class="value" id="stat_margin">--</div><div class="sub">越低越安全</div></div>
  <div class="stat-card"><div class="label">持仓数</div><div class="value" style="color:#a78bfa">--</div><div class="sub">当前仓位</div></div>
  <div class="stat-card"><div class="label">风控状态</div><div class="value" id="stat_cb" style="font-size:1rem">--</div><div class="sub">熔断 / 正常</div></div>
</div>

<!-- Row 2: System Status + Positions -->
<div class="grid">
  <div class="card">
    <h2>系统 & 风控 <span class="hint" id="hint_ws"></span></h2>
    <div class="inline-stat"><span>行情源</span><span id="sys_ws">--</span></div>
    <div class="inline-stat"><span>熔断</span><span id="sys_cb">--</span></div>
    <div class="inline-stat"><span>当日盈亏</span><span id="sys_daily_pnl">--</span></div>
    <div class="inline-stat"><span>保证金监控</span><span id="sys_margin">--</span></div>
    <div class="inline-stat"><span>警告/危急阈值</span><span id="sys_margin_pct">--</span></div>
    <div class="inline-stat"><span>扫描候选池</span><span id="sys_pool">--</span></div>
    <div class="inline-stat"><span>数据源模式</span><span id="sys_mode">--</span></div>
  </div>

  <div class="card">
    <h2>当前持仓 <span class="hint" id="hint_pos"></span></h2>
    <div id="positions"><div class="scroll-table"><table><tr><th>币种</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>未实现盈亏</th><th>杠杆</th></tr></table></div><p style="text-align:center;padding:20px;color:#64748b;">暂无持仓</p></div>
  </div>
</div>

<!-- Row 3: Performance + Signal Log -->
<div class="grid">
  <div class="card">
    <h2>交易绩效 <span class="hint" id="hint_perf"></span></h2>
    <div id="report">
      <div class="inline-stat"><span>交易次数</span><span>--</span></div>
      <div class="inline-stat"><span>胜率</span><span>--</span></div>
      <div class="inline-stat"><span>总盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>最大回撤</span><span>--</span></div>
      <div class="inline-stat"><span>夏普比率</span><span>--</span></div>
      <div class="inline-stat"><span>盈亏因子</span><span>--</span></div>
    </div>
  </div>

  <div class="card">
    <h2>信号日志 <span class="hint" id="hint_sig"></span></h2>
    <div id="signal_log"><p style="text-align:center;padding:20px;color:#64748b;">暂无信号 — 评分未达阈值</p></div>
  </div>
</div>

<!-- Row 4: Candidate Scoring Detail -->
<div class="grid">
  <div class="card">
    <h2>候选池评分明细 <span class="hint">Top-5 多因子投票</span></h2>
    <div id="scoring_detail"><p style="text-align:center;padding:20px;color:#64748b;">暂无候选 — 等待扫描器产出</p></div>
  </div>
</div>

<div class="footer">
  <span>CryptoPilot v1.3</span>
  <span>刷新间隔 10s | 最近更新: <span id="last_update">--</span></span>
</div>

<script>
const REFRESH_MS = 10000;
let countdown = REFRESH_MS / 1000;
let refreshTimer = null;

function fmtUSD(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '--';
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '--';
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}
function fmtNum(v, d) {
  d = d || 2;
  const n = parseFloat(v);
  if (isNaN(n)) return '--';
  return n.toFixed(d);
}
function cn(v, pos, neg) {
  const n = parseFloat(v);
  if (isNaN(n) || n === 0) return 'zero';
  return n > 0 ? (pos || 'pnl-pos') : (neg || 'pnl-neg');
}

async function load() {
  const now = new Date();
  document.getElementById('timestamp').textContent = now.toLocaleString();
  document.getElementById('last_update').textContent = now.toLocaleTimeString();

  // Reset countdown
  countdown = REFRESH_MS / 1000;
  document.getElementById('timestamp').textContent = now.toLocaleString() + ' (下次刷新: ' + countdown + 's)';

  // ---- Account ----
  try {
    const r = await fetch('/health/account');
    const d = await r.json();
    if (!d.error) {
      const cards = document.querySelectorAll('#account_bar .stat-card');
      cards[0].querySelector('.value').textContent = fmtUSD(d.total_balance).replace('$','');
      cards[1].querySelector('.value').textContent = fmtUSD(d.available_balance).replace('$','');
      const upnlEl = document.getElementById('stat_upnl');
      upnlEl.textContent = fmtPct(d.unrealized_pnl);
      upnlEl.style.color = d.unrealized_pnl >= 0 ? '#4ade80' : '#f87171';
      const mrEl = document.getElementById('stat_margin');
      mrEl.textContent = fmtPct(d.margin_ratio * 100);
      mrEl.style.color = d.margin_ratio > 0.8 ? '#f87171' : d.margin_ratio > 0.5 ? '#fbbf24' : '#4ade80';
    }
  } catch(e) {}

  // ---- Positions (for count) ----
  try {
    const r = await fetch('/health/positions');
    const d = await r.json();
    if (!d.error) {
      const cards = document.querySelectorAll('#account_bar .stat-card');
      cards[4].querySelector('.value').textContent = d.count;
      document.getElementById('hint_pos').textContent = '共 ' + d.count + ' 个';
    }
  } catch(e) {}

  // ---- Health (System) ----
  let wsOk = false;
  try {
    const r = await fetch('/health');
    const d = await r.json();
    wsOk = d.websocket_connected;
    document.getElementById('sys_ws').innerHTML = wsOk ? '<span class="conn-dot ok pulse"></span>WebSocket 已连接' : '<span class="conn-dot err"></span>WebSocket 断开';
    document.getElementById('hint_ws').textContent = 'v' + d.version;
  } catch(e) {
    document.getElementById('sys_ws').innerHTML = '<span class="conn-dot err"></span>无法连接';
  }

  // ---- Circuit Breaker ----
  try {
    const r = await fetch('/health/circuit');
    const d = await r.json();
    if (!d.error) {
      const tripped = d.tripped;
      document.getElementById('sys_cb').innerHTML = tripped ? '<span class="badge badge-err">已熔断</span>' : '<span class="badge badge-ok">正常</span>';
      document.getElementById('sys_daily_pnl').innerHTML = '<span class="' + cn(d.daily_pnl) + '">' + fmtUSD(d.daily_pnl) + '</span>';
      // Update stat card
      const cbEl = document.getElementById('stat_cb');
      cbEl.textContent = tripped ? '已熔断' : '正常';
      cbEl.style.color = tripped ? '#f87171' : '#4ade80';
    }
  } catch(e) {}

  // ---- Margin Monitor ----
  try {
    const r = await fetch('/health/margin');
    const d = await r.json();
    if (!d.error) {
      document.getElementById('sys_margin').innerHTML = d.running ? '<span class="badge badge-ok">运行中</span>' : '<span class="badge badge-err">未启动</span>';
      document.getElementById('sys_margin_pct').textContent = (d.warning_threshold * 100).toFixed(0) + '% / ' + (d.critical_threshold * 100).toFixed(0) + '%';
    }
  } catch(e) {}

  // ---- System mode info ----
  try {
    document.getElementById('sys_mode').textContent = 'ws_ok' in window && window.ws_ok ? 'WebSocket 实时' : 'WebSocket / REST 降级';
  } catch(e) {}

  // ---- Positions detail ----
  try {
    const r = await fetch('/health/positions');
    const d = await r.json();
    if (!d.error && d.positions && d.positions.length > 0) {
      let html = '<div class="scroll-table"><table><tr><th>币种</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>未实现盈亏</th><th>杠杆</th></tr>';
      d.positions.forEach(p => {
        const pnl = parseFloat(p.unrealized_pnl || 0);
        const side = (p.side || '').toUpperCase();
        html += '<tr>' +
          '<td><strong>' + p.symbol + '</strong></td>' +
          '<td><span class="badge ' + (side === 'LONG' ? 'badge-long' : 'badge-short') + '">' + side + '</span></td>' +
          '<td>' + fmtNum(p.qty) + '</td>' +
          '<td>' + fmtNum(p.entry_price) + '</td>' +
          '<td>' + fmtNum(p.mark_price) + '</td>' +
          '<td class="' + cn(pnl) + '">' + fmtUSD(pnl) + '</td>' +
          '<td>' + (p.leverage || '--') + 'x</td>' +
          '</tr>';
      });
      html += '</table></div>';
      document.getElementById('positions').innerHTML = html;
    } else {
      document.getElementById('positions').innerHTML = '<p style="text-align:center;padding:20px;color:#64748b;">暂无持仓</p>';
    }
  } catch(e) {
    document.getElementById('positions').innerHTML = '<p class="error">持仓数据加载失败</p>';
  }

  // ---- Performance ----
  try {
    const r = await fetch('/health/report/summary');
    const d = await r.json();
    if (!d.error) {
      const pnl = parseFloat(d.total_pnl || 0);
      let html = '';
      html += '<div class="inline-stat"><span>交易次数</span><span>' + d.total_trades + '</span></div>';
      html += '<div class="inline-stat"><span>胜率</span><span>' + d.win_rate + '%</span></div>';
      html += '<div class="inline-stat"><span>总盈亏</span><span class="' + cn(pnl) + '">' + fmtUSD(pnl) + '</span></div>';
      html += '<div class="inline-stat"><span>最大回撤</span><span>' + d.max_drawdown_pct + '%</span></div>';
      html += '<div class="inline-stat"><span>夏普比率</span><span>' + d.sharpe_ratio + '</span></div>';
      document.getElementById('report').innerHTML = html;
    }
  } catch(e) {}

  // ---- Scoring Detail ----
  try {
    const r = await fetch('/health/scoring-detail');
    const d = await r.json();
    if (!d.error && d.candidates && d.candidates.length > 0) {
      let html = '<div class="scroll-table"><table><tr><th>币种</th><th>价格</th><th>涨跌</th><th>扫描分</th><th>因子投票 (绿=多 红=空 灰=中性)</th></tr>';
      d.candidates.forEach(c => {
        const changeCls = parseFloat(c.change_24h) >= 0 ? 'pnl-pos' : 'pnl-neg';
        let factorsHtml = '<div class="factor-bar">';
        if (c.factors && c.factors.length > 0) {
          c.factors.forEach(f => {
            let dotCls = 'factor-dot-neutral';
            if (f.direction === 'LONG') dotCls = 'factor-dot-long';
            else if (f.direction === 'SHORT') dotCls = 'factor-dot-short';
            factorsHtml += '<span class="factor-dot ' + dotCls + '" title="' + f.name + ': ' + f.direction + ' [' + f.score + ']"></span>';
          });
        }
        factorsHtml += '</div>';
        html += '<tr>' +
          '<td><strong style="color:#38bdf8">' + c.symbol + '</strong></td>' +
          '<td>' + fmtNum(c.price, 4) + '</td>' +
          '<td class="' + changeCls + '">' + fmtPct(c.change_24h) + '</td>' +
          '<td><span class="badge badge-purple">' + c.scanner_score + '</span></td>' +
          '<td>' + factorsHtml + '</td>' +
          '</tr>';
      });
      html += '</table></div>';
      document.getElementById('scoring_detail').innerHTML = html;
    } else {
      document.getElementById('scoring_detail').innerHTML = '<p style="text-align:center;padding:20px;color:#64748b;">暂无候选 — 等待扫描器产出</p>';
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
      const recent = d.signals.slice().reverse().slice(0, 25);
      recent.forEach(s => {
        const act = s.action || '';
        let actCls = 'badge-hold';
        if (act.includes('LONG')) actCls = 'badge-long';
        else if (act.includes('SHORT')) actCls = 'badge-short';
        const tm = s.time ? new Date(s.time).toLocaleTimeString() : '-';
        html += '<tr class="signal-row ' + (act.includes('LONG') ? 'LONG' : (act.includes('SHORT') ? 'SHORT' : 'HOLD')) + '">' +
          '<td class="nowrap">' + tm + '</td>' +
          '<td><strong>' + s.symbol + '</strong></td>' +
          '<td><span class="badge ' + actCls + '">' + act + '</span></td>' +
          '<td>' + (s.score || '-') + '</td>' +
          '<td class="truncate" title="' + (s.detail || '') + '">' + (s.detail || '-') + '</td>' +
          '</tr>';
      });
      html += '</table></div>';
      document.getElementById('signal_log').innerHTML = html;
      document.getElementById('hint_sig').textContent = '共 ' + d.total + ' 条';
    } else {
      document.getElementById('signal_log').innerHTML = '<p style="text-align:center;padding:20px;color:#64748b;">暂无信号 — 评分未达阈值</p>';
      document.getElementById('hint_sig').textContent = '0 条';
    }
  } catch(e) {
    document.getElementById('signal_log').innerHTML = '<p class="error">加载失败</p>';
  }
}

// Countdown timer
function tick() {
  countdown -= 1;
  if (countdown <= 0) countdown = REFRESH_MS / 1000;
  const td = document.getElementById('timestamp');
  if (td && td.textContent) {
    td.textContent = td.textContent.replace(/\(下次刷新: \d+s\)/, '(下次刷新: ' + countdown + 's)');
  }
}
setInterval(tick, 1000);

load();
setInterval(load, REFRESH_MS);
</script>
</body>
</html>"""


def add_dashboard_route(app: FastAPI) -> None:
    """Add the dashboard route to a FastAPI app."""

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML
