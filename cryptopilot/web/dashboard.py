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
    --bg:#0a0a0a;
    --bg-alt:#131313;
    --panel:#151515;
    --panel-soft:#1b1b1b;
    --line:rgba(255,255,255,.09);
    --line-strong:rgba(255,255,255,.16);
    --text:#f3f3ef;
    --muted:#a7a7a0;
    --dim:#6f6f68;
    --accent:#d6b36f;
    --accent-soft:rgba(214,179,111,.14);
    --good:#56d37d;
    --good-soft:rgba(86,211,125,.14);
    --bad:#ff6a5f;
    --bad-soft:rgba(255,106,95,.14);
    --warn:#ffca57;
    --warn-soft:rgba(255,202,87,.14);
    --blue:#79b8ff;
    --radius-xl:28px;
    --radius-lg:22px;
    --radius-md:16px;
    --radius-sm:12px;
    --shadow:0 18px 60px rgba(0,0,0,.34);
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:
    radial-gradient(circle at top left, rgba(214,179,111,.12), transparent 28%),
    radial-gradient(circle at top right, rgba(121,184,255,.08), transparent 24%),
    linear-gradient(180deg, #090909 0%, #0c0c0c 52%, #111111 100%);
    color:var(--text);
    font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  }
  body{min-height:100vh;line-height:1.5}
  .shell{width:100%;max-width:none;margin:0;padding:12px 8px 40px}
  .hero{
    position:sticky;top:0;z-index:9;margin-bottom:20px;
    background:rgba(10,10,10,.78);backdrop-filter:blur(18px) saturate(130%);
    border:1px solid var(--line);border-radius:var(--radius-xl);
    box-shadow:var(--shadow);
  }
  .hero-inner{
    display:grid;grid-template-columns:minmax(0,1.8fr) minmax(340px,.9fr);
    gap:20px;padding:22px 24px;
  }
  .eyebrow{color:var(--accent);font-size:12px;letter-spacing:.22em;text-transform:uppercase}
  h1{
    margin:10px 0 0;font-size:40px;line-height:1.02;font-weight:700;
    letter-spacing:-.04em;
  }
  .hero-sub{margin-top:10px;color:var(--muted);max-width:760px;font-size:14px}
  .hero-meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
  .pill{
    display:inline-flex;align-items:center;gap:8px;
    padding:9px 14px;border:1px solid var(--line);
    background:rgba(255,255,255,.03);border-radius:999px;
    color:var(--text);font-size:13px
  }
  .dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:var(--good)}
  .hero-kpis{
    display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;
  }
  .hero-kpi,.metric-card,.panel,.subpanel{
    border:1px solid var(--line);background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015));
  }
  .hero-kpi{
    border-radius:20px;padding:16px 18px;min-height:106px;
  }
  .label{
    color:var(--muted);font-size:11px;letter-spacing:.15em;text-transform:uppercase
  }
  .value{
    margin-top:10px;font-size:29px;letter-spacing:-.05em;font-weight:700
  }
  .hint{margin-top:6px;color:var(--dim);font-size:12px}
  .layout{
    display:grid;grid-template-columns:minmax(0,1.4fr) minmax(420px,.95fr);gap:18px
  }
  .stack{display:grid;gap:18px}
  .panel{
    border-radius:var(--radius-lg);padding:20px 20px 18px;
    box-shadow:var(--shadow)
  }
  .panel-head{
    display:flex;justify-content:space-between;align-items:flex-start;gap:14px;
    margin-bottom:18px
  }
  .panel-title{font-size:24px;letter-spacing:-.035em;font-weight:650;margin:0}
  .panel-sub{margin-top:6px;color:var(--muted);font-size:13px}
  .badge{
    display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;
    font-size:12px;border:1px solid var(--line);background:rgba(255,255,255,.04)
  }
  .badge.good{color:var(--good);background:var(--good-soft)}
  .badge.bad{color:var(--bad);background:var(--bad-soft)}
  .badge.warn{color:var(--warn);background:var(--warn-soft)}
  .badge.neutral{color:var(--accent);background:var(--accent-soft)}
  .metric-grid{
    display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px
  }
  .metric-card{
    border-radius:18px;padding:15px 16px;min-height:110px
  }
  .metric-card .value{font-size:24px}
  .metric-card .hint{font-size:11px}
  .subgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}
  .subpanel{
    border-radius:18px;padding:15px 16px
  }
  .subpanel h3{margin:0 0 12px;font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
  .stat-list{display:grid;gap:10px}
  .stat-row{
    display:flex;justify-content:space-between;gap:12px;align-items:flex-start;
    padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.06);font-size:14px
  }
  .stat-row:last-child{border-bottom:none;padding-bottom:0}
  .stat-key{color:var(--muted)}
  .stat-val{font-weight:600;text-align:right}
  .table-wrap{overflow:auto;border-radius:16px;border:1px solid rgba(255,255,255,.06)}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.06);white-space:nowrap;text-align:left}
  th{background:rgba(255,255,255,.04);color:var(--muted);font-size:11px;letter-spacing:.16em;text-transform:uppercase}
  tr:hover td{background:rgba(255,255,255,.025)}
  .symbol-cell b{display:block;font-size:14px}
  .symbol-cell span{display:block;margin-top:4px;color:var(--dim);font-size:11px}
  .tag{
    display:inline-flex;align-items:center;padding:5px 10px;border-radius:999px;
    font-size:11px;font-weight:700;letter-spacing:.08em
  }
  .tag.long{background:var(--good-soft);color:var(--good)}
  .tag.short{background:var(--bad-soft);color:var(--bad)}
  .tag.hold{background:rgba(121,184,255,.12);color:var(--blue)}
  .muted{color:var(--muted)}
  .dim{color:var(--dim)}
  .good{color:var(--good)}
  .bad{color:var(--bad)}
  .warn{color:var(--warn)}
  .mono{font-family:"Cascadia Mono","SFMono-Regular",Consolas,monospace}
  .signal-list,.trade-list,.candidate-list{display:grid;gap:10px}
  .feed-item{
    display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center;
    padding:13px 14px;border-radius:16px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05)
  }
  .feed-time{color:var(--dim);font-size:12px}
  .feed-main{min-width:0}
  .feed-title{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .feed-detail{font-size:12px;color:var(--muted);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .trend{
    display:flex;align-items:flex-end;gap:4px;height:106px;padding-top:8px
  }
  .bar{
    flex:1 1 0;min-width:8px;border-radius:999px 999px 4px 4px;opacity:.95
  }
  .bar.pos{background:linear-gradient(180deg, rgba(86,211,125,.95), rgba(86,211,125,.35))}
  .bar.neg{background:linear-gradient(180deg, rgba(255,106,95,.95), rgba(255,106,95,.35))}
  .trend-axis{display:flex;justify-content:space-between;color:var(--dim);font-size:11px;margin-top:8px}
  .log{
    max-height:300px;overflow:auto;border-radius:16px;background:#101010;padding:14px;border:1px solid rgba(255,255,255,.06)
  }
  .log-line{display:flex;gap:12px;padding:4px 0;font-family:"Cascadia Mono",Consolas,monospace;font-size:12px}
  .log-time{color:var(--dim);min-width:62px}
  .actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
  button{
    border:none;border-radius:999px;padding:10px 16px;font:inherit;font-size:13px;
    background:linear-gradient(180deg, rgba(214,179,111,.26), rgba(214,179,111,.16));
    color:var(--text);cursor:pointer;transition:transform .15s ease,opacity .15s ease
  }
  button:hover{transform:translateY(-1px);opacity:.96}
  .empty{padding:18px;color:var(--muted);text-align:center}
  @media(max-width:1280px){
    .layout{grid-template-columns:1fr}
    .hero-inner{grid-template-columns:1fr}
    .metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  }
  @media(max-width:900px){
    .subgrid{grid-template-columns:1fr}
    .feed-item{grid-template-columns:1fr;gap:8px}
    .feed-item > div:last-child{justify-self:flex-start}
    .panel-head{align-items:flex-start}
  }
  @media(max-width:640px){
    .shell{padding:14px 14px 28px}
    .hero{position:relative;top:auto}
    .hero-inner,.panel{padding:16px}
    h1{font-size:30px}
    .hero-kpis,.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
    .value{font-size:25px}
    .metric-card .value{font-size:22px}
    .hero-kpi,.metric-card{min-height:98px}
    .table-wrap{border-radius:14px}
  }
  @media(max-width:520px){
    .hero-kpis,.metric-grid{grid-template-columns:1fr}
    .value{font-size:23px}
    .metric-card .value{font-size:20px}
  }
</style>
</head>
<body>
<div class="shell">
  <section class="hero">
    <div class="hero-inner">
      <div>
        <div class="eyebrow">Trading Control Center</div>
        <h1>宙斯交易中枢</h1>
        <div class="hero-sub">交易状态、风控、绩效、候选与信号放在同一块决策界面里。重点不再是堆表格，而是先看当前风险，再看机会密度，再看执行质量。</div>
        <div class="hero-meta">
          <span class="pill"><span class="dot" id="sys_dot"></span><span id="status">连接中</span></span>
          <span class="pill mono" id="clock">--</span>
          <span class="pill" id="hero_runtime">策略待加载</span>
        </div>
      </div>
      <div class="hero-kpis">
        <div class="hero-kpi"><div class="label">总权益</div><div class="value" id="kpi_balance">--</div><div class="hint">Binance Futures 账户视角</div></div>
        <div class="hero-kpi"><div class="label">可用保证金</div><div class="value" id="kpi_avail">--</div><div class="hint">可继续开仓资金</div></div>
        <div class="hero-kpi"><div class="label">浮动盈亏</div><div class="value" id="kpi_upnl">--</div><div class="hint">当前持仓未实现损益</div></div>
        <div class="hero-kpi"><div class="label">保护单覆盖</div><div class="value" id="kpi_orders">--</div><div class="hint">SL / TP 保护状态</div></div>
      </div>
    </div>
  </section>

  <div class="layout">
    <div class="stack">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">当前持仓</h2>
            <div class="panel-sub">用持仓寿命、保护单和风险/收益映射来决定是否继续持有。</div>
          </div>
          <div class="badge neutral" id="orderSummary">保护单 --</div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>币种</th>
                <th>方向</th>
                <th>数量</th>
                <th>杠杆</th>
                <th>入场</th>
                <th>持仓</th>
                <th>标记</th>
                <th>未实现</th>
                <th>ROI</th>
                <th>SL / TP</th>
                <th>保护单</th>
              </tr>
            </thead>
            <tbody id="positions"></tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">交易绩效</h2>
            <div class="panel-sub">先看今天和 7 天，再看累计质量与交易密度，避免一堆同权字段堆在一起。</div>
          </div>
          <div class="badge neutral" id="hint_perf">--</div>
        </div>
        <div class="metric-grid">
          <div class="metric-card"><div class="label">今日净盈亏</div><div class="value" id="perf_1d">--</div><div class="hint" id="perf_1d_sub">--</div></div>
          <div class="metric-card"><div class="label">7日净盈亏</div><div class="value" id="perf_7d">--</div><div class="hint" id="perf_7d_sub">--</div></div>
          <div class="metric-card"><div class="label">30日净盈亏</div><div class="value" id="perf_30d">--</div><div class="hint" id="perf_30d_sub">--</div></div>
          <div class="metric-card"><div class="label">累计净盈亏</div><div class="value" id="perf_all">--</div><div class="hint" id="perf_all_sub">--</div></div>
        </div>
        <div class="subgrid">
          <div class="subpanel">
            <h3>交易质量</h3>
            <div class="stat-list" id="perf_quality"></div>
          </div>
          <div class="subpanel">
            <h3>交易流量</h3>
            <div class="stat-list" id="perf_volume"></div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">候选与信号</h2>
            <div class="panel-sub">左边是扫描结果，右边是最近动作。候选不只看分数，要看方向和置信度。</div>
          </div>
          <div class="actions">
            <button onclick="loadAll()">刷新数据</button>
          </div>
        </div>
        <div class="subgrid">
          <div class="subpanel">
            <h3>候选池</h3>
            <div class="candidate-list" id="scoring_body"></div>
          </div>
          <div class="subpanel">
            <h3>信号日志</h3>
            <div class="signal-list" id="signal_log_body"></div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">近期成交</h2>
            <div class="panel-sub">最近成交用时间序列卡片展示，适合快速看节奏和策略来源。</div>
          </div>
          <div class="badge neutral" id="hint_trades">--</div>
        </div>
        <div class="trade-list" id="trade_body"></div>
      </section>
    </div>

    <div class="stack">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">系统状态</h2>
            <div class="panel-sub">把状态拆成连接、策略、风险、保证金，不再是一列弱层级文字。</div>
          </div>
          <div class="badge neutral" id="hint_sys">--</div>
        </div>
        <div class="subgrid">
          <div class="subpanel">
            <h3>连接与策略</h3>
            <div class="stat-list" id="sys_core"></div>
          </div>
          <div class="subpanel">
            <h3>风险与账户</h3>
            <div class="stat-list" id="sys_risk"></div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">30天净盈亏轨迹</h2>
            <div class="panel-sub">只保留关键柱图，不让图表喧宾夺主。</div>
          </div>
          <div class="badge neutral">Daily Net</div>
        </div>
        <div id="daily_pnl"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2 class="panel-title">运行日志</h2>
            <div class="panel-sub">最后 40 行核心日志，用来追异常与执行流。</div>
          </div>
          <div class="badge neutral" id="hint_log">--</div>
        </div>
        <div class="log" id="log_lines">读取中...</div>
      </section>
    </div>
  </div>
</div>

<script>
const REFRESH_MS = 5000;
const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });
const num = v => Number.isFinite(Number(v)) ? Number(v) : 0;
const money = v => `${num(v) >= 0 ? '+' : ''}${fmt.format(num(v))} USDT`;
const plainMoney = v => `${fmt.format(num(v))} USDT`;
const pct = v => `${num(v) >= 0 ? '+' : ''}${num(v).toFixed(2)}%`;
const esc = v => {
  const s = String(v ?? '');
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};
const price = v => num(v) ? Number(v).toPrecision(8).replace(/\.?0+$/, '') : '--';
const cls = v => num(v) > 0 ? 'good' : (num(v) < 0 ? 'bad' : 'muted');
const marginLabel = t => t === 'ISOLATED' || t === 'isolated' ? '逐仓' : '全仓';
const tagDir = dir => dir === 'LONG' ? 'long' : (dir === 'SHORT' ? 'short' : 'hold');
function holdLabel(sec){
  const total = Math.max(0, Math.floor(num(sec)));
  if(!total) return '--';
  if(total < 60) return total + 's';
  const mins = Math.floor(total / 60), secs = total % 60;
  if(mins < 60) return mins + 'm' + String(secs).padStart(2, '0') + 's';
  const hours = Math.floor(mins / 60), remMins = mins % 60;
  if(hours < 24) return hours + 'h' + String(remMins).padStart(2, '0') + 'm';
  const days = Math.floor(hours / 24), remHours = hours % 24;
  return days + 'd' + String(remHours).padStart(2, '0') + 'h';
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
function metricHtml(usd, pctVal){
  return `<span class="${cls(usd)}">${money(usd)}</span> <span class="muted">${fmtPct(pctVal)}</span>`;
}
function statRow(label, value){
  return `<div class="stat-row"><span class="stat-key">${label}</span><span class="stat-val">${value}</span></div>`;
}
function setMetric(id, value, sub='', className=''){
  const el = document.getElementById(id);
  el.textContent = value;
  el.className = className ? `value ${className}` : 'value';
  const subEl = document.getElementById(id + '_sub');
  if(subEl) subEl.innerHTML = sub;
}
function feedItem(time, title, detail, sideClass='hold', right=''){
  return `<div class="feed-item">
    <div class="feed-time">${esc(time)}</div>
    <div class="feed-main">
      <div class="feed-title">${title}</div>
      <div class="feed-detail">${detail}</div>
    </div>
    <div><span class="tag ${sideClass}">${right}</span></div>
  </div>`;
}

async function loadAll(){
  document.getElementById('clock').textContent = new Date().toLocaleString();
  document.getElementById('status').textContent = '同步中';

  try{
    const [acctR,posR,hR,cbR,pnlR,ordR,candR,stratR,sigR,tradeR,dailyR,volR] = await Promise.all([
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
      fetch('/health/volume')
    ]);

    const acct = await acctR.json();
    const pos = await posR.json();
    const hD = await hR.json();
    const cbD = await cbR.json();
    const pnlD = await pnlR.json();
    const ordD = await ordR.json();
    const candD = await candR.json();
    const stratD = await stratR.json();
    const sigD = await sigR.json();
    const tradeD = await tradeR.json();
    const dailyD = await dailyR.json();
    const volD = await volR.json();

    document.getElementById('status').textContent = hD.websocket_connected ? '系统在线' : '连接异常';
    document.getElementById('sys_dot').style.background = hD.websocket_connected ? 'var(--good)' : 'var(--bad)';
    document.getElementById('hint_sys').textContent = 'v' + (hD.version || '--');
    document.getElementById('hero_runtime').textContent = stratD && stratD.preset ? `预设 ${stratD.preset}` : '策略待加载';

    if(!acct.error){
      document.getElementById('kpi_balance').textContent = plainMoney(acct.total_balance);
      document.getElementById('kpi_avail').textContent = plainMoney(acct.available_balance);
      document.getElementById('kpi_upnl').textContent = money(acct.unrealized_pnl);
      document.getElementById('kpi_upnl').className = `value ${cls(acct.unrealized_pnl)}`;
    }

    let slCount = 0, tpCount = 0;
    if(!ordD.error && ordD.by_symbol) ordD.by_symbol.forEach(s => { slCount += s.stop_orders; tpCount += s.tp_orders; });
    const ordHas = slCount > 0 || tpCount > 0;
    document.getElementById('kpi_orders').innerHTML = ordHas ? `SL:${slCount} TP:${tpCount}` : '无保护单';
    document.getElementById('kpi_orders').className = `value ${ordHas ? 'good' : 'bad'}`;
    document.getElementById('orderSummary').className = `badge ${ordHas ? 'good' : 'bad'}`;
    document.getElementById('orderSummary').textContent = ordHas ? `保护单 SL:${slCount} TP:${tpCount}` : '无保护单';

    const tripped = !!cbD.tripped;
    const sysCore = [
      statRow('行情连接', hD.websocket_connected ? '<span class="good">WebSocket 实时</span>' : '<span class="bad">已断开</span>'),
      statRow('策略预设', `<span class="muted">${esc(stratD.preset || '--')}</span>`),
      statRow('评分阈值', `买入 ${stratD.buy_threshold ?? '--'} / 卖出 ${stratD.sell_threshold ?? '--'}`),
      statRow('候选池规模', `${candD.total || 0} 个`)
    ];
    const sysRisk = [
      statRow('风控熔断', tripped ? '<span class="bad">已触发</span>' : '<span class="good">正常</span>'),
      statRow('今日净值变化', metricHtml(pnlD.net_pnl_1d || 0, pnlD.net_pnl_1d_pct)),
      statRow('保证金模式', marginLabel(acct.margin_type || 'cross')),
      statRow('保证金余额', acct.margin_balance > 0 ? plainMoney(acct.margin_balance) : '--'),
      statRow('维持保证金', acct.maintenance_margin > 0 ? plainMoney(acct.maintenance_margin) : '--'),
      statRow('当前持仓数', `${pos.count || 0} / ${(window.maxPositions || 5)}`)
    ];
    document.getElementById('sys_core').innerHTML = sysCore.join('');
    document.getElementById('sys_risk').innerHTML = sysRisk.join('');

    setMetric('perf_1d', money(pnlD.net_pnl_1d || 0), `${fmtPct(pnlD.net_pnl_1d_pct)} · 胜率 ${fmtRate(pnlD.win_rate_1d)}`, cls(pnlD.net_pnl_1d || 0));
    setMetric('perf_7d', money(pnlD.net_pnl_7d || 0), `${fmtPct(pnlD.net_pnl_7d_pct)} · 胜率 ${fmtRate(pnlD.win_rate_7d)}`, cls(pnlD.net_pnl_7d || 0));
    setMetric('perf_30d', money(pnlD.net_pnl_30d || 0), `${fmtPct(pnlD.net_pnl_30d_pct)} · 胜率 ${fmtRate(pnlD.win_rate_30d)}`, cls(pnlD.net_pnl_30d || 0));
    setMetric('perf_all', money(pnlD.net_pnl_total || 0), `${fmtPct(pnlD.net_pnl_total_pct)} · 总权益 ${plainMoney(pnlD.total_equity || 0)}`, cls(pnlD.net_pnl_total || 0));
    document.getElementById('hint_perf').textContent = '交易所盈亏口径 + 本地成交流量';

    document.getElementById('perf_quality').innerHTML = [
      statRow('已实现交易数', `${pnlD.trade_count_1d || 0} / ${pnlD.trade_count_7d || 0} / ${pnlD.trade_count_30d || 0}`),
      statRow('已交易币种', `${pnlD.symbols_traded || 0} 个`),
      statRow('7日手续费', plainMoney(pnlD.commission_7d || 0)),
      statRow('7日资金费率', plainMoney(pnlD.funding_7d || 0)),
      statRow('当前浮动盈亏', `<span class="${cls(acct.unrealized_pnl || 0)}">${money(acct.unrealized_pnl || 0)}</span>`)
    ].join('');

    document.getElementById('perf_volume').innerHTML = [
      statRow('今日成交额', `${plainMoney(volD.volume_1d || 0)} · ${volD.trades_1d || 0} 笔`),
      statRow('7日成交额', `${plainMoney(volD.volume_7d || 0)} · ${volD.trades_7d || 0} 笔`),
      statRow('30日成交额', `${plainMoney(volD.volume_30d || 0)} · ${volD.trades_30d || 0} 笔`),
      statRow('累计成交额', `${plainMoney(volD.volume_total || 0)} · ${volD.trades_total || 0} 笔`)
    ].join('');

    let protBySymbol = {};
    (ordD.by_symbol || []).forEach(s => { protBySymbol[s.symbol] = { sl: s.stop_orders, tp: s.tp_orders, total: s.total }; });
    const posBody = document.getElementById('positions');
    if(!pos.error && pos.positions && pos.positions.length > 0){
      let html = '';
      pos.positions.forEach(p => {
        const pnl = num(p.unrealized_pnl), roi = num(p.roi_pct), side = (p.side || '').toUpperCase();
        const lev = p.leverage || 1, entry = num(p.entry_price), qty = num(p.qty);
        const prot = protBySymbol[p.symbol] || { sl: 0, tp: 0 };
        const slPrice = num(p.sl_price), tpPrice = num(p.tp_price);
        const holdHtml = `${holdLabel(p.hold_seconds)}<span class="dim" style="display:block;margin-top:4px">${p.opened_at ? esc(new Date(p.opened_at).toLocaleString()) : '--'}</span>`;
        let slPnl = 0, tpPnl = 0;
        if(side === 'LONG'){
          slPnl = slPrice > 0 ? (slPrice - entry) * Math.abs(qty) : 0;
          tpPnl = tpPrice > 0 ? (tpPrice - entry) * Math.abs(qty) : 0;
        }else{
          slPnl = slPrice > 0 ? (entry - slPrice) * Math.abs(qty) : 0;
          tpPnl = tpPrice > 0 ? (entry - tpPrice) * Math.abs(qty) : 0;
        }
        const protHtml = (prot.sl > 0 || prot.tp > 0)
          ? `<span class="good">SL ${prot.sl}</span> / <span class="good">TP ${prot.tp}</span>`
          : '<span class="bad">裸仓</span>';
        const riskMap = `${slPrice > 0 ? `<span class="bad">SL ${money(slPnl)}</span>` : '--'} / ${tpPrice > 0 ? `<span class="good">TP ${money(tpPnl)}</span>` : '--'}`;
        html += `<tr>
          <td class="symbol-cell"><b>${esc(p.symbol)}</b><span>${esc(p.margin_type || 'cross')} · 名义 ${plainMoney(p.notional || 0)}</span></td>
          <td><span class="tag ${side === 'LONG' ? 'long' : 'short'}">${side}</span></td>
          <td class="mono">${fmt.format(num(p.qty))}</td>
          <td>${lev}x</td>
          <td class="mono">${price(p.entry_price)}</td>
          <td>${holdHtml}</td>
          <td class="mono">${price(p.mark_price)}</td>
          <td class="${cls(pnl)}">${money(pnl)}</td>
          <td class="${cls(roi)}">${pct(roi)}</td>
          <td>${riskMap}</td>
          <td>${protHtml}</td>
        </tr>`;
      });
      posBody.innerHTML = html;
    }else{
      posBody.innerHTML = '<tr><td colspan="11" class="empty">当前无持仓</td></tr>';
    }

    const candBody = document.getElementById('scoring_body');
    if(!candD.error && candD.candidates && candD.candidates.length > 0){
      candBody.innerHTML = candD.candidates.slice(0, 10).map(c => {
        const direction = c.direction || 'HOLD';
        return feedItem(
          price(c.price),
          `<b>${esc(c.symbol)}</b> · 扫描 ${esc(c.scanner_score)}`,
          `24h ${pct(c.change_24h || 0)} · 置信 ${(num(c.confidence || 0) * 100).toFixed(0)}% · 综合 ${Math.round(c.composite_score || c.total_score || c.score || 0)}`,
          tagDir(direction),
          esc(direction)
        );
      }).join('');
    }else{
      candBody.innerHTML = '<div class="empty">等待扫描器产出候选</div>';
    }

    const signalBody = document.getElementById('signal_log_body');
    if(!sigD.error && sigD.signals && sigD.signals.length > 0){
      signalBody.innerHTML = sigD.signals.slice().reverse().slice(0, 6).map(s => {
        const act = s.action || 'HOLD';
        return feedItem(
          s.time ? new Date(s.time).toLocaleTimeString() : '--',
          `<b>${esc(s.symbol)}</b> · ${esc(act)} · 评分 ${esc(s.score ?? '--')}`,
          esc(s.detail || '-'),
          act.includes('SHORT') ? 'short' : act.includes('LONG') ? 'long' : 'hold',
          esc(act)
        );
      }).join('');
    }else{
      signalBody.innerHTML = '<div class="empty">暂无信号</div>';
    }

    const tradeBody = document.getElementById('trade_body');
    if(!tradeD.error && tradeD.trades && tradeD.trades.length > 0){
      tradeBody.innerHTML = tradeD.trades.slice(0, 12).map(t => {
        const side = (t.side || '').toUpperCase();
        return feedItem(
          t.filled_at ? new Date(t.filled_at).toLocaleString() : '--',
          `<b>${esc(t.symbol)}</b> · ${esc(side)} @ ${price(t.price)}`,
          `数量 ${fmt.format(num(t.qty))} · 手续费 ${num(t.commission).toFixed(6)} · ${esc(t.strategy_name || t.type || '-')}`,
          side === 'SELL' ? 'short' : 'long',
          esc(side)
        );
      }).join('');
      document.getElementById('hint_trades').textContent = `${tradeD.total} 笔`;
    }else{
      tradeBody.innerHTML = '<div class="empty">暂无成交</div>';
      document.getElementById('hint_trades').textContent = '0 笔';
    }

    if(!dailyD.error && dailyD.daily_pnl && dailyD.daily_pnl.length > 0){
      const bars = dailyD.daily_pnl;
      const maxAbs = Math.max(...bars.map(b => Math.abs(num(b.pnl))), 0.01);
      const trend = bars.map(b => {
        const h = Math.max(10, Math.round(Math.abs(num(b.pnl)) / maxAbs * 96));
        return `<div class="bar ${num(b.pnl) >= 0 ? 'pos' : 'neg'}" style="height:${h}px" title="${esc(b.date)} ${money(b.pnl)} (${b.trades} 笔)"></div>`;
      }).join('');
      document.getElementById('daily_pnl').innerHTML = `<div class="trend">${trend}</div><div class="trend-axis"><span>${esc(bars[0].date)}</span><span>${esc(bars[bars.length - 1].date)}</span></div>`;
    }
  }catch(e){
    document.getElementById('status').textContent = '连接异常';
    document.getElementById('sys_dot').style.background = 'var(--bad)';
  }
}

async function loadLogs(){
  try{
    const r = await fetch('/health/logs?lines=40');
    const d = await r.json();
    if(!d.error && d.lines && d.lines.length > 0){
      document.getElementById('log_lines').innerHTML = d.lines.map(l => `
        <div class="log-line">
          <span class="log-time">${esc(l.time || '')}</span>
          <span class="${esc((l.level || 'INFO').toLowerCase())}">${esc(l.msg || '')}</span>
        </div>
      `).join('');
      document.getElementById('hint_log').textContent = `${d.file || 'logs'} · ${d.lines.length} lines`;
    }
  }catch(e){}
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
