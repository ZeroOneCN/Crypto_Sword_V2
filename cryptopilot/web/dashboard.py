"""Dashboard HTML for the trading control center."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CryptoPilot 控制台</title>
<style>
  :root{
    --bg:#0a0d10;
    --bg-soft:#0f1419;
    --panel:#151b22;
    --panel-2:#1b232c;
    --line:rgba(255,255,255,.08);
    --line-strong:rgba(255,255,255,.14);
    --text:#eef3f8;
    --muted:#9aa8b7;
    --dim:#66727f;
    --gold:#d8b66a;
    --gold-soft:rgba(216,182,106,.14);
    --green:#53d18a;
    --green-soft:rgba(83,209,138,.14);
    --red:#ff7667;
    --red-soft:rgba(255,118,103,.14);
    --blue:#7bb9ff;
    --blue-soft:rgba(123,185,255,.14);
    --radius:18px;
    --shadow:0 18px 42px rgba(0,0,0,.28);
  }
  *{box-sizing:border-box}
  html,body{
    margin:0;
    min-height:100%;
    color:var(--text);
    background:
      radial-gradient(circle at top left, rgba(216,182,106,.09), transparent 22%),
      radial-gradient(circle at top right, rgba(123,185,255,.08), transparent 22%),
      linear-gradient(180deg, #090b0e 0%, #10161d 100%);
    font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  }
  body{line-height:1.45}
  *::-webkit-scrollbar{width:10px;height:10px}
  *::-webkit-scrollbar-thumb{
    background:linear-gradient(180deg, rgba(216,182,106,.55), rgba(123,185,255,.35));
    border-radius:999px;
    border:2px solid transparent;
    background-clip:padding-box;
  }
  *::-webkit-scrollbar-track{background:rgba(255,255,255,.04);border-radius:999px}
  .shell{max-width:1700px;margin:0 auto;padding:18px}
  .topbar{
    display:flex;justify-content:space-between;align-items:center;gap:12px;
    margin-bottom:16px;
  }
  .title{
    margin:0;
    font-size:28px;
    font-weight:800;
    letter-spacing:-.03em;
  }
  .subtext{margin-top:6px;color:var(--muted);font-size:13px}
  .top-actions{display:flex;gap:10px;align-items:center}
  button,.badge{
    border:1px solid var(--line);
    border-radius:999px;
    background:rgba(255,255,255,.04);
    color:var(--text);
    font:inherit;
  }
  button{padding:10px 14px;cursor:pointer}
  button:hover{border-color:var(--line-strong)}
  .badge{display:inline-flex;align-items:center;padding:8px 12px;font-size:12px}
  .badge.good{color:var(--green);background:var(--green-soft)}
  .badge.bad{color:var(--red);background:var(--red-soft)}
  .badge.info{color:var(--blue);background:var(--blue-soft)}
  .badge.warn{color:var(--gold);background:var(--gold-soft)}
  .stats{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:14px;
    margin-bottom:16px;
  }
  .card,.panel,.feed-item,.metric,.strategy-card{
    border:1px solid var(--line);
    background:linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.018));
    box-shadow:var(--shadow);
  }
  .card{
    padding:14px 15px;
    border-radius:16px;
    min-height:110px;
  }
  .label{
    font-size:11px;
    letter-spacing:.14em;
    color:var(--muted);
    text-transform:uppercase;
  }
  .value{
    margin-top:10px;
    font-size:24px;
    font-weight:800;
    letter-spacing:-.04em;
  }
  .hint{margin-top:8px;color:var(--dim);font-size:12px}
  .good{color:var(--green)}
  .bad{color:var(--red)}
  .muted{color:var(--muted)}
  .layout{
    display:grid;
    grid-template-columns:minmax(0,1.3fr) minmax(360px,.9fr);
    gap:16px;
    align-items:start;
  }
  .stack{display:flex;flex-direction:column;gap:16px;min-width:0}
  .panel{
    border-radius:20px;
    padding:16px;
    min-height:220px;
  }
  .panel-head{
    display:flex;justify-content:space-between;align-items:flex-start;gap:12px;
    margin-bottom:12px;
  }
  .panel-title{margin:0;font-size:22px;font-weight:800;letter-spacing:-.03em}
  .panel-sub{margin-top:5px;color:var(--muted);font-size:13px}
  .panel-body{display:flex;flex-direction:column;gap:12px;min-height:0}
  .table-wrap{
    overflow:auto;
    max-height:440px;
    border-radius:16px;
    border:1px solid rgba(255,255,255,.06);
    background:rgba(0,0,0,.16);
  }
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{
    padding:11px 12px;
    border-bottom:1px solid rgba(255,255,255,.06);
    text-align:left;
    white-space:nowrap;
    vertical-align:top;
  }
  th{
    position:sticky;top:0;z-index:1;
    background:rgba(20,25,31,.96);
    color:var(--muted);
    font-size:11px;
    letter-spacing:.12em;
    text-transform:uppercase;
  }
  .symbol b{display:block;font-size:14px}
  .symbol span{display:block;margin-top:4px;color:var(--dim);font-size:11px}
  .tag{
    display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;
    font-size:11px;font-weight:700;letter-spacing:.06em;
  }
  .tag.long{background:var(--green-soft);color:var(--green)}
  .tag.short{background:var(--red-soft);color:var(--red)}
  .tag.hold{background:var(--blue-soft);color:var(--blue)}
  .tag.warn{background:var(--gold-soft);color:var(--gold)}
  .mono{font-family:"Cascadia Mono","SFMono-Regular",Consolas,monospace}
  .split{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:12px;
  }
  .feed{
    display:flex;
    flex-direction:column;
    gap:10px;
    max-height:360px;
    overflow:auto;
    padding-right:2px;
  }
  .feed-item{
    border-radius:16px;
    padding:12px 13px;
    display:grid;
    grid-template-columns:82px minmax(0,1fr) auto;
    gap:10px;
    align-items:start;
  }
  .feed-time{font-size:12px;color:var(--dim)}
  .feed-title{font-size:14px;font-weight:700}
  .feed-detail{margin-top:4px;color:var(--muted);font-size:12px;word-break:break-word}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .chip{
    display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;
    border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.035);
    color:var(--muted);font-size:11px;
  }
  .metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
  .metric{padding:14px;border-radius:16px}
  .metric .value{font-size:22px}
  .list{display:flex;flex-direction:column;gap:10px}
  .row{
    display:flex;justify-content:space-between;gap:12px;
    border-bottom:1px solid rgba(255,255,255,.06);
    padding-bottom:9px;
    font-size:13px;
  }
  .row:last-child{border-bottom:none;padding-bottom:0}
  .strategy-list{display:flex;flex-direction:column;gap:12px;max-height:500px;overflow:auto}
  .strategy-card{padding:14px;border-radius:16px}
  .strategy-top{display:flex;justify-content:space-between;gap:10px;align-items:start}
  .strategy-name{font-size:15px;font-weight:800}
  .strategy-meta{margin-top:4px;color:var(--muted);font-size:11px}
  .strategy-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}
  .mini{padding:10px 11px;border-radius:14px;background:rgba(255,255,255,.03)}
  .mini .label{font-size:10px}
  .mini .value{font-size:17px;margin-top:6px}
  .chart{
    min-height:220px;
    display:flex;
    align-items:flex-end;
    gap:4px;
    padding:14px 10px 4px;
    border-radius:16px;
    border:1px solid rgba(255,255,255,.06);
    background:rgba(0,0,0,.15);
  }
  .bar{flex:1 1 0;min-width:8px;border-radius:999px 999px 4px 4px}
  .bar.pos{background:linear-gradient(180deg, rgba(83,209,138,.95), rgba(83,209,138,.35))}
  .bar.neg{background:linear-gradient(180deg, rgba(255,118,103,.95), rgba(255,118,103,.35))}
  .axis{display:flex;justify-content:space-between;color:var(--dim);font-size:11px;padding:0 4px}
  .log-box{
    max-height:420px;
    overflow:auto;
    border-radius:16px;
    border:1px solid rgba(255,255,255,.06);
    background:#0e1318;
    padding:12px;
  }
  .log-line{
    display:grid;
    grid-template-columns:70px 60px minmax(0,1fr);
    gap:10px;
    padding:4px 0;
    font-family:"Cascadia Mono","SFMono-Regular",Consolas,monospace;
    font-size:12px;
  }
  .empty{padding:18px;color:var(--muted);text-align:center}
  @media (max-width:1380px){
    .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
    .layout{grid-template-columns:1fr}
  }
  @media (max-width:860px){
    .shell{padding:14px}
    .stats,.split,.metrics,.strategy-grid{grid-template-columns:1fr}
    .feed-item{grid-template-columns:1fr}
  }
</style>
</head>
<body>
<div class="shell">
  <div class="topbar">
    <div>
      <h1 class="title">CryptoPilot 交易控制台</h1>
      <div class="subtext">双列布局、统一活动流、数据库复盘口径、分批 TP 可视化。</div>
    </div>
    <div class="top-actions">
      <span class="badge info mono" id="clock">--</span>
      <button onclick="loadAll(true)">刷新</button>
    </div>
  </div>

  <section class="stats">
    <div class="card">
      <div class="label">系统状态</div>
      <div class="value" id="kpi_status">--</div>
      <div class="hint" id="kpi_status_hint">--</div>
    </div>
    <div class="card">
      <div class="label">账户权益</div>
      <div class="value" id="kpi_balance">--</div>
      <div class="hint" id="kpi_balance_hint">--</div>
    </div>
    <div class="card">
      <div class="label">持仓 / 保护单</div>
      <div class="value" id="kpi_positions">--</div>
      <div class="hint" id="kpi_positions_hint">--</div>
    </div>
    <div class="card">
      <div class="label">启用策略</div>
      <div class="value" id="kpi_presets">--</div>
      <div class="hint" id="kpi_presets_hint">--</div>
    </div>
  </section>

  <section class="layout">
    <div class="stack">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">当前持仓</h2>
            <div class="panel-sub">显示开仓原因、已命中 TP 层级、剩余保护单覆盖、平仓复盘所需的核心字段。</div>
          </div>
          <span class="badge good">实时持仓</span>
        </div>
        <div class="panel-body">
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>币种</th>
                  <th>方向</th>
                  <th>策略</th>
                  <th>价格</th>
                  <th>盈亏</th>
                  <th>TP 进度</th>
                  <th>开仓原因</th>
                  <th>保护单</th>
                </tr>
              </thead>
              <tbody id="positions_body"></tbody>
            </table>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">复盘与成交</h2>
            <div class="panel-sub">成交笔数统一按一开一平算 1 笔，左侧看综合表现，右侧看最近已完成交易。</div>
          </div>
          <span class="badge warn" id="trade_count_badge">--</span>
        </div>
        <div class="panel-body split">
          <div class="list">
            <div class="metrics">
              <div class="metric">
                <div class="label">今日净盈亏</div>
                <div class="value" id="perf_1d">--</div>
                <div class="hint" id="perf_1d_sub">--</div>
              </div>
              <div class="metric">
                <div class="label">7日净盈亏</div>
                <div class="value" id="perf_7d">--</div>
                <div class="hint" id="perf_7d_sub">--</div>
              </div>
              <div class="metric">
                <div class="label">30日净盈亏</div>
                <div class="value" id="perf_30d">--</div>
                <div class="hint" id="perf_30d_sub">--</div>
              </div>
              <div class="metric">
                <div class="label">累计净盈亏</div>
                <div class="value" id="perf_all">--</div>
                <div class="hint" id="perf_all_sub">--</div>
              </div>
            </div>
            <div class="panel" style="padding:14px">
              <div class="panel-sub" style="margin-top:0">复盘摘要</div>
              <div class="list" id="report_summary"></div>
            </div>
          </div>
          <div class="feed" id="recent_trades"></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">候选、信号与操作记录</h2>
            <div class="panel-sub">统一视觉样式，减少一屏过长的问题；所有关键动作都进入活动流以便复盘。</div>
          </div>
          <span class="badge info">统一事件流</span>
        </div>
        <div class="panel-body split">
          <div class="panel" style="padding:14px">
            <div class="panel-sub" style="margin-top:0">候选与信号</div>
            <div class="feed" id="signals_mix"></div>
          </div>
          <div class="panel" style="padding:14px">
            <div class="panel-sub" style="margin-top:0">活动记录</div>
            <div class="feed" id="activity_feed"></div>
          </div>
        </div>
      </section>
    </div>

    <div class="stack">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">策略拆分</h2>
            <div class="panel-sub">按 preset 看净盈亏、胜率、笔数、平均持仓、TP 命中和退出原因。</div>
          </div>
          <span class="badge info">按数据库复盘</span>
        </div>
        <div class="panel-body">
          <div class="strategy-list" id="strategy_cards"></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">30 日净盈亏</h2>
            <div class="panel-sub">日级净盈亏轨迹，适合和活动流、日志对照复盘。</div>
          </div>
          <span class="badge warn">日报表</span>
        </div>
        <div class="panel-body">
          <div class="chart" id="daily_chart"></div>
          <div class="axis" id="daily_axis"></div>
          <div class="list" id="daily_meta"></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">运行日志</h2>
            <div class="panel-sub">保留滚动条和阅读位置，不再把视图硬拉到最底部；只有靠近底部时才自动跟随。</div>
          </div>
          <span class="badge info" id="logs_source">最近日志</span>
        </div>
        <div class="panel-body">
          <div class="log-box" id="log_lines"></div>
        </div>
      </section>
    </div>
  </section>
</div>

<script>
const REFRESH_MS = 5000;
const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });
const num = v => Number.isFinite(Number(v)) ? Number(v) : 0;
const money = v => `${num(v) >= 0 ? '+' : ''}${fmt.format(num(v))} USDT`;
const plainMoney = v => `${fmt.format(num(v))} USDT`;
const pct = v => `${num(v) >= 0 ? '+' : ''}${num(v).toFixed(2)}%`;
const esc = v => String(v ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');
const price = v => num(v) ? Number(v).toPrecision(8).replace(/\.?0+$/, '') : '--';
const cls = v => num(v) > 0 ? 'good' : (num(v) < 0 ? 'bad' : 'muted');
const dirClass = side => {
  const s = String(side || '').toUpperCase();
  if (s === 'LONG' || s === 'BUY' || s.includes('LONG')) return 'long';
  if (s === 'SHORT' || s === 'SELL' || s.includes('SHORT')) return 'short';
  return 'hold';
};
const holdLabel = sec => {
  const total = Math.max(0, Math.floor(num(sec)));
  if (!total) return '--';
  if (total < 60) return `${total}s`;
  const mins = Math.floor(total / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  if (hours < 24) return `${hours}h${String(remMins).padStart(2, '0')}m`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return `${days}d${String(remHours).padStart(2, '0')}h`;
};

function renderEmpty(id, text){
  document.getElementById(id).innerHTML = `<div class="empty">${esc(text)}</div>`;
}

function row(label, value){
  return `<div class="row"><span class="muted">${label}</span><span>${value}</span></div>`;
}

function feedItem(time, title, detail, badge, badgeClass='hold', chips=[]){
  return `<div class="feed-item">
    <div class="feed-time">${esc(time)}</div>
    <div>
      <div class="feed-title">${title}</div>
      <div class="feed-detail">${detail}</div>
      ${chips.length ? `<div class="chips">${chips.map(v => `<span class="chip">${esc(v)}</span>`).join('')}</div>` : ''}
    </div>
    <div><span class="tag ${badgeClass}">${esc(badge)}</span></div>
  </div>`;
}

function strategyCard(name, report={}, runtime={}){
  const pnlClass = cls(report.pnl || 0);
  const breakdown = Object.entries(report.exit_reason_breakdown || {}).slice(0, 3)
    .map(([k, v]) => `${k}:${v}`).join(' / ') || '--';
  return `<div class="strategy-card">
    <div class="strategy-top">
      <div>
        <div class="strategy-name">${esc(name)}</div>
        <div class="strategy-meta">预算 ${num(runtime.risk_budget || 0)}% / 并发 ${runtime.max_concurrent ?? '--'} / 止损 ${runtime.stop_loss_pct ?? '--'}%</div>
      </div>
      <span class="badge info">${esc(report.avg_hold_time || holdLabel(report.avg_hold_time_seconds || 0))}</span>
    </div>
    <div class="strategy-grid">
      <div class="mini"><div class="label">净盈亏</div><div class="value ${pnlClass}">${money(report.pnl || 0)}</div></div>
      <div class="mini"><div class="label">胜率</div><div class="value">${pct(report.win_rate || 0)}</div></div>
      <div class="mini"><div class="label">交易笔数</div><div class="value">${num(report.trades || 0)}</div></div>
      <div class="mini"><div class="label">Profit Factor</div><div class="value">${report.profit_factor ?? '--'}</div></div>
    </div>
    <div class="hint">TP1/TP2/TP3: ${num(report.tp_hits?.TP1 || 0)} / ${num(report.tp_hits?.TP2 || 0)} / ${num(report.tp_hits?.TP3 || 0)} | ${esc(breakdown)}</div>
  </div>`;
}

let logPinnedToBottom = true;

function setText(id, value, className='value'){
  const el = document.getElementById(id);
  el.textContent = value;
  el.className = className;
}

function renderLogs(data){
  const box = document.getElementById('log_lines');
  const nearBottom = (box.scrollHeight - box.scrollTop - box.clientHeight) < 36;
  const prevScrollTop = box.scrollTop;
  logPinnedToBottom = nearBottom || box.innerHTML.trim() === '';
  if (!data || data.error || !Array.isArray(data.lines) || !data.lines.length){
    renderEmpty('log_lines', '暂无日志');
    return;
  }
  document.getElementById('logs_source').textContent = `${data.file || 'logs'} / ${data.lines.length} lines`;
  box.innerHTML = data.lines.map(item => `
    <div class="log-line">
      <span class="muted">${esc(item.time || '')}</span>
      <span class="${cls((item.level || '').includes('ERROR') ? -1 : (item.level || '').includes('WARN') ? 0 : 1)}">${esc(item.level || 'INFO')}</span>
      <span>${esc(item.msg || '')}</span>
    </div>
  `).join('');
  if (logPinnedToBottom){
    box.scrollTop = box.scrollHeight;
  }else{
    box.scrollTop = prevScrollTop;
  }
}

async function loadLogs(){
  try{
    const response = await fetch('/health/logs?lines=240&_=' + Date.now());
    renderLogs(await response.json());
  }catch{
    renderEmpty('log_lines', '日志读取失败');
  }
}

async function loadAll(forceClock=false){
  if (forceClock) document.getElementById('clock').textContent = new Date().toLocaleString();
  try{
    const [
      healthR, accountR, positionsR, ordersR, pnlR, reportR, report30R,
      strategyR, tradesR, candidatesR, signalsR, activityR
    ] = await Promise.all([
      fetch('/health'),
      fetch('/health/account'),
      fetch('/health/positions?_=' + Date.now()),
      fetch('/health/orders?_=' + Date.now()),
      fetch('/health/pnl'),
      fetch('/health/report'),
      fetch('/health/report/30d'),
      fetch('/health/strategy'),
      fetch('/health/trades'),
      fetch('/health/candidates'),
      fetch('/health/signals'),
      fetch('/health/activity')
    ]);

    const health = await healthR.json();
    const account = await accountR.json();
    const positions = await positionsR.json();
    const orders = await ordersR.json();
    const pnl = await pnlR.json();
    const report = await reportR.json();
    const report30 = await report30R.json();
    const strategy = await strategyR.json();
    const trades = await tradesR.json();
    const candidates = await candidatesR.json();
    const signals = await signalsR.json();
    const activity = await activityR.json();

    const statusText = health.websocket_connected ? '在线' : '离线';
    setText('kpi_status', statusText, `value ${health.websocket_connected ? 'good' : 'bad'}`);
    document.getElementById('kpi_status_hint').textContent = `Circuit ${health.circuit_breaker_tripped ? 'tripped' : 'ok'} / v${health.version || '--'}`;

    if (!account.error){
      setText('kpi_balance', plainMoney(account.total_balance || 0), 'value');
      document.getElementById('kpi_balance_hint').textContent = `可用 ${plainMoney(account.available_balance || 0)} / 浮盈 ${money(account.unrealized_pnl || 0)}`;
    }

    const posCount = num(positions.count || 0);
    let slCount = 0, tpCount = 0;
    (orders.by_symbol || []).forEach(item => {
      slCount += num(item.stop_orders || 0);
      tpCount += num(item.tp_orders || 0);
    });
    setText('kpi_positions', `${posCount} / SL ${slCount} / TP ${tpCount}`, `value ${posCount ? 'good' : 'muted'}`);
    document.getElementById('kpi_positions_hint').textContent = '分批止盈保持挂单，剩余仓位继续持有';

    const presets = strategy.enabled_presets || [];
    setText('kpi_presets', presets.length ? presets.join(' / ') : '--', `value ${presets.length ? 'good' : 'muted'}`);
    document.getElementById('kpi_presets_hint').textContent = `主预设 ${strategy.preset || '--'}`;

    const protectionMap = {};
    (orders.by_symbol || []).forEach(item => protectionMap[item.symbol] = item);
    if (Array.isArray(positions.positions) && positions.positions.length){
      document.getElementById('positions_body').innerHTML = positions.positions.map(pos => {
        const side = String(pos.side || '').toUpperCase();
        const entryReason = String(pos.entry_reason || '--').replace(/^preset:[^|]+\|/, '');
        const filledTiers = String(pos.tp_tiers_filled || '').trim() || '--';
        const protect = protectionMap[pos.symbol] || {};
        const sl = num(pos.sl_price || pos.stop_loss_price) > 0 ? price(pos.sl_price || pos.stop_loss_price) : '--';
        const tp = num(pos.tp_price || pos.take_profit_price) > 0 ? price(pos.tp_price || pos.take_profit_price) : '--';
        const protectText = `SL ${num(protect.stop_orders || 0)} / TP ${num(protect.tp_orders || 0)}`;
        return `<tr>
          <td class="symbol"><b>${esc(pos.symbol)}</b><span>${esc(pos.strategy_id || '--')} / ${holdLabel(pos.hold_seconds || 0)}</span></td>
          <td><span class="tag ${dirClass(side)}">${esc(side)}</span></td>
          <td class="symbol"><b>${esc(pos.strategy_preset || '--')}</b><span>${esc(pos.support_presets || '--')}</span></td>
          <td class="mono">开 ${price(pos.entry_price)} / 标 ${price(pos.mark_price)}</td>
          <td class="${cls(pos.unrealized_pnl || 0)}">${money(pos.unrealized_pnl || 0)}<div class="${cls(pos.roi_pct || 0)}">${pct(pos.roi_pct || 0)}</div></td>
          <td class="mono">已中 ${esc(filledTiers)}<div class="muted">TP3 锚点 ${esc(tp)}</div></td>
          <td>${esc(entryReason || '--')}</td>
          <td class="mono">${esc(protectText)}<div class="muted">SL ${esc(sl)}</div></td>
        </tr>`;
      }).join('');
    }else{
      document.getElementById('positions_body').innerHTML = '<tr><td colspan="8" class="empty">当前无持仓</td></tr>';
    }

    setText('perf_1d', money(pnl.net_pnl_1d || 0), `value ${cls(pnl.net_pnl_1d || 0)}`);
    document.getElementById('perf_1d_sub').textContent = `${pct(pnl.net_pnl_1d_pct || 0)} / 胜率 ${pct(pnl.win_rate_1d || 0)}`;
    setText('perf_7d', money(pnl.net_pnl_7d || 0), `value ${cls(pnl.net_pnl_7d || 0)}`);
    document.getElementById('perf_7d_sub').textContent = `${pct(pnl.net_pnl_7d_pct || 0)} / 胜率 ${pct(pnl.win_rate_7d || 0)}`;
    setText('perf_30d', money(pnl.net_pnl_30d || 0), `value ${cls(pnl.net_pnl_30d || 0)}`);
    document.getElementById('perf_30d_sub').textContent = `${pct(pnl.net_pnl_30d_pct || 0)} / 胜率 ${pct(pnl.win_rate_30d || 0)}`;
    setText('perf_all', money(pnl.net_pnl_total || 0), `value ${cls(pnl.net_pnl_total || 0)}`);
    document.getElementById('perf_all_sub').textContent = `${pct(pnl.net_pnl_total_pct || 0)} / 权益 ${plainMoney(pnl.total_equity || 0)}`;

    document.getElementById('trade_count_badge').textContent = `成交 ${num(report.total_trades || 0)} 笔`;
    document.getElementById('report_summary').innerHTML = [
      row('成交笔数', `${num(report.total_trades || 0)}（按一开一平算 1 笔）`),
      row('胜率', pct(report.win_rate || 0)),
      row('平均盈利 / 亏损', `${money(report.avg_win || 0)} / ${money(report.avg_loss || 0)}`),
      row('平均持仓', holdLabel(report.avg_hold_time_seconds || 0)),
      row('Profit Factor', report.profit_factor ?? '--'),
      row('最大回撤', pct(report.max_drawdown_pct || 0)),
      row('Sharpe', report.sharpe_ratio ?? '--'),
    ].join('');

    if (Array.isArray(report.trades) && report.trades.length){
      document.getElementById('recent_trades').innerHTML = report.trades.slice().reverse().slice(0, 14).map(item => {
        const chips = [
          `策略 ${item.strategy || '--'}`,
          `平仓原因 ${item.exit_reason || '--'}`,
          `TP ${Array.isArray(item.tp_tiers_hit) && item.tp_tiers_hit.length ? item.tp_tiers_hit.join('/') : '--'}`,
          `持仓 ${holdLabel(item.hold_seconds || 0)}`
        ];
        return feedItem(
          item.closed_at ? new Date(item.closed_at).toLocaleString() : '--',
          `<b>${esc(item.symbol)}</b> ${esc(item.side || '')} ${money(item.pnl || 0)}`,
          `开 ${price(item.entry_price)} / 平 ${price(item.exit_price)} / ${pct(item.pnl_pct || 0)}`,
          item.exit_reason || 'CLOSE',
          cls(item.pnl || 0) === 'good' ? 'long' : cls(item.pnl || 0) === 'bad' ? 'short' : 'hold',
          chips
        );
      }).join('');
    }else{
      renderEmpty('recent_trades', '暂无已完成交易');
    }

    const signalItems = [];
    (candidates.candidates || []).slice(0, 3).forEach(item => {
      signalItems.push(feedItem(
        '候选',
        `<b>${esc(item.symbol)}</b> 扫描 ${esc(item.scanner_score)}`,
        `24h ${pct(item.change_24h || 0)} / 置信 ${(num(item.confidence || 0) * 100).toFixed(0)}% / 综合 ${num(item.composite_score || 0).toFixed(1)}`,
        item.direction || 'HOLD',
        dirClass(item.direction),
        Object.entries(item.preset_scores || {}).map(([k, v]) => `${k}:${Math.round(num(v))}`)
      ));
    });
    (signals.signals || []).slice().reverse().slice(0, 4).forEach(item => {
      const chips = [];
      if (item.preset) chips.push(`主策略 ${item.preset}`);
      (item.supporting_presets || []).forEach(v => chips.push(`支持 ${v}`));
      if (item.opportunity_type) chips.push(`机会 ${item.opportunity_type}`);
      signalItems.push(feedItem(
        item.time ? new Date(item.time).toLocaleTimeString() : '信号',
        `<b>${esc(item.symbol)}</b> ${esc(item.action || '--')}`,
        esc(item.detail || '--'),
        item.preset || item.action || '--',
        dirClass(item.action),
        chips
      ));
    });
    document.getElementById('signals_mix').innerHTML = signalItems.length ? signalItems.join('') : '<div class="empty">暂无候选与信号</div>';

    if (Array.isArray(activity.items) && activity.items.length){
      document.getElementById('activity_feed').innerHTML = activity.items.slice(0, 20).map(item => {
        const chips = [];
        if (item.preset) chips.push(`预设 ${item.preset}`);
        if (item.strategy_id) chips.push(`ID ${item.strategy_id}`);
        return feedItem(
          item.time ? new Date(item.time).toLocaleString() : '--',
          esc(item.title || item.event_type || '--'),
          esc(item.detail || '--'),
          item.badge || item.event_type || '--',
          (item.event_type === 'signal_rejected' || item.event_type === 'protection_failed') ? 'warn' : item.event_type === 'position_closed' ? 'short' : 'hold',
          chips
        );
      }).join('');
    }else{
      renderEmpty('activity_feed', '暂无活动记录');
    }

    const strategyNames = Object.keys({ ...(strategy.preset_details || {}), ...(report.strategies || {}) });
    document.getElementById('strategy_cards').innerHTML = strategyNames.length
      ? strategyNames.map(name => strategyCard(name, report.strategies?.[name] || {}, strategy.preset_details?.[name] || {})).join('')
      : '<div class="empty">暂无策略拆分数据</div>';

    const daily = report30.daily_pnl || report.daily_pnl || [];
    if (daily.length){
      const maxAbs = Math.max(...daily.map(x => Math.abs(num(x.pnl))), 0.01);
      document.getElementById('daily_chart').innerHTML = daily.map(item => {
        const height = Math.max(12, Math.round(Math.abs(num(item.pnl)) / maxAbs * 220));
        return `<div class="bar ${num(item.pnl) >= 0 ? 'pos' : 'neg'}" style="height:${height}px" title="${esc(item.date)} ${money(item.pnl)}"></div>`;
      }).join('');
      document.getElementById('daily_axis').innerHTML = `<span>${esc(daily[0].date)}</span><span>${esc(daily[daily.length - 1].date)}</span>`;
      document.getElementById('daily_meta').innerHTML = [
        row('30日净盈亏', money(pnl.net_pnl_30d || 0)),
        row('累计净盈亏', money(pnl.net_pnl_total || 0)),
        row('报表生成', report.generated_at ? new Date(report.generated_at).toLocaleString() : '--')
      ].join('');
    }else{
      renderEmpty('daily_chart', '暂无 30 日净盈亏数据');
      document.getElementById('daily_axis').innerHTML = '';
      document.getElementById('daily_meta').innerHTML = '';
    }
  }catch{
    setText('kpi_status', '接口异常', 'value bad');
    document.getElementById('kpi_status_hint').textContent = '请检查 health 接口与日志';
  }
}

document.getElementById('log_lines').addEventListener('scroll', (event) => {
  const box = event.currentTarget;
  logPinnedToBottom = (box.scrollHeight - box.scrollTop - box.clientHeight) < 36;
});

loadAll(true);
loadLogs();
setInterval(() => loadAll(false), REFRESH_MS);
setInterval(loadLogs, 5000);
</script>
</body>
</html>"""


def add_dashboard_route(app: FastAPI) -> None:
    """Add dashboard routes to an existing FastAPI app."""

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return DASHBOARD_HTML


def create_dashboard_app() -> FastAPI:
    """Create a standalone FastAPI app serving the dashboard."""

    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    return app
