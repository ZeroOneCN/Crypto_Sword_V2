"""Dashboard HTML for the trading control center."""

from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
except Exception:  # pragma: no cover - preview fallback without FastAPI installed
    FastAPI = Any  # type: ignore
    HTMLResponse = None


DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CryptoPilot 数据看板</title>
  <style>
    :root {
      --bg: #050608;
      --panel: #0d1015;
      --panel-2: #111720;
      --panel-3: #07090d;
      --line: #28303a;
      --line-soft: rgba(255, 255, 255, 0.08);
      --text: #f4f6f8;
      --muted: #87919e;
      --muted-2: #5f6874;
      --m-blue: #00a3e0;
      --m-navy: #003a70;
      --m-red: #e4002b;
      --good: #20d37a;
      --bad: #ff3d55;
      --warn: #ffd23f;
      --shadow: rgba(0, 0, 0, 0.42);
    }

    * { box-sizing: border-box; }
    *::-webkit-scrollbar { width: 10px; height: 10px; }
    *::-webkit-scrollbar-thumb { background: linear-gradient(var(--m-blue), var(--m-red)); }
    *::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        linear-gradient(115deg, rgba(0, 163, 224, 0.12), transparent 28%),
        radial-gradient(circle at 86% 8%, rgba(228, 0, 43, 0.12), transparent 24%),
        repeating-linear-gradient(135deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 16px),
        var(--bg);
      font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    }

    header {
      position: sticky;
      top: 0;
      z-index: 5;
      padding: 20px clamp(14px, 3vw, 34px) 18px;
      background: rgba(5, 6, 8, 0.88);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(16px);
    }

    .m-stripe {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      width: 132px;
      height: 5px;
      margin-bottom: 16px;
      box-shadow: 0 0 24px rgba(0, 163, 224, 0.28);
    }
    .m-stripe span:nth-child(1) { background: var(--m-blue); }
    .m-stripe span:nth-child(2) { background: var(--m-navy); }
    .m-stripe span:nth-child(3) { background: var(--m-red); }

    .title-row {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-end;
      flex-wrap: wrap;
    }

    h1 {
      margin: 0;
      font-size: clamp(24px, 4vw, 40px);
      letter-spacing: 0.08em;
      line-height: 1;
      text-transform: uppercase;
    }

    .sub {
      color: var(--muted);
      font-size: 13px;
      margin-top: 10px;
      letter-spacing: 0.02em;
    }

    main { padding: 22px clamp(14px, 3vw, 34px) 42px; }

    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
    }

    .pill, button {
      border: 1px solid var(--line);
      color: var(--text);
      background: rgba(255,255,255,0.035);
      padding: 9px 12px;
      border-radius: 0;
      font: inherit;
      font-size: 13px;
      letter-spacing: 0.02em;
    }

    button { cursor: pointer; }
    button:hover {
      border-color: var(--m-blue);
      background: rgba(0, 163, 224, 0.12);
    }

    .status-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      margin-right: 7px;
      background: var(--good);
      box-shadow: 0 0 18px var(--good);
    }

    .grid { display: grid; gap: 14px; }
    .cards { grid-template-columns: repeat(8, minmax(132px, 1fr)); }
    .two { grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr); }
    .three { grid-template-columns: repeat(3, minmax(0, 1fr)); }

    .panel, .card {
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)), var(--panel);
      border: 1px solid var(--line);
      border-radius: 0;
      box-shadow: 0 20px 50px var(--shadow);
      position: relative;
      overflow: hidden;
    }

    .card::before, .panel::before {
      content: "";
      position: absolute;
      left: 0;
      top: 0;
      width: 3px;
      height: 100%;
      background: linear-gradient(var(--m-blue), var(--m-navy), var(--m-red));
      opacity: 0.9;
    }

    .card { padding: 16px 16px 15px 18px; min-height: 112px; }
    .panel { padding: 18px 18px 18px 20px; }

    .label { color: var(--muted); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
    .value {
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: clamp(19px, 2.7vw, 28px);
      font-weight: 800;
      margin-top: 10px;
      word-break: break-word;
    }
    .hint { margin-top: 8px; color: var(--muted-2); font-size: 12px; }

    .panel-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .panel h2 { margin: 0; font-size: 18px; letter-spacing: 0.06em; }

    .scroll { overflow: auto; }
    .positions-scroll { max-height: 430px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td {
      padding: 11px 10px;
      border-bottom: 1px solid var(--line-soft);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }
    th {
      color: var(--muted);
      font-weight: 600;
      background: var(--panel-3);
      letter-spacing: 0.04em;
    }
    tr:hover td { background: rgba(0, 163, 224, 0.045); }

    .mono { font-family: "Cascadia Mono", Consolas, monospace; }
    .good { color: var(--good); }
    .bad { color: var(--bad); }
    .warn { color: var(--warn); }
    .muted { color: var(--muted); }
    .stack { display: block; }
    .stack > * + * { margin-top: 14px; }
    .small-card {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.025);
      padding: 12px 12px 10px;
      min-height: 102px;
    }
    .feed {
      max-height: 320px;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .feed-item {
      border: 1px solid var(--line);
      background: var(--panel-2);
      padding: 12px;
    }
    .feed-top {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      margin-bottom: 6px;
    }
    .feed-title { font-weight: 700; }
    .feed-detail {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
      white-space: normal;
      word-break: break-word;
    }
    .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
    .chip {
      border: 1px solid var(--line);
      padding: 3px 8px;
      font-size: 11px;
      color: var(--muted);
    }
    .tag {
      display: inline-block;
      border: 1px solid var(--line);
      padding: 2px 8px;
      font-size: 11px;
      min-width: 56px;
      text-align: center;
    }
    .log {
      background: var(--panel-3);
      border: 1px solid var(--line);
      padding: 14px;
      max-height: 360px;
      overflow: auto;
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 12px;
      line-height: 1.55;
      color: #b8c7de;
      white-space: pre-wrap;
    }

    @media (max-width: 1320px) {
      .cards { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    }
    @media (max-width: 1000px) {
      .two { grid-template-columns: 1fr; }
      .three { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 620px) {
      .cards, .three { grid-template-columns: 1fr; }
      .title-row { align-items: flex-start; }
      .toolbar { justify-content: flex-start; }
      th, td { padding: 9px 8px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="m-stripe" aria-hidden="true"><span></span><span></span><span></span></div>
    <div class="title-row">
      <div>
        <h1>CryptoPilot 中枢</h1>
        <div class="sub">参考 crypto_sword dashboard 骨架重构，顶部指标卡、双列主布局、三列信息区和底部日志统一到一套视图。</div>
      </div>
      <div class="toolbar">
        <span class="pill"><span class="status-dot"></span><span id="status">连接中</span></span>
        <span class="pill mono" id="clock">--</span>
        <button onclick="loadAll(true)">立即刷新</button>
      </div>
    </div>
  </header>

  <main>
    <section class="grid cards">
      <div class="card"><div class="label">总权益</div><div class="value" id="totalBalance">--</div><div class="hint">账户总权益</div></div>
      <div class="card"><div class="label">可用余额</div><div class="value" id="availableBalance">--</div><div class="hint">可继续开仓资金</div></div>
      <div class="card"><div class="label">未实现盈亏</div><div class="value" id="unrealized">--</div><div class="hint">当前持仓浮盈浮亏</div></div>
      <div class="card"><div class="label">今日净盈亏</div><div class="value" id="todayPnl">--</div><div class="hint" id="todayWindow">--</div></div>
      <div class="card"><div class="label">7日净盈亏</div><div class="value" id="pnl7">--</div><div class="hint">交易所口径优先</div></div>
      <div class="card"><div class="label">30日净盈亏</div><div class="value" id="pnl30">--</div><div class="hint">数据库复盘辅助</div></div>
      <div class="card"><div class="label">今日成交笔数</div><div class="value" id="todayTrades">--</div><div class="hint">一开一平算 1 笔</div></div>
      <div class="card"><div class="label">启用策略</div><div class="value" id="presetText">--</div><div class="hint" id="presetHint">--</div></div>
    </section>

    <section class="grid two" style="margin-top:14px">
      <div class="panel">
        <div class="panel-head"><h2>当前持仓</h2><span class="pill" id="orderSummary">保护单 --</span></div>
        <div class="scroll positions-scroll"><table>
          <thead><tr><th>币种</th><th>方向</th><th>策略</th><th>数量</th><th>开仓 / 标记</th><th>未实现</th><th>ROI</th><th>TP进度</th><th>开仓原因</th></tr></thead>
          <tbody id="positions"></tbody>
        </table></div>
      </div>

      <div class="stack">
        <div class="panel">
          <div class="panel-head"><h2>今日战况</h2><span class="pill" id="incomeSource">来源 --</span></div>
          <div class="grid three">
            <div class="small-card"><div class="label">胜率</div><div class="value" id="todayWinRate">--</div><div class="hint">今日口径</div></div>
            <div class="small-card"><div class="label">平均盈利</div><div class="value" id="avgWin">--</div><div class="hint">已完成交易</div></div>
            <div class="small-card"><div class="label">平均亏损</div><div class="value" id="avgLoss">--</div><div class="hint">已完成交易</div></div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><h2>30日净盈亏轨迹</h2><span class="muted" id="reportTime">--</span></div>
          <div class="scroll"><table>
            <thead><tr><th>日期</th><th>净盈亏</th><th>交易数</th></tr></thead>
            <tbody id="periods"></tbody>
          </table></div>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:14px">
      <div class="panel-head"><h2>候选、信号、活动</h2><span class="muted">统一三列信息区</span></div>
      <div class="grid three">
        <div>
          <div class="label" style="margin-bottom:10px">候选池</div>
          <div class="feed" id="candidatesFeed"></div>
        </div>
        <div>
          <div class="label" style="margin-bottom:10px">信号日志</div>
          <div class="feed" id="signalsFeed"></div>
        </div>
        <div>
          <div class="label" style="margin-bottom:10px">操作记录</div>
          <div class="feed" id="activityFeed"></div>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:14px">
      <div class="panel-head"><h2>最近已完成交易</h2><span class="pill" id="tradeSummary">复盘 --</span></div>
      <div class="scroll"><table>
        <thead><tr><th>平仓时间</th><th>币种</th><th>方向</th><th>策略</th><th>开仓</th><th>平仓</th><th>盈亏</th><th>幅度</th><th>平仓原因</th><th>TP命中</th><th>持仓</th></tr></thead>
        <tbody id="recentTrades"></tbody>
      </table></div>
    </section>

    <section class="panel" style="margin-top:14px">
      <div class="panel-head"><h2>策略拆分</h2><span class="muted">按 preset 复盘</span></div>
      <div class="scroll"><table>
        <thead><tr><th>策略</th><th>笔数</th><th>净盈亏</th><th>胜率</th><th>平均持仓</th><th>Profit Factor</th><th>TP命中</th><th>退出原因</th></tr></thead>
        <tbody id="strategyRows"></tbody>
      </table></div>
    </section>

    <section class="panel" style="margin-top:14px">
      <div class="panel-head"><h2>运行日志尾部</h2><span class="muted">仅展示最近 240 行</span></div>
      <div class="log" id="logs">读取中...</div>
    </section>
  </main>

  <script>
    const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });
    const num = v => Number.isFinite(Number(v)) ? Number(v) : 0;
    const money = v => `${num(v) >= 0 ? '+' : ''}${fmt.format(num(v))} USDT`;
    const plainMoney = v => `${fmt.format(num(v))} USDT`;
    const pct = v => `${num(v) >= 0 ? '+' : ''}${num(v).toFixed(2)}%`;
    const cls = v => num(v) > 0 ? 'good' : (num(v) < 0 ? 'bad' : 'muted');
    const safe = v => String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    const price = v => num(v) ? Number(v).toPrecision(8).replace(/\.?0+$/, '') : '--';
    const hold = sec => {
      const total = Math.max(0, Math.floor(num(sec)));
      if (!total) return '--';
      if (total < 60) return `${total}s`;
      const mins = Math.floor(total / 60);
      if (mins < 60) return `${mins}m`;
      const hours = Math.floor(mins / 60);
      const remMins = mins % 60;
      if (hours < 24) return `${hours}h${String(remMins).padStart(2, '0')}m`;
      const days = Math.floor(hours / 24);
      return `${days}d${String(hours % 24).padStart(2, '0')}h`;
    };

    function setValue(id, value, className='') {
      const el = document.getElementById(id);
      el.textContent = value;
      el.className = className ? `value ${className}` : 'value';
    }

    function cell(v, c='') { return `<td class="${c}">${v}</td>`; }

    function feedCard(title, detail, chips=[], right='') {
      return `<div class="feed-item">
        <div class="feed-top"><span class="feed-title">${title}</span>${right ? `<span class="tag">${safe(right)}</span>` : ''}</div>
        <div class="feed-detail">${detail}</div>
        ${chips.length ? `<div class="chips">${chips.map(c => `<span class="chip">${safe(c)}</span>`).join('')}</div>` : ''}
      </div>`;
    }

    function renderPositions(rows) {
      const body = document.getElementById('positions');
      if (!rows || !rows.length) {
        body.innerHTML = `<tr><td colspan="9" class="muted">当前无持仓，系统待命。</td></tr>`;
        return;
      }
      body.innerHTML = rows.map(p => `<tr>
        ${cell(`<b>${safe(p.symbol)}</b>`, '')}
        ${cell(safe(p.side), cls(p.side === 'SHORT' ? -1 : 1))}
        ${cell(`<b>${safe(p.strategy_preset || '--')}</b><br><span class="muted">${safe(p.support_presets || '--')}</span>`)}
        ${cell(fmt.format(num(p.qty)), 'mono')}
        ${cell(`${price(p.entry_price)}<br><span class="muted">${price(p.mark_price)}</span>`, 'mono')}
        ${cell(money(p.unrealized_pnl), cls(p.unrealized_pnl))}
        ${cell(pct(p.roi_pct), cls(p.roi_pct))}
        ${cell(`${safe(p.tp_tiers_filled || '--')}<br><span class="muted">TP3 ${price(p.tp_price || p.take_profit_price)}</span>`)}
        ${cell(safe(String(p.entry_reason || '--').replace(/^preset:[^|]+\|/, '')))}
      </tr>`).join('');
    }

    function renderDaily(rows) {
      const body = document.getElementById('periods');
      if (!rows || !rows.length) {
        body.innerHTML = `<tr><td colspan="3" class="muted">暂无 30 日净盈亏数据。</td></tr>`;
        return;
      }
      body.innerHTML = rows.map(r => `<tr>
        ${cell(safe(r.date), 'mono')}
        ${cell(money(r.pnl), cls(r.pnl))}
        ${cell(num(r.trades || 0), 'mono')}
      </tr>`).join('');
    }

    function renderTrades(rows) {
      const body = document.getElementById('recentTrades');
      if (!rows || !rows.length) {
        body.innerHTML = `<tr><td colspan="11" class="muted">暂无已完成交易。</td></tr>`;
        return;
      }
      body.innerHTML = rows.map(t => `<tr>
        ${cell(safe((t.closed_at || '').replace('T', ' ').replace('Z', '')), 'mono')}
        ${cell(`<b>${safe(t.symbol)}</b>`)}
        ${cell(safe(t.side))}
        ${cell(safe(t.strategy || '--'))}
        ${cell(price(t.entry_price), 'mono')}
        ${cell(price(t.exit_price), 'mono')}
        ${cell(money(t.pnl), cls(t.pnl))}
        ${cell(pct(t.pnl_pct), cls(t.pnl_pct))}
        ${cell(safe(t.exit_reason || '--'))}
        ${cell(safe((t.tp_tiers_hit || []).join('/') || '--'))}
        ${cell(hold(t.hold_seconds))}
      </tr>`).join('');
    }

    function renderStrategies(strategies) {
      const body = document.getElementById('strategyRows');
      const names = Object.keys(strategies || {});
      if (!names.length) {
        body.innerHTML = `<tr><td colspan="8" class="muted">暂无策略复盘数据。</td></tr>`;
        return;
      }
      body.innerHTML = names.map(name => {
        const s = strategies[name] || {};
        const exitBreakdown = Object.entries(s.exit_reason_breakdown || {}).map(([k,v]) => `${k}:${v}`).join(' / ') || '--';
        const tpHits = s.tp_hits ? `TP1 ${num(s.tp_hits.TP1)} / TP2 ${num(s.tp_hits.TP2)} / TP3 ${num(s.tp_hits.TP3)}` : '--';
        return `<tr>
          ${cell(`<b>${safe(name)}</b>`)}
          ${cell(num(s.trades || 0), 'mono')}
          ${cell(money(s.pnl || 0), cls(s.pnl || 0))}
          ${cell(pct(s.win_rate || 0))}
          ${cell(safe(s.avg_hold_time || hold(s.avg_hold_time_seconds)))}
          ${cell(s.profit_factor ?? '--', 'mono')}
          ${cell(tpHits)}
          ${cell(exitBreakdown)}
        </tr>`;
      }).join('');
    }

    function renderFeed(elId, rows, emptyText) {
      const el = document.getElementById(elId);
      if (!rows.length) {
        el.innerHTML = `<div class="muted">${safe(emptyText)}</div>`;
        return;
      }
      el.innerHTML = rows.join('');
    }

    async function loadAll(manual=false) {
      try {
        const [healthRes, accountRes, positionsRes, strategyRes, candidatesRes, signalsRes, tradesRes, ordersRes, pnlRes, reportRes, report30Res, activityRes, logsRes] = await Promise.all([
          fetch('/health', { cache: 'no-store' }),
          fetch('/health/account', { cache: 'no-store' }),
          fetch('/health/positions', { cache: 'no-store' }),
          fetch('/health/strategy', { cache: 'no-store' }),
          fetch('/health/candidates', { cache: 'no-store' }),
          fetch('/health/signals', { cache: 'no-store' }),
          fetch('/health/report', { cache: 'no-store' }),
          fetch('/health/orders', { cache: 'no-store' }),
          fetch('/health/pnl', { cache: 'no-store' }),
          fetch('/health/report', { cache: 'no-store' }),
          fetch('/health/report/30d', { cache: 'no-store' }),
          fetch('/health/activity', { cache: 'no-store' }),
          fetch('/health/logs?lines=240', { cache: 'no-store' }),
        ]);

        const health = await healthRes.json();
        const account = await accountRes.json();
        const positions = await positionsRes.json();
        const strategy = await strategyRes.json();
        const candidates = await candidatesRes.json();
        const signals = await signalsRes.json();
        const trades = await tradesRes.json();
        const orders = await ordersRes.json();
        const pnl = await pnlRes.json();
        const report = await reportRes.json();
        const report30 = await report30Res.json();
        const activity = await activityRes.json();
        const logs = await logsRes.json();

        document.getElementById('status').textContent = health.websocket_connected ? (manual ? '已手动刷新' : '在线运行') : '连接异常';
        document.getElementById('clock').textContent = new Date().toLocaleString();

        setValue('totalBalance', plainMoney(account.total_balance || 0));
        setValue('availableBalance', plainMoney(account.available_balance || 0));
        setValue('unrealized', money(account.unrealized_pnl || 0), cls(account.unrealized_pnl || 0));
        setValue('todayPnl', money(pnl.net_pnl_1d || 0), cls(pnl.net_pnl_1d || 0));
        setValue('pnl7', money(pnl.net_pnl_7d || 0), cls(pnl.net_pnl_7d || 0));
        setValue('pnl30', money(pnl.net_pnl_30d || 0), cls(pnl.net_pnl_30d || 0));
        setValue('todayTrades', num(report.total_trades || 0));
        setValue('presetText', (strategy.enabled_presets || []).join(' / ') || '--');
        document.getElementById('presetHint').textContent = `主预设 ${strategy.preset || '--'}`;
        document.getElementById('todayWindow').textContent = `胜率 ${pct(pnl.win_rate_1d || 0)}`;
        document.getElementById('incomeSource').textContent = `来源 ${pnl.error ? 'db' : 'exchange+db'}`;
        setValue('todayWinRate', pct(report.win_rate || 0));
        setValue('avgWin', money(report.avg_win || 0), cls(report.avg_win || 0));
        setValue('avgLoss', money(report.avg_loss || 0), cls(report.avg_loss || 0));
        document.getElementById('orderSummary').textContent = `保护单 ${num(orders.total || 0)}`;
        document.getElementById('tradeSummary').textContent = `复盘 ${num(report.total_trades || 0)} 笔`;
        document.getElementById('reportTime').textContent = report.generated_at ? new Date(report.generated_at).toLocaleString() : '--';

        renderPositions(positions.positions || []);
        renderDaily(report30.daily_pnl || report.daily_pnl || []);
        renderTrades((report.trades || []).slice().reverse());
        renderStrategies(report.strategies || {});

        renderFeed(
          'candidatesFeed',
          (candidates.candidates || []).slice(0, 8).map(c => feedCard(
            `${safe(c.symbol)} / 扫描 ${safe(c.scanner_score)}`,
            `24h ${pct(c.change_24h || 0)} / 综合 ${num(c.composite_score || 0).toFixed(1)} / 置信 ${(num(c.confidence || 0) * 100).toFixed(0)}%`,
            Object.entries(c.preset_scores || {}).map(([k, v]) => `${k}:${Math.round(num(v))}`),
            c.direction || 'HOLD'
          )),
          '暂无候选池数据'
        );

        renderFeed(
          'signalsFeed',
          (signals.signals || []).slice().reverse().slice(0, 10).map(s => feedCard(
            `${safe(s.symbol)} / ${safe(s.action || '--')}`,
            safe(s.detail || '--'),
            [
              s.preset ? `主策略 ${s.preset}` : '',
              ...(s.supporting_presets || []).map(p => `支持 ${p}`),
              s.opportunity_type ? `机会 ${s.opportunity_type}` : '',
            ].filter(Boolean),
            s.preset || '--'
          )),
          '暂无信号'
        );

        renderFeed(
          'activityFeed',
          (activity.items || []).slice(0, 12).map(a => feedCard(
            `${safe(a.symbol || '--')} / ${safe(a.badge || a.event_type || '--')}`,
            safe(a.detail || '--'),
            [a.preset ? `预设 ${a.preset}` : '', a.strategy_id ? `ID ${a.strategy_id}` : ''].filter(Boolean),
            a.event_type || '--'
          )),
          '暂无操作记录'
        );

        document.getElementById('logs').textContent = (logs.lines || []).map(line => `[${line.time || ''}] ${line.level || 'INFO'} ${line.msg || ''}`).join('\n') || '暂无日志';
      } catch (err) {
        document.getElementById('status').textContent = `连接异常: ${err.message}`;
      }
    }

    loadAll();
    setInterval(loadAll, 5000);
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
