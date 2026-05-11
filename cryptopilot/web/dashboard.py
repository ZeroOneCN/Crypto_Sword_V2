"""Dashboard HTML for the trading control center."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>宙斯交易中枢 | CryptoPilot V2</title>
<style>
  :root{
    --bg:#0a0b0d;
    --panel:#13161a;
    --panel-2:#191d22;
    --panel-3:#20262d;
    --line:rgba(255,255,255,.08);
    --line-strong:rgba(255,255,255,.15);
    --text:#f3f5f7;
    --muted:#a2acb7;
    --dim:#6d7783;
    --accent:#d7b36a;
    --accent-soft:rgba(215,179,106,.16);
    --good:#55d38a;
    --good-soft:rgba(85,211,138,.16);
    --bad:#ff7061;
    --bad-soft:rgba(255,112,97,.16);
    --warn:#f1c75a;
    --warn-soft:rgba(241,199,90,.16);
    --blue:#79b7ff;
    --blue-soft:rgba(121,183,255,.16);
    --radius-lg:22px;
    --radius-md:16px;
    --radius-sm:12px;
    --shadow:0 16px 40px rgba(0,0,0,.28);
  }
  *{box-sizing:border-box}
  html,body{
    margin:0;padding:0;min-height:100%;
    background:
      radial-gradient(circle at top left, rgba(215,179,106,.08), transparent 20%),
      radial-gradient(circle at top right, rgba(121,183,255,.06), transparent 20%),
      linear-gradient(180deg, #090a0c 0%, #0d1014 100%);
    color:var(--text);
    font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  }
  body{line-height:1.45}
  .shell{max-width:1800px;margin:0 auto;padding:16px 18px 28px}
  .topbar{
    display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:8px 2px 16px;
  }
  .title{
    margin:0;
    font-size:28px;
    letter-spacing:-.03em;
    font-weight:700;
  }
  .top-actions{display:flex;align-items:center;gap:10px}
  button{
    border:1px solid var(--line);
    border-radius:999px;
    padding:9px 14px;
    background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.03));
    color:var(--text);
    font:inherit;
    cursor:pointer;
  }
  button:hover{border-color:var(--line-strong)}
  .status-strip{
    display:grid;
    grid-template-columns:repeat(8, minmax(0, 1fr));
    gap:14px;
    margin-bottom:16px;
  }
  .status-card,.panel,.metric-box,.subpanel,.strategy-card,.feed-item{
    border:1px solid var(--line);
    background:linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.018));
    box-shadow:var(--shadow);
  }
  .status-card{
    min-height:108px;
    border-radius:18px;
    padding:14px 15px;
    display:flex;
    flex-direction:column;
    justify-content:space-between;
  }
  .label{
    font-size:11px;
    letter-spacing:.14em;
    text-transform:uppercase;
    color:var(--muted);
  }
  .value{
    margin-top:8px;
    font-size:25px;
    font-weight:700;
    letter-spacing:-.04em;
  }
  .hint{
    margin-top:6px;
    font-size:12px;
    color:var(--dim);
  }
  .badge{
    display:inline-flex;align-items:center;gap:8px;
    padding:7px 11px;border-radius:999px;
    font-size:12px;border:1px solid var(--line);
    background:rgba(255,255,255,.04);
  }
  .badge.good{color:var(--good);background:var(--good-soft)}
  .badge.bad{color:var(--bad);background:var(--bad-soft)}
  .badge.warn{color:var(--warn);background:var(--warn-soft)}
  .badge.neutral{color:var(--accent);background:var(--accent-soft)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--good)}
  .main-grid{
    display:grid;
    grid-template-columns:repeat(3, minmax(0, 1fr));
    gap:16px;
    align-items:stretch;
  }
  .panel{
    border-radius:var(--radius-lg);
    padding:18px;
    min-height:460px;
    display:flex;
    flex-direction:column;
    overflow:hidden;
  }
  .panel-wide{grid-column:1 / -1;min-height:360px}
  .panel-head{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:12px;
    margin-bottom:14px;
  }
  .panel-title{
    margin:0;
    font-size:22px;
    font-weight:700;
    letter-spacing:-.03em;
  }
  .panel-sub{
    margin-top:5px;
    color:var(--muted);
    font-size:13px;
  }
  .panel-body{
    flex:1;
    min-height:0;
    display:flex;
    flex-direction:column;
    gap:12px;
  }
  .metric-grid{
    display:grid;
    grid-template-columns:repeat(2, minmax(0, 1fr));
    gap:12px;
  }
  .metric-box{
    border-radius:16px;
    padding:14px 15px;
    min-height:110px;
  }
  .metric-box .value{font-size:22px}
  .subgrid{
    display:grid;
    grid-template-columns:repeat(2, minmax(0, 1fr));
    gap:12px;
    flex:1;
    min-height:0;
  }
  .subpanel{
    border-radius:16px;
    padding:14px 15px;
    display:flex;
    flex-direction:column;
    min-height:0;
  }
  .subpanel h3{
    margin:0 0 10px;
    font-size:13px;
    color:var(--muted);
    letter-spacing:.1em;
    text-transform:uppercase;
  }
  .table-wrap{
    flex:1;
    min-height:0;
    overflow:auto;
    border-radius:16px;
    border:1px solid rgba(255,255,255,.06);
    background:rgba(0,0,0,.14);
  }
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{
    padding:11px 12px;
    border-bottom:1px solid rgba(255,255,255,.06);
    text-align:left;
    white-space:nowrap;
  }
  th{
    position:sticky;top:0;z-index:1;
    background:rgba(22,26,31,.96);
    color:var(--muted);
    font-size:11px;
    letter-spacing:.14em;
    text-transform:uppercase;
  }
  .symbol-cell b{display:block;font-size:14px}
  .symbol-cell span{display:block;margin-top:4px;color:var(--dim);font-size:11px}
  .tag{
    display:inline-flex;align-items:center;
    padding:5px 9px;border-radius:999px;
    font-size:11px;font-weight:700;letter-spacing:.08em;
  }
  .tag.long{background:var(--good-soft);color:var(--good)}
  .tag.short{background:var(--bad-soft);color:var(--bad)}
  .tag.hold{background:var(--blue-soft);color:var(--blue)}
  .mono{font-family:"Cascadia Mono","SFMono-Regular",Consolas,monospace}
  .good{color:var(--good)}
  .bad{color:var(--bad)}
  .warn{color:var(--warn)}
  .muted{color:var(--muted)}
  .dim{color:var(--dim)}
  .feed-list,.log-list,.strategy-list,.stat-list{
    display:flex;
    flex-direction:column;
    gap:10px;
    min-height:0;
    overflow:auto;
  }
  .feed-item{
    border-radius:15px;
    padding:12px 13px;
    display:grid;
    grid-template-columns:auto minmax(0,1fr) auto;
    gap:10px;
    align-items:start;
  }
  .feed-time{font-size:12px;color:var(--dim);min-width:70px}
  .feed-main{min-width:0}
  .feed-title{
    font-size:14px;font-weight:600;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  }
  .feed-detail{
    font-size:12px;color:var(--muted);
    margin-top:4px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  }
  .feed-stack{
    display:flex;flex-wrap:wrap;gap:6px;margin-top:7px;
  }
  .chip{
    display:inline-flex;align-items:center;
    padding:4px 8px;border-radius:999px;
    background:rgba(255,255,255,.045);
    border:1px solid rgba(255,255,255,.06);
    font-size:11px;color:var(--muted);
  }
  .stat-row{
    display:flex;justify-content:space-between;gap:12px;align-items:flex-start;
    padding:0 0 10px;border-bottom:1px solid rgba(255,255,255,.06);
    font-size:13px;
  }
  .stat-row:last-child{border-bottom:none;padding-bottom:0}
  .stat-key{color:var(--muted)}
  .stat-val{text-align:right;font-weight:600}
  .strategy-card{
    border-radius:16px;
    padding:14px 15px;
  }
  .strategy-top{
    display:flex;justify-content:space-between;align-items:center;gap:10px;
  }
  .strategy-name{font-size:15px;font-weight:700}
  .strategy-meta{font-size:11px;color:var(--muted)}
  .strategy-metrics{
    display:grid;
    grid-template-columns:repeat(2, minmax(0,1fr));
    gap:10px;
    margin-top:12px;
  }
  .mini{
    padding:10px 11px;border-radius:14px;background:rgba(255,255,255,.03);
  }
  .mini .label{font-size:10px}
  .mini .value{font-size:17px;margin-top:6px}
  .chart-wrap{
    flex:1;
    min-height:0;
    display:flex;
    flex-direction:column;
    gap:12px;
  }
  .trend{
    flex:1;
    min-height:180px;
    display:flex;
    align-items:flex-end;
    gap:4px;
    padding:14px 10px 0;
    border-radius:16px;
    border:1px solid rgba(255,255,255,.06);
    background:rgba(0,0,0,.12);
  }
  .bar{flex:1 1 0;min-width:8px;border-radius:999px 999px 5px 5px;opacity:.95}
  .bar.pos{background:linear-gradient(180deg, rgba(85,211,138,.95), rgba(85,211,138,.35))}
  .bar.neg{background:linear-gradient(180deg, rgba(255,112,97,.95), rgba(255,112,97,.35))}
  .trend-axis{
    display:flex;justify-content:space-between;
    font-size:11px;color:var(--dim);
    padding:0 4px;
  }
  .log-box{
    flex:1;
    min-height:0;
    overflow:auto;
    border-radius:16px;
    border:1px solid rgba(255,255,255,.06);
    background:#0f1216;
    padding:12px;
  }
  .log-line{
    display:grid;
    grid-template-columns:68px 54px minmax(0,1fr);
    gap:10px;
    padding:4px 0;
    font-family:"Cascadia Mono","SFMono-Regular",Consolas,monospace;
    font-size:12px;
  }
  .empty{
    padding:18px;
    text-align:center;
    color:var(--muted);
  }
  @media(max-width:1500px){
    .status-strip{grid-template-columns:repeat(4, minmax(0, 1fr))}
  }
  @media(max-width:1220px){
    .main-grid{grid-template-columns:repeat(2, minmax(0,1fr))}
    .panel-wide{grid-column:1 / -1}
  }
  @media(max-width:860px){
    .shell{padding:14px}
    .status-strip{grid-template-columns:repeat(2, minmax(0, 1fr))}
    .main-grid{grid-template-columns:1fr}
    .subgrid,.metric-grid,.strategy-metrics{grid-template-columns:1fr}
    .feed-item{grid-template-columns:1fr}
    .feed-time{min-width:0}
  }
</style>
</head>
<body>
<div class="shell">
  <div class="topbar">
    <h1 class="title">宙斯交易中枢</h1>
    <div class="top-actions">
      <span class="badge neutral mono" id="clock">--</span>
      <button onclick="loadAll()">刷新</button>
    </div>
  </div>

  <section class="status-strip">
    <div class="status-card">
      <div class="label">系统状态</div>
      <div class="value" id="status_text">--</div>
      <div class="hint" id="status_hint">--</div>
    </div>
    <div class="status-card">
      <div class="label">总权益</div>
      <div class="value" id="kpi_balance">--</div>
      <div class="hint">官方账户口径</div>
    </div>
    <div class="status-card">
      <div class="label">可用余额</div>
      <div class="value" id="kpi_avail">--</div>
      <div class="hint">可继续开仓资金</div>
    </div>
    <div class="status-card">
      <div class="label">未实现盈亏</div>
      <div class="value" id="kpi_upnl">--</div>
      <div class="hint">官方持仓浮盈浮亏</div>
    </div>
    <div class="status-card">
      <div class="label">当前持仓</div>
      <div class="value" id="kpi_positions">--</div>
      <div class="hint">官方持仓 + 本地归因</div>
    </div>
    <div class="status-card">
      <div class="label">保护挂单</div>
      <div class="value" id="kpi_orders">--</div>
      <div class="hint" id="kpi_orders_hint">--</div>
    </div>
    <div class="status-card">
      <div class="label">启用策略</div>
      <div class="value" id="kpi_presets">--</div>
      <div class="hint">运行中的多策略预设</div>
    </div>
    <div class="status-card">
      <div class="label">保证金模式</div>
      <div class="value" id="kpi_margin">--</div>
      <div class="hint" id="kpi_margin_hint">--</div>
    </div>
  </section>

  <section class="main-grid">
    <section class="panel panel-wide">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">当前持仓</h2>
          <div class="panel-sub">优先展示交易所实时持仓、实时标记价、保护单覆盖和本地策略归因。</div>
        </div>
        <div class="badge good" id="positions_source">官方实时</div>
      </div>
      <div class="panel-body">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>币种</th>
                <th>方向</th>
                <th>策略</th>
                <th>数量</th>
                <th>杠杆</th>
                <th>开仓价</th>
                <th>标记价</th>
                <th>未实现</th>
                <th>ROI</th>
                <th>持仓时长</th>
                <th>止损</th>
                <th>止盈</th>
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
          <h2 class="panel-title">交易绩效</h2>
          <div class="panel-sub">上层用 Binance 盈亏口径，下层保留本地报表用于策略复盘和持仓质量判断。</div>
        </div>
        <div class="badge neutral" id="perf_source">官方 + 本地归因</div>
      </div>
      <div class="panel-body">
        <div class="metric-grid">
          <div class="metric-box"><div class="label">今日净盈亏</div><div class="value" id="perf_1d">--</div><div class="hint" id="perf_1d_sub">--</div></div>
          <div class="metric-box"><div class="label">7日净盈亏</div><div class="value" id="perf_7d">--</div><div class="hint" id="perf_7d_sub">--</div></div>
          <div class="metric-box"><div class="label">30日净盈亏</div><div class="value" id="perf_30d">--</div><div class="hint" id="perf_30d_sub">--</div></div>
          <div class="metric-box"><div class="label">累计净盈亏</div><div class="value" id="perf_all">--</div><div class="hint" id="perf_all_sub">--</div></div>
        </div>
        <div class="subgrid">
          <div class="subpanel">
            <h3>官方统计</h3>
            <div class="stat-list" id="perf_official"></div>
          </div>
          <div class="subpanel">
            <h3>本地复盘</h3>
            <div class="stat-list" id="perf_local"></div>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">候选与信号</h2>
          <div class="panel-sub">候选池保留多策略评分，信号区直接看主策略、支持策略和拒单原因。</div>
        </div>
        <div class="badge neutral" id="signals_source">本地策略链路</div>
      </div>
      <div class="panel-body">
        <div class="subgrid">
          <div class="subpanel">
            <h3>候选池</h3>
            <div class="feed-list" id="candidates_body"></div>
          </div>
          <div class="subpanel">
            <h3>信号日志</h3>
            <div class="feed-list" id="signals_body"></div>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">近期成交</h2>
          <div class="panel-sub">优先展示 Binance userTrades，能匹配到本地订单时再补策略归因。</div>
        </div>
        <div class="badge good" id="trades_source">官方成交</div>
      </div>
      <div class="panel-body">
        <div class="feed-list" id="trades_body"></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">策略拆分</h2>
          <div class="panel-sub">这里保留本地归因统计，用来判断三策略谁在赚钱、谁在拖累组合。</div>
        </div>
        <div class="badge neutral" id="strategy_source">本地策略归因</div>
      </div>
      <div class="panel-body">
        <div class="strategy-list" id="strategy_cards"></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">30天净盈亏轨迹</h2>
          <div class="panel-sub">按日展示本地复盘净盈亏，便于和运行日志同屏排查异常交易日。</div>
        </div>
        <div class="badge neutral">本地报表</div>
      </div>
      <div class="panel-body chart-wrap">
        <div class="trend" id="daily_pnl_chart"></div>
        <div class="trend-axis" id="daily_pnl_axis"></div>
        <div class="subpanel" style="padding:12px 14px">
          <div class="stat-list" id="trend_meta"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 class="panel-title">运行日志</h2>
          <div class="panel-sub">固定读取最近 200 行，重点观察挂单、同步、拒单、止损和策略竞争异常。</div>
        </div>
        <div class="badge neutral" id="logs_source">最近 200 行</div>
      </div>
      <div class="panel-body">
        <div class="log-box" id="log_lines"></div>
      </div>
    </section>
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
const marginLabel = t => String(t || '').toLowerCase() === 'isolated' ? '逐仓' : '全仓';
const tagDir = dir => dir === 'LONG' || dir === 'BUY' ? 'long' : ((dir === 'SHORT' || dir === 'SELL') ? 'short' : 'hold');

function holdLabel(sec){
  const total = Math.max(0, Math.floor(num(sec)));
  if(!total) return '--';
  if(total < 60) return total + 's';
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if(mins < 60) return `${mins}m${String(secs).padStart(2, '0')}s`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  if(hours < 24) return `${hours}h${String(remMins).padStart(2, '0')}m`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return `${days}d${String(remHours).padStart(2, '0')}h`;
}

function fmtPct(v){
  if(v == null || Number.isNaN(Number(v))) return '--';
  const n = Number(v);
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function fmtRate(v){
  if(v == null || Number.isNaN(Number(v))) return '--';
  return `${Number(v).toFixed(1)}%`;
}

function statRow(label, value){
  return `<div class="stat-row"><span class="stat-key">${label}</span><span class="stat-val">${value}</span></div>`;
}

function feedItem(time, title, detail, sideClass='hold', right='', chips=[]){
  const chipHtml = chips.length ? `<div class="feed-stack">${chips.map(t => `<span class="chip">${esc(t)}</span>`).join('')}</div>` : '';
  return `<div class="feed-item">
    <div class="feed-time">${esc(time)}</div>
    <div class="feed-main">
      <div class="feed-title">${title}</div>
      <div class="feed-detail">${detail}</div>
      ${chipHtml}
    </div>
    <div><span class="tag ${sideClass}">${esc(right)}</span></div>
  </div>`;
}

function strategyCard(name, report, runtime){
  const pnlClass = cls(report.pnl || 0);
  const pf = report.profit_factor == null ? '--' : report.profit_factor;
  const exitBreakdown = Object.entries(report.exit_reason_breakdown || {}).slice(0, 3)
    .map(([k, v]) => `${k}:${v}`).join(' / ') || '--';
  return `<div class="strategy-card">
    <div class="strategy-top">
      <div>
        <div class="strategy-name">${esc(name)}</div>
        <div class="strategy-meta">风险 ${fmtPct(runtime.risk_budget)} / 并发 ${runtime.max_concurrent ?? '--'} / SL ${runtime.stop_loss_pct ?? '--'}%</div>
      </div>
      <span class="badge neutral">${esc(report.avg_hold_time || holdLabel(report.avg_hold_time_seconds || 0) || '--')}</span>
    </div>
    <div class="strategy-metrics">
      <div class="mini"><div class="label">净盈亏</div><div class="value ${pnlClass}">${money(report.pnl || 0)}</div></div>
      <div class="mini"><div class="label">胜率</div><div class="value">${fmtRate(report.win_rate)}</div></div>
      <div class="mini"><div class="label">交易数</div><div class="value">${num(report.trades || 0)}</div></div>
      <div class="mini"><div class="label">Profit Factor</div><div class="value">${esc(pf)}</div></div>
    </div>
    <div class="hint" style="margin-top:10px">TP ${num(report.tp_hits?.TP1 || 0)} / ${num(report.tp_hits?.TP2 || 0)} / ${num(report.tp_hits?.TP3 || 0)} | ${esc(exitBreakdown)}</div>
  </div>`;
}

function renderEmpty(id, text){
  document.getElementById(id).innerHTML = `<div class="empty">${esc(text)}</div>`;
}

async function loadAll(){
  document.getElementById('clock').textContent = new Date().toLocaleString();

  try{
    const [
      acctR, posR, healthR, circuitR, pnlR, ordersR, candidatesR,
      strategyR, signalsR, tradesR, report30R, volumeR, reportR
    ] = await Promise.all([
      fetch('/health/account'),
      fetch('/health/positions?_=' + Date.now()),
      fetch('/health'),
      fetch('/health/circuit'),
      fetch('/health/pnl'),
      fetch('/health/orders?_=' + Date.now()),
      fetch('/health/candidates'),
      fetch('/health/strategy'),
      fetch('/health/signals'),
      fetch('/health/trades'),
      fetch('/health/report/30d'),
      fetch('/health/volume'),
      fetch('/health/report')
    ]);

    const acct = await acctR.json();
    const pos = await posR.json();
    const health = await healthR.json();
    const circuit = await circuitR.json();
    const pnl = await pnlR.json();
    const orders = await ordersR.json();
    const candidates = await candidatesR.json();
    const strategy = await strategyR.json();
    const signals = await signalsR.json();
    const trades = await tradesR.json();
    const report30 = await report30R.json();
    const volume = await volumeR.json();
    const report = await reportR.json();

    const websocketOk = !!health.websocket_connected;
    const tripped = !!circuit.tripped;
    const enabledPresets = strategy.enabled_presets || (strategy.preset ? [strategy.preset] : []);
    const presetDetails = strategy.preset_details || {};

    document.getElementById('status_text').innerHTML = `${websocketOk ? '在线' : '离线'}${tripped ? ' / 熔断' : ''}`;
    document.getElementById('status_text').className = `value ${tripped ? 'bad' : websocketOk ? 'good' : 'warn'}`;
    document.getElementById('status_hint').textContent = `WS ${websocketOk ? '已连接' : '异常'} | v${health.version || '--'}`;

    if(!acct.error){
      document.getElementById('kpi_balance').textContent = plainMoney(acct.total_balance);
      document.getElementById('kpi_avail').textContent = plainMoney(acct.available_balance);
      document.getElementById('kpi_upnl').textContent = money(acct.unrealized_pnl);
      document.getElementById('kpi_upnl').className = `value ${cls(acct.unrealized_pnl)}`;
      document.getElementById('kpi_margin').textContent = marginLabel(acct.margin_type || 'cross');
      document.getElementById('kpi_margin_hint').textContent = acct.margin_display || '--';
    }

    const openPositions = num(pos.count || 0);
    document.getElementById('kpi_positions').textContent = String(openPositions);
    document.getElementById('kpi_positions').className = `value ${openPositions > 0 ? 'good' : 'muted'}`;

    let slCount = 0;
    let tpCount = 0;
    (orders.by_symbol || []).forEach(item => {
      slCount += num(item.stop_orders || 0);
      tpCount += num(item.tp_orders || 0);
    });
    document.getElementById('kpi_orders').textContent = `SL ${slCount} / TP ${tpCount}`;
    document.getElementById('kpi_orders').className = `value ${(slCount + tpCount) > 0 ? 'good' : 'bad'}`;
    document.getElementById('kpi_orders_hint').textContent = `官方挂单 ${num(orders.total || 0)} 个`;

    document.getElementById('kpi_presets').textContent = enabledPresets.length ? enabledPresets.join(' / ') : '--';
    document.getElementById('kpi_presets').className = `value ${enabledPresets.length ? 'good' : 'muted'}`;

    const positionsBody = document.getElementById('positions_body');
    const protectionMap = {};
    (orders.by_symbol || []).forEach(item => protectionMap[item.symbol] = item);
    if(!pos.error && Array.isArray(pos.positions) && pos.positions.length){
      positionsBody.innerHTML = pos.positions.map(item => {
        const side = String(item.side || '').toUpperCase();
        const strategyName = item.strategy_preset || item.strategy_id || item.entry_reason || '--';
        const support = item.support_presets ? `<span>${esc(item.support_presets)}</span>` : '';
        const protection = protectionMap[item.symbol] || {};
        const slLabel = num(item.sl_price || item.stop_loss_price) > 0 ? price(item.sl_price || item.stop_loss_price) : '--';
        const tpLabel = num(item.tp_price || item.take_profit_price) > 0 ? price(item.tp_price || item.take_profit_price) : '--';
        const protectionLabel = (num(protection.stop_orders || 0) + num(protection.tp_orders || 0)) > 0
          ? `SL ${num(protection.stop_orders || 0)} / TP ${num(protection.tp_orders || 0)}`
          : '缺失';
        return `<tr>
          <td class="symbol-cell"><b>${esc(item.symbol)}</b><span>${marginLabel(item.margin_type || 'cross')} / 名义 ${plainMoney(item.notional || 0)}</span></td>
          <td><span class="tag ${tagDir(side)}">${esc(side)}</span></td>
          <td class="symbol-cell"><b>${esc(strategyName)}</b>${support}</td>
          <td class="mono">${fmt.format(num(item.qty))}</td>
          <td>${num(item.leverage || 1)}x</td>
          <td class="mono">${price(item.entry_price)}</td>
          <td class="mono">${price(item.mark_price)}</td>
          <td class="${cls(item.unrealized_pnl)}">${money(item.unrealized_pnl)}</td>
          <td class="${cls(item.roi_pct)}">${pct(item.roi_pct)}</td>
          <td>${holdLabel(item.hold_seconds)}<div class="dim">${item.opened_at ? esc(new Date(item.opened_at).toLocaleString()) : '--'}</div></td>
          <td class="mono">${esc(slLabel)}</td>
          <td class="mono">${esc(tpLabel)}</td>
          <td class="${protectionLabel === '缺失' ? 'bad' : 'good'}">${esc(protectionLabel)}</td>
        </tr>`;
      }).join('');
    }else{
      positionsBody.innerHTML = '<tr><td colspan="13" class="empty">当前无持仓</td></tr>';
    }

    document.getElementById('perf_1d').textContent = money(pnl.net_pnl_1d || 0);
    document.getElementById('perf_1d').className = `value ${cls(pnl.net_pnl_1d || 0)}`;
    document.getElementById('perf_1d_sub').textContent = `${fmtPct(pnl.net_pnl_1d_pct)} / 胜率 ${fmtRate(pnl.win_rate_1d)}`;
    document.getElementById('perf_7d').textContent = money(pnl.net_pnl_7d || 0);
    document.getElementById('perf_7d').className = `value ${cls(pnl.net_pnl_7d || 0)}`;
    document.getElementById('perf_7d_sub').textContent = `${fmtPct(pnl.net_pnl_7d_pct)} / 胜率 ${fmtRate(pnl.win_rate_7d)}`;
    document.getElementById('perf_30d').textContent = money(pnl.net_pnl_30d || 0);
    document.getElementById('perf_30d').className = `value ${cls(pnl.net_pnl_30d || 0)}`;
    document.getElementById('perf_30d_sub').textContent = `${fmtPct(pnl.net_pnl_30d_pct)} / 胜率 ${fmtRate(pnl.win_rate_30d)}`;
    document.getElementById('perf_all').textContent = money(pnl.net_pnl_total || 0);
    document.getElementById('perf_all').className = `value ${cls(pnl.net_pnl_total || 0)}`;
    document.getElementById('perf_all_sub').textContent = `${fmtPct(pnl.net_pnl_total_pct)} / 权益 ${plainMoney(pnl.total_equity || 0)}`;

    document.getElementById('perf_official').innerHTML = [
      statRow('今日成交', `${num(pnl.trade_count_1d || 0)} 笔 / 胜率 ${fmtRate(pnl.win_rate_1d)}`),
      statRow('7日成交', `${num(pnl.trade_count_7d || 0)} 笔 / 胜率 ${fmtRate(pnl.win_rate_7d)}`),
      statRow('30日成交', `${num(pnl.trade_count_30d || 0)} 笔 / 胜率 ${fmtRate(pnl.win_rate_30d)}`),
      statRow('交易币种', `${num(pnl.symbols_traded || 0)} 个`),
      statRow('7日手续费', plainMoney(pnl.commission_7d || 0)),
      statRow('7日资金费', plainMoney(pnl.funding_7d || 0)),
      statRow('今日成交额', `${plainMoney(volume.volume_1d || 0)} / ${num(volume.trades_1d || 0)} 笔`)
    ].join('');

    document.getElementById('perf_local').innerHTML = [
      statRow('累计交易', `${num(report.total_trades || 0)} 笔`),
      statRow('本地胜率', fmtRate(report.win_rate)),
      statRow('平均持仓', holdLabel(report.avg_hold_time_seconds || 0)),
      statRow('平均盈利 / 亏损', `${money(report.avg_win || 0)} / ${money(report.avg_loss || 0)}`),
      statRow('Profit Factor', report.profit_factor == null ? '--' : String(report.profit_factor)),
      statRow('最大回撤', fmtPct(report.max_drawdown_pct)),
      statRow('Sharpe', report.sharpe_ratio == null ? '--' : String(report.sharpe_ratio))
    ].join('');

    if(!candidates.error && Array.isArray(candidates.candidates) && candidates.candidates.length){
      document.getElementById('candidates_body').innerHTML = candidates.candidates.slice(0, 8).map(item => {
        const scores = Object.entries(item.preset_scores || {}).map(([k, v]) => `${k}:${Math.round(num(v))}`);
        return feedItem(
          price(item.price),
          `<b>${esc(item.symbol)}</b> / 扫描 ${esc(item.scanner_score)}`,
          `24h ${pct(item.change_24h || 0)} / 置信 ${(num(item.confidence || 0) * 100).toFixed(0)}% / 综合 ${Math.round(num(item.composite_score || item.total_score || item.score || 0))}`,
          tagDir(item.direction || 'HOLD'),
          item.direction || 'HOLD',
          scores
        );
      }).join('');
    }else{
      renderEmpty('candidates_body', '暂无候选池数据');
    }

    if(!signals.error && Array.isArray(signals.signals) && signals.signals.length){
      document.getElementById('signals_body').innerHTML = signals.signals.slice().reverse().slice(0, 8).map(item => {
        const action = item.action || 'HOLD';
        const chips = [];
        if(item.preset) chips.push(`主策略 ${item.preset}`);
        if((item.supporting_presets || []).length) chips.push(`支持 ${item.supporting_presets.join(',')}`);
        if(item.opportunity_type) chips.push(`机会 ${item.opportunity_type}`);
        return feedItem(
          item.time ? new Date(item.time).toLocaleTimeString() : '--',
          `<b>${esc(item.symbol)}</b> / ${esc(action)} / 评分 ${esc(item.score ?? '--')}`,
          esc(item.detail || '-'),
          action.includes('SHORT') ? 'short' : action.includes('LONG') ? 'long' : 'hold',
          item.preset || action,
          chips
        );
      }).join('');
    }else{
      renderEmpty('signals_body', '暂无信号');
    }

    const tradeSource = trades.source || 'database';
    document.getElementById('trades_source').className = `badge ${tradeSource === 'exchange' ? 'good' : 'warn'}`;
    document.getElementById('trades_source').textContent = tradeSource === 'exchange' ? '官方成交' : '本地成交';
    if(!trades.error && Array.isArray(trades.trades) && trades.trades.length){
      document.getElementById('trades_body').innerHTML = trades.trades.slice(0, 12).map(item => {
        const side = (item.side || '').toUpperCase();
        const chips = [];
        if(item.preset) chips.push(`策略 ${item.preset}`);
        if(item.type) chips.push(`类型 ${item.type}`);
        if(num(item.realized_pnl) !== 0) chips.push(`已实现 ${money(item.realized_pnl)}`);
        chips.push(item.source === 'exchange' ? 'Binance userTrades' : '本地 fills');
        return feedItem(
          item.filled_at ? new Date(item.filled_at).toLocaleString() : '--',
          `<b>${esc(item.symbol)}</b> / ${esc(side)} @ ${price(item.price)}`,
          `数量 ${fmt.format(num(item.qty))} / 手续费 ${num(item.commission).toFixed(6)} ${esc(item.commission_asset || '')}`,
          tagDir(side),
          item.preset || side,
          chips
        );
      }).join('');
    }else{
      renderEmpty('trades_body', '暂无成交记录');
    }

    const strategies = report.strategies || {};
    const strategyNames = Object.keys({...presetDetails, ...strategies});
    if(strategyNames.length){
      document.getElementById('strategy_cards').innerHTML = strategyNames.map(name => {
        return strategyCard(name, strategies[name] || {}, presetDetails[name] || {});
      }).join('');
    }else{
      renderEmpty('strategy_cards', '暂无策略拆分数据');
    }

    const daily = report30.daily_pnl || report.daily_pnl || [];
    if(daily.length){
      const maxAbs = Math.max(...daily.map(item => Math.abs(num(item.pnl))), 0.01);
      document.getElementById('daily_pnl_chart').innerHTML = daily.map(item => {
        const height = Math.max(12, Math.round(Math.abs(num(item.pnl)) / maxAbs * 220));
        return `<div class="bar ${num(item.pnl) >= 0 ? 'pos' : 'neg'}" style="height:${height}px" title="${esc(item.date)} ${money(item.pnl)}"></div>`;
      }).join('');
      document.getElementById('daily_pnl_axis').innerHTML = `<span>${esc(daily[0].date)}</span><span>${esc(daily[daily.length - 1].date)}</span>`;
    }else{
      document.getElementById('daily_pnl_chart').innerHTML = '<div class="empty" style="width:100%">暂无 30 天净盈亏数据</div>';
      document.getElementById('daily_pnl_axis').innerHTML = '';
    }

    document.getElementById('trend_meta').innerHTML = [
      statRow('30日净盈亏', money(pnl.net_pnl_30d || 0)),
      statRow('累计净盈亏', money(pnl.net_pnl_total || 0)),
      statRow('复盘生成时间', report.generated_at ? esc(new Date(report.generated_at).toLocaleString()) : '--')
    ].join('');
  }catch(error){
    document.getElementById('status_text').textContent = '连接异常';
    document.getElementById('status_text').className = 'value bad';
    document.getElementById('status_hint').textContent = '接口拉取失败';
  }
}

async function loadLogs(){
  try{
    const response = await fetch('/health/logs?lines=200');
    const data = await response.json();
    if(!data.error && Array.isArray(data.lines) && data.lines.length){
      document.getElementById('logs_source').textContent = `${data.file || 'logs'} / ${data.lines.length} lines`;
      document.getElementById('log_lines').innerHTML = data.lines.map(item => `
        <div class="log-line">
          <span class="dim">${esc(item.time || '')}</span>
          <span class="${esc(String(item.level || 'INFO').toLowerCase())}">${esc(item.level || 'INFO')}</span>
          <span>${esc(item.msg || '')}</span>
        </div>
      `).join('');
    }else{
      renderEmpty('log_lines', '暂无日志');
    }
  }catch(error){
    renderEmpty('log_lines', '日志读取失败');
  }
}

loadAll();
loadLogs();
setInterval(loadAll, REFRESH_MS);
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
