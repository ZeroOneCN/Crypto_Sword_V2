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
  .perf-btn { background: #1e3a5f; color: #64748b; border: 1px solid #334155; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 0.72rem; }
  .perf-btn.active { background: #2563eb; color: #fff; border-color: #2563eb; }
  .perf-btn:hover:not(.active) { background: #1e3a5f; color: #93c5fd; }
  .daily-bar { display: inline-block; height: 20px; min-width: 2px; border-radius: 2px; margin: 0 1px; }
  .daily-bar-pos { background: #34d399; }
  .daily-bar-neg { background: #f87171; }
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
  <div class="stat-card"><div class="label">持仓数</div><div class="value" id="stat_poscount" style="color:#a78bfa">--</div><div class="sub">已开 / 上限</div></div>
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
    <div id="positions"><div class="scroll-table"><table><tr><th>币种</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>未实现盈亏</th><th>ROI</th><th>保护单</th></tr></table></div><p style="text-align:center;padding:20px;color:#64748b;">暂无持仓</p></div>
  </div>
</div>

<!-- Row 3: Multi-period Performance -->
<div class="grid">
  <div class="card">
    <h2>交易绩效 (Binance) <span class="hint" id="hint_perf"></span></h2>
    <div id="report">
      <div class="inline-stat"><span>7天盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>30天盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>累计盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>7天手续费</span><span>--</span></div>
      <div class="inline-stat"><span>7天资金费率</span><span>--</span></div>
      <div class="inline-stat"><span>今日盈亏</span><span>--</span></div>
    </div>
  </div>

  <div class="card">
    <h2>信号日志 <span class="hint" id="hint_sig"></span></h2>
    <div id="signal_log"><p style="text-align:center;padding:20px;color:#64748b;">暂无信号 — 评分未达阈值</p></div>
  </div>
</div>

<!-- Row 4: Scoring Detail + Trade History -->
<div class="grid">
  <div class="card">
    <h2>候选池评分明细 <span class="hint">Top-5 多因子投票</span></h2>
    <div id="scoring_detail"><p style="text-align:center;padding:20px;color:#64748b;">暂无候选 — 等待扫描器产出</p></div>
  </div>
  <div class="card">
    <h2>成交记录 <span class="hint" id="hint_trades"></span></h2>
    <div id="trade_history"><p style="text-align:center;padding:20px;color:#64748b;">暂无成交记录</p></div>
  </div>
</div>

<!-- Row 5: Daily PnL Chart -->
<div class="grid">
  <div class="card">
    <h2>每日盈亏走势 <span class="hint" id="hint_daily"></span></h2>
    <div id="daily_pnl"><p style="text-align:center;padding:20px;color:#64748b;">等待数据...</p></div>
  </div>
</div>
</div>

<div class="footer">
  <span>CryptoPilot v1.3</span>
  <span>刷新间隔 5s | 最近更新: <span id="last_update">--</span></span>
</div>

<script>
const REFRESH_MS = 5000;
let countdown = REFRESH_MS / 1000;
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
      upnlEl.textContent = fmtUSD(d.unrealized_pnl);
      upnlEl.style.color = d.unrealized_pnl >= 0 ? '#4ade80' : '#f87171';
      const mrEl = document.getElementById('stat_margin');
      const mrPct = (d.margin_ratio || 0) * 100;
      mrEl.textContent = mrPct.toFixed(2) + '%';
      mrEl.style.color = mrPct > 80 ? '#f87171' : mrPct > 50 ? '#fbbf24' : '#4ade80';
    }
  } catch(e) {}

  // ---- Positions (for count) ----
  try {
    const r = await fetch('/health/positions?_=' + Date.now());
    const d = await r.json();
    if (!d.error) {
      document.getElementById('stat_poscount').textContent = d.count + ' / ' + (window.maxPositions || 5);
      document.getElementById('hint_pos').textContent = d.count + ' / ' + (window.maxPositions || 5) + ' 个';
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

  // ---- Protection orders ----
  let protBySymbol = {};
  try {
    const r = await fetch('/health/orders?_=' + Date.now());
    const d = await r.json();
    if (!d.error && d.by_symbol) {
      d.by_symbol.forEach(s => {
        protBySymbol[s.symbol] = { sl: s.stop_orders, tp: s.tp_orders, total: s.total };
      });
    }
  } catch(e) {}

  // ---- Positions detail ----
  try {
    const r = await fetch('/health/positions?_=' + Date.now());
    const d = await r.json();
    if (!d.error && d.positions && d.positions.length > 0) {
      let html = '<div class="scroll-table"><table><tr><th>币种</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>未实现盈亏</th><th>ROI</th><th>保护单</th></tr>';
      d.positions.forEach(p => {
        const pnl = parseFloat(p.unrealized_pnl || 0);
        const roi = parseFloat(p.roi_pct || 0);
        const side = (p.side || '').toUpperCase();
        const prot = protBySymbol[p.symbol] || { sl: 0, tp: 0 };
        const protHtml = (prot.sl > 0 || prot.tp > 0)
          ? '<span class="badge badge-ok">SL:' + prot.sl + ' TP:' + prot.tp + '</span>'
          : '<span class="badge badge-err" style="animation:pulse 1s infinite">裸仓!</span>';
        html += '<tr>' +
          '<td><strong>' + p.symbol + '</strong></td>' +
          '<td><span class="badge ' + (side === 'LONG' ? 'badge-long' : 'badge-short') + '">' + side + '</span></td>' +
          '<td>' + fmtNum(p.qty, 3) + '</td>' +
          '<td>' + fmtNum(p.entry_price, 5) + '</td>' +
          '<td>' + fmtNum(p.mark_price, 5) + '</td>' +
          '<td class="' + cn(pnl) + '">' + fmtUSD(pnl) + '</td>' +
          '<td class="' + cn(roi) + '">' + fmtPct(roi) + '</td>' +
          '<td>' + protHtml + '</td>' +
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

  // ---- Binance 权威盈亏 ----
  try {
    const r = await fetch('/health/pnl');
    const d = await r.json();
    if (!d.error) {
      // net_pnl = realized_pnl + commission + funding (与 Binance 交易所显示一致)
      const net7 = d.net_pnl_7d || 0;
      const net30 = d.net_pnl_30d || 0;
      const netTotal = d.net_pnl_total || 0;
      const net1d = d.net_pnl_1d || 0;
      document.getElementById('report').innerHTML =
        '<div class="inline-stat"><span>7天净盈亏</span><span class="' + cn(net7) + ' value-big">' + fmtUSD(net7) + '</span></div>' +
        '<div class="inline-stat"><span>30天净盈亏</span><span class="' + cn(net30) + ' value-big">' + fmtUSD(net30) + '</span></div>' +
        '<div class="inline-stat"><span>累计净盈亏</span><span class="' + cn(netTotal) + ' value-big">' + fmtUSD(netTotal) + '</span></div>' +
        '<div class="inline-stat"><span>今日净盈亏</span><span class="' + cn(net1d) + ' value-big">' + fmtUSD(net1d) + '</span></div>' +
        '<div class="inline-stat"><span>手续费</span><span>' + fmtUSD(d.commission_7d || 0) + '</span></div>' +
        '<div class="inline-stat"><span>资金费率</span><span>' + fmtUSD(d.funding_7d || 0) + '</span></div>' +
        '<div class="inline-stat"><span>交易币种</span><span>' + (d.symbols_traded || 0) + '</span></div>' +
        '<div class="inline-stat" style="font-size:0.65rem;color:#475569;"><span>拉取记录</span><span>' + (d.total_events || 0) + ' 条</span></div>';
      document.getElementById('hint_perf').textContent = '含手续费+资金费率';
    }
  } catch(e) {}

  // ---- Trade History ----
  try {
    const r = await fetch('/health/trades');
    const d = await r.json();
    if (!d.error && d.trades && d.trades.length > 0) {
      let html = '<div class="scroll-table"><table><tr><th>时间</th><th>币种</th><th>方向</th><th>价格</th><th>数量</th><th>手续费</th><th>策略</th></tr>';
      d.trades.slice(0, 30).forEach(t => {
        const side = (t.side || '').toUpperCase();
        const sideCls = side === 'BUY' ? 'badge-long' : 'badge-short';
        const tm = t.filled_at ? new Date(t.filled_at).toLocaleTimeString() : '-';
        const strat = (t.strategy_name || t.type || '-');
        html += '<tr>' +
          '<td class="nowrap">' + tm + '</td>' +
          '<td><strong>' + t.symbol + '</strong></td>' +
          '<td><span class="badge ' + sideCls + '">' + side + '</span></td>' +
          '<td>' + fmtNum(t.price, 5) + '</td>' +
          '<td>' + fmtNum(t.qty, 4) + '</td>' +
          '<td>' + fmtNum(t.commission, 6) + '</td>' +
          '<td class="truncate" title="' + (strat) + '">' + (strat.length > 15 ? strat.slice(0,15)+'..' : strat) + '</td>' +
          '</tr>';
      });
      html += '</table></div>';
      document.getElementById('trade_history').innerHTML = html;
      document.getElementById('hint_trades').textContent = '共 ' + d.total + ' 笔';
    }
  } catch(e) {}

  // ---- Daily PnL ----
  try {
    const r = await fetch('/health/report/30d');
    const d = await r.json();
    if (!d.error && d.daily_pnl && d.daily_pnl.length > 0) {
      const bars = d.daily_pnl;
      const maxAbs = Math.max(...bars.map(b => Math.abs(b.pnl)), 0.01);
      let html = '<div style="display:flex;align-items:flex-end;gap:1px;height:80px;overflow-x:auto;padding:4px 0;">';
      bars.forEach(b => {
        const h = Math.max(4, (Math.abs(b.pnl) / maxAbs * 70));
        const cls = b.pnl >= 0 ? 'daily-bar-pos' : 'daily-bar-neg';
        html += '<div title="' + b.date + ': ' + fmtUSD(b.pnl) + ' (' + b.trades + '笔)" ' +
          'class="daily-bar ' + cls + '" style="height:' + h + 'px;flex:0 0 12px;"></div>';
      });
      html += '</div><div style="font-size:0.65rem;color:#475569;margin-top:4px;text-align:center;">每日盈亏柱状图 (最近30天)</div>';
      document.getElementById('daily_pnl').innerHTML = html;
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
