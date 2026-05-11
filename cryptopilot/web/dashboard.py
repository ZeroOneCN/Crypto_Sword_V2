"""仪表盘 HTML — CryptoPilot V2 驾驶舱 · Apple Design System."""

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
  :root {
    --canvas: #000000;
    --surface: #1d1d1f;
    --surface-elevated: #272729;
    --surface-card: #2a2a2c;
    --ink: #f5f5f7;
    --ink-muted: #a1a1a6;
    --ink-subtle: #6e6e73;
    --primary: #0066cc;
    --primary-hover: #0077ed;
    --good: #30d158;
    --bad: #ff453a;
    --warn: #ffd60a;
    --hairline: rgba(255,255,255,0.10);
    --hairline-soft: rgba(255,255,255,0.06);
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 18px;
    --radius-pill: 9999px;
    --spacing-xs: 8px;
    --spacing-sm: 12px;
    --spacing-md: 16px;
    --spacing-lg: 24px;
    --spacing-xl: 32px;
    --spacing-xxl: 48px;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{
    margin:0;min-height:100vh;color:var(--ink);
    background:var(--canvas);
    font-family:"SF Pro Text","SF Pro Display",system-ui,-apple-system,BlinkMacSystemFont,"Inter","Microsoft YaHei",sans-serif;
    font-size:17px;font-weight:400;line-height:1.47;letter-spacing:-0.022em;
    -webkit-font-smoothing:antialiased;
  }
  header{
    position:sticky;top:0;z-index:5;
    padding:var(--spacing-md) var(--spacing-xl);
    background:rgba(29,29,31,0.85);
    border-bottom:1px solid var(--hairline);
    backdrop-filter:saturate(180%) blur(20px);
    -webkit-backdrop-filter:saturate(180%) blur(20px);
  }
  .title-row{display:flex;justify-content:space-between;gap:var(--spacing-md);align-items:center;flex-wrap:wrap}
  h1{margin:0;font-family:"SF Pro Display",system-ui,-apple-system,sans-serif;font-size:28px;font-weight:600;letter-spacing:-0.012em;line-height:1.1}
  .sub{color:var(--ink-muted);font-size:13px;font-weight:400;letter-spacing:-0.01em;margin-top:4px}
  main{padding:var(--spacing-lg) var(--spacing-xl) var(--spacing-xxl)}
  .pill,button{
    border:1px solid var(--hairline);color:var(--ink);background:rgba(255,255,255,0.06);
    padding:7px 14px;font:inherit;font-size:14px;font-weight:400;text-decoration:none;
    border-radius:var(--radius-pill);letter-spacing:-0.016em;cursor:pointer;
    transition:background .15s,border-color .15s;
  }
  button:hover{background:rgba(255,255,255,0.10);border-color:var(--primary)}
  .status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;background:var(--good)}
  .grid{display:grid;gap:var(--spacing-md)}
  .cards{grid-template-columns:repeat(7,minmax(132px,1fr))}
  .two{grid-template-columns:minmax(0,1.1fr) minmax(0,0.9fr)}
  .card{
    background:var(--surface);border:1px solid var(--hairline-soft);
    border-radius:var(--radius-lg);padding:var(--spacing-lg);
    transition:border-color .2s;
  }
  .card:hover{border-color:var(--hairline)}
  main > section + section {
    margin-top: var(--spacing-xxl);
    padding-top: var(--spacing-lg);
    border-top: 1px solid var(--hairline);
  }
  main > section:first-child { margin-top: 0; padding-top: 0; border-top: none; }
  .panel{
    background:var(--surface);border:1px solid var(--hairline-soft);
    border-radius:var(--radius-lg);padding:var(--spacing-lg);
  }
  .grid .panel{height:100%}
  .label{color:var(--ink-muted);font-size:12px;font-weight:600;letter-spacing:0;text-transform:uppercase}
  .value{
    font-family:"SF Mono","SF Pro Display",monospace;
    font-size:28px;font-weight:600;margin-top:6px;word-break:break-word;
    letter-spacing:-0.022em;
  }
  .hint{margin-top:6px;color:var(--ink-subtle);font-size:12px;font-weight:400;letter-spacing:-0.01em}
  .panel-head{display:flex;justify-content:space-between;gap:var(--spacing-sm);align-items:center;flex-wrap:wrap;margin-bottom:var(--spacing-md)}
  .panel h2{margin:0;font-family:"SF Pro Display",system-ui,-apple-system,sans-serif;font-size:20px;font-weight:600;letter-spacing:-0.016em}
  .scroll{overflow-x:auto}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th,td{padding:10px 12px;border-bottom:1px solid var(--hairline-soft);text-align:left;white-space:nowrap}
  th{color:var(--ink-muted);font-weight:600;background:var(--surface-elevated);font-size:12px;text-transform:uppercase;letter-spacing:0}
  tr:hover td{background:rgba(255,255,255,0.03)}
  .mono{font-family:"SF Mono",Menlo,Consolas,monospace;font-size:13px}
  .good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.muted{color:var(--ink-muted)}
  .badge{display:inline-block;padding:3px 10px;font-size:11px;font-weight:600;letter-spacing:0;border-radius:var(--radius-pill)}
  .badge-ok{color:var(--good);background:rgba(48,209,88,0.12)}
  .badge-warn{color:var(--warn);background:rgba(255,214,10,0.12)}
  .badge-err{color:var(--bad);background:rgba(255,69,58,0.12)}
  .badge-long{color:var(--good);background:rgba(48,209,88,0.12)}
  .badge-short{color:var(--bad);background:rgba(255,69,58,0.12)}
  .badge-purple{color:#bf5af2;background:rgba(191,90,242,0.12)}
  .badge-teal{color:#64d2ff;background:rgba(100,210,255,0.12)}
  .badge-blue{color:var(--primary);background:rgba(0,102,204,0.12)}
  .conn-dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:6px}
  .conn-dot.ok{background:var(--good)}.conn-dot.err{background:var(--bad)}
  .conn-dot.warn{background:var(--warn)}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  .conn-dot.pulse{animation:pulse 2s ease-in-out infinite}
  .badge-err.pulse{animation:pulse 2s ease-in-out infinite}
  .value-big{font-size:18px;font-weight:600}
  .inline-stat{display:flex;justify-content:space-between;padding:5px 0;font-size:14px;border-bottom:1px solid var(--hairline-soft);letter-spacing:-0.016em}
  .inline-stat:last-child{border-bottom:none}
  .inline-stat span:last-child{font-weight:600}
  .daily-bar{display:inline-block;height:24px;min-width:3px;margin:0 1px;border-radius:2px}
  .daily-bar-pos{background:var(--good)}.daily-bar-neg{background:var(--bad)}
  .nowrap{white-space:nowrap}.truncate{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .log{
    background:var(--surface-elevated);border:1px solid var(--hairline-soft);
    border-radius:var(--radius-md);padding:var(--spacing-md);max-height:300px;overflow:auto;
    font-family:"SF Mono",Menlo,Consolas,monospace;font-size:12px;line-height:1.6;color:var(--ink-muted);
    white-space:pre-wrap;
  }
  .log-INFO{color:var(--ink-muted)}.log-WARNING{color:var(--warn)}.log-ERROR{color:var(--bad)}.log-DEBUG{color:var(--ink-subtle)}.log-SUCCESS{color:var(--good)}
  .log-line{white-space:nowrap;padding:1px 0}.log-line .lt{color:var(--ink-subtle);margin-right:8px}
  .label-tag{font-size:10px;color:var(--ink-muted);background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:var(--radius-sm);margin-right:3px;text-transform:uppercase;letter-spacing:0}
  @media(max-width:1320px){.cards{grid-template-columns:repeat(4,minmax(0,1fr))}}
  @media(max-width:1000px){.two{grid-template-columns:1fr}}
  @media(max-width:620px){.cards{grid-template-columns:1fr}.two{grid-template-columns:1fr}main{padding:var(--spacing-sm)}header{padding:var(--spacing-sm)}}
</style>
</head>
<body>
<header>
  <div class="title-row">
    <div>
      <h1>宙斯交易中枢</h1>
      <div class="sub">CryptoPilot V2 · 多因子评分引擎 · UTC 自然日统计</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <span class="pill"><span class="status-dot" id="sys_dot"></span><span id="status">连接中</span></span>
      <span class="pill mono" id="clock" style="font-size:13px">--</span>
      <button onclick="loadAll()">刷新</button>
    </div>
  </div>
</header>

<main>
  <!-- KPI Cards -->
  <section class="grid cards" style="margin-bottom:var(--spacing-md)">
    <div class="card"><div class="label">总余额</div><div class="value" id="kpi_balance">--</div><div class="hint">USDT · Binance Futures</div></div>
    <div class="card"><div class="label">可用</div><div class="value" id="kpi_avail">--</div><div class="hint">可开仓资金</div></div>
    <div class="card"><div class="label">浮动盈亏</div><div class="value" id="kpi_upnl">--</div><div class="hint">未实现盈亏</div></div>
    <div class="card"><div class="label">保证金率</div><div class="value" id="kpi_margin">--</div><div class="hint">越低越安全</div></div>
    <div class="card"><div class="label">持仓</div><div class="value" id="kpi_pos">--</div><div class="hint">已开 / 上限</div></div>
    <div class="card"><div class="label">风控</div><div class="value" id="kpi_cb">--</div><div class="hint">熔断状态</div></div>
    <div class="card"><div class="label">保护单</div><div class="value" id="kpi_orders">--</div><div class="hint">SL / TP</div></div>
  </section>

  <!-- Positions + System -->
  <section class="grid two">
    <div class="panel">
      <div class="panel-head"><h2>当前持仓</h2><span class="pill" id="orderSummary">保护单 --</span></div>
      <div class="scroll"><table>
        <thead><tr><th>币种</th><th>方向</th><th>数量</th><th>杠杆</th><th>入场</th><th>标记</th><th>未实现</th><th>ROI</th><th>预估SL/TP</th><th>保护单</th></tr></thead>
        <tbody id="positions"></tbody>
      </table></div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>系统状态</h2><span class="pill" id="hint_sys">--</span></div>
      <div class="inline-stat"><span>行情源</span><span id="sys_ws">--</span></div>
      <div class="inline-stat"><span>策略预设</span><span id="sys_preset">--</span></div>
      <div class="inline-stat"><span>评分阈值</span><span id="sys_threshold">--</span></div>
      <div class="inline-stat"><span>熔断</span><span id="sys_cb">--</span></div>
      <div class="inline-stat"><span>当日盈亏 UTC</span><span id="sys_daily_pnl">--</span></div>
      <div class="inline-stat"><span>候选池</span><span id="sys_pool">--</span></div>
      <div class="inline-stat"><span>持仓模式</span><span id="sys_mtype">--</span></div>
      <div class="inline-stat"><span>保证金余额</span><span id="sys_margin_bal">--</span></div>
      <div class="inline-stat"><span>维持保证金</span><span id="sys_maint_margin">--</span></div>
    </div>
  </section>

  <!-- Performance + Signals -->
  <section class="grid two">
    <div class="panel">
      <div class="panel-head"><h2>交易绩效</h2><span class="pill" id="hint_perf">--</span></div>
      <div id="report">
        <div class="inline-stat"><span>7天净盈亏</span><span>--</span></div>
        <div class="inline-stat"><span>30天净盈亏</span><span>--</span></div>
        <div class="inline-stat"><span>累计净盈亏</span><span>--</span></div>
        <div class="inline-stat"><span>今日净盈亏</span><span>--</span></div>
        <div class="inline-stat"><span>手续费</span><span>--</span></div>
        <div class="inline-stat"><span>资金费率</span><span>--</span></div>
        <div class="inline-stat"><span>交易币种</span><span>--</span></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>信号日志</h2><span class="pill" id="hint_sig">--</span></div>
      <div class="scroll"><table>
        <thead><tr><th>时间</th><th>币种</th><th>动作</th><th>评分</th><th>说明</th></tr></thead>
        <tbody id="signal_log_body"></tbody>
      </table></div>
    </div>
  </section>

  <!-- Candidate Pool (15 items) + Recent Trades -->
  <section class="grid two">
    <div class="panel">
      <div class="panel-head"><h2>候选池</h2><span class="pill muted">Top-10</span></div>
      <div class="scroll"><table>
        <thead><tr><th>币种</th><th>价格</th><th>涨跌</th><th>扫描</th><th>综合</th><th>方向</th><th>置信</th></tr></thead>
        <tbody id="scoring_body"></tbody>
      </table></div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>近期成交</h2><span class="pill" id="hint_trades">--</span></div>
      <div class="scroll"><table>
        <thead><tr><th>时间</th><th>币种</th><th>方向</th><th>价格</th><th>数量</th><th>手续费</th><th>策略</th></tr></thead>
        <tbody id="trade_body"></tbody>
      </table></div>
    </div>
  </section>

  <!-- Daily PnL Chart -->
  <section class="panel">
    <div class="panel-head"><h2>30天走势</h2><span class="pill muted">每日净盈亏</span></div>
    <div id="daily_pnl" style="padding:8px 0"></div>
  </section>

  <!-- Logs -->
  <section class="panel">
    <div class="panel-head"><h2>运行日志</h2><span class="pill muted" id="hint_log">--</span></div>
    <div class="log" id="log_lines">读取中...</div>
  </section>
</main>

<script>
const REFRESH_MS=5000;
const fmt=new Intl.NumberFormat('en-US',{maximumFractionDigits:6});
const num=v=>Number.isFinite(Number(v))?Number(v):0;
const money=v=>`${num(v)>=0?'+':''}${fmt.format(num(v))} USDT`;
const plainMoney=v=>`${fmt.format(num(v))} USDT`;
const pct=v=>`${num(v)>=0?'+':''}${num(v).toFixed(2)}%`;
const cls=v=>num(v)>0?'good':(num(v)<0?'bad':'muted');
const esc=v=>{const s=String(v??'');return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');};
const price=v=>num(v)?Number(v).toPrecision(8).replace(/\.?0+$/,''):'--';
const cn=v=>num(v)>0?'good':(num(v)<0?'bad':'muted');
const marginLabel=t=>t==='ISOLATED'||t==='isolated'?'逐仓':'全仓';

function setEl(id,val,className=''){const el=document.getElementById(id);el.textContent=val;if(className)el.className=className+' value';}

async function loadAll(){
  const now=new Date();
  document.getElementById('clock').textContent=now.toLocaleString();
  document.getElementById('status').textContent='已连接';

  try{
    const[acctR,posR,hR,cbR,pnlR,ordR,candR,stratR,sigR,tradeR,dailyR]=await Promise.all([
      fetch('/health/account'),fetch('/health/positions?_='+Date.now()),
      fetch('/health'),fetch('/health/circuit'),fetch('/health/pnl'),
      fetch('/health/orders?_='+Date.now()),fetch('/health/candidates'),
      fetch('/health/strategy'),fetch('/health/signals'),fetch('/health/trades'),
      fetch('/health/report/30d')
    ]);
    const acct=await acctR.json(),pos=await posR.json();
    const hD=await hR.json(),cbD=await cbR.json(),pnlD=await pnlR.json();
    const ordD=await ordR.json(),candD=await candR.json(),stratD=await stratR.json();
    const sigD=await sigR.json(),tradeD=await tradeR.json(),dailyD=await dailyR.json();

    if(!acct.error){
      setEl('kpi_balance',plainMoney(acct.total_balance));
      setEl('kpi_avail',plainMoney(acct.available_balance));
      setEl('kpi_upnl',money(acct.unrealized_pnl),cls(acct.unrealized_pnl));
      setEl('kpi_margin',acct.margin_display||((acct.margin_ratio||0)*100).toFixed(2)+'%');
      document.getElementById('kpi_margin').nextElementSibling.textContent=
        acct.maintenance_margin>0?'维持 '+plainMoney(acct.maintenance_margin):'越低越安全';
      document.getElementById('sys_mtype').textContent=marginLabel(acct.margin_type||'cross');
      document.getElementById('sys_margin_bal').innerHTML=acct.margin_balance>0
        ?'<span class="good">'+plainMoney(acct.margin_balance)+'</span>':'--';
      document.getElementById('sys_maint_margin').innerHTML=acct.maintenance_margin>0
        ?'<span class="muted">'+plainMoney(acct.maintenance_margin)+'</span>':'--';
    }
    if(!pos.error){setEl('kpi_pos',(pos.count||0)+' / '+(window.maxPositions||5))}

    document.getElementById('sys_dot').className=hD.websocket_connected?'status-dot':'status-dot err';
    document.getElementById('sys_ws').innerHTML=hD.websocket_connected
      ?'<span class="conn-dot ok pulse"></span>WebSocket 实时'
      :'<span class="conn-dot err"></span>断开';
    document.getElementById('hint_sys').textContent='v'+hD.version;
    if(!stratD.error){
      document.getElementById('sys_preset').innerHTML='<span class="badge badge-purple">'+esc(stratD.preset||'composite')+'</span>';
      document.getElementById('sys_threshold').innerHTML='买入≥'+stratD.buy_threshold+' 卖出≤'+stratD.sell_threshold;
    }
    const tripped=cbD.tripped;
    document.getElementById('sys_cb').innerHTML=tripped?'<span class="badge badge-err">已熔断</span>':'<span class="badge badge-ok">正常</span>';
    setEl('kpi_cb',tripped?'已熔断':'正常',tripped?'bad':'good');
    document.getElementById('sys_daily_pnl').innerHTML='<span class="'+cn(pnlD.net_pnl_1d||0)+' value-big">'+money(pnlD.net_pnl_1d||0)+'</span>';
    document.getElementById('sys_pool').textContent=(candD&&candD.total||0)+' 个候选';

    let slCount=0,tpCount=0,totalOrders=0;
    if(!ordD.error&&ordD.by_symbol)ordD.by_symbol.forEach(s=>{slCount+=s.stop_orders;tpCount+=s.tp_orders;totalOrders+=s.total});
    const ordHas=(slCount>0||tpCount>0);
    document.getElementById('kpi_orders').innerHTML=ordHas?'SL:'+slCount+' TP:'+tpCount:'<span style="color:var(--bad)">裸仓!</span>';
    document.getElementById('kpi_orders').style.color=ordHas?slCount>0?'var(--good)':'var(--warn)':'var(--bad)';
    document.getElementById('orderSummary').textContent=ordHas?'保护单 SL:'+slCount+' TP:'+tpCount:'⚠ 无保护单';
    window._ordBySymbol=ordD.by_symbol||[];

    const net7=pnlD.net_pnl_7d||0,net30=pnlD.net_pnl_30d||0,netTotal=pnlD.net_pnl_total||0,net1d=pnlD.net_pnl_1d||0;
    document.getElementById('report').innerHTML=
      '<div class="inline-stat"><span>7天净盈亏</span><span class="'+cn(net7)+' value-big">'+money(net7)+'</span></div>'+
      '<div class="inline-stat"><span>30天净盈亏</span><span class="'+cn(net30)+' value-big">'+money(net30)+'</span></div>'+
      '<div class="inline-stat"><span>累计净盈亏</span><span class="'+cn(netTotal)+' value-big">'+money(netTotal)+'</span></div>'+
      '<div class="inline-stat"><span>今日净盈亏</span><span class="'+cn(net1d)+' value-big">'+money(net1d)+'</span></div>'+
      '<div class="inline-stat"><span>手续费</span><span>'+plainMoney(pnlD.commission_7d||0)+'</span></div>'+
      '<div class="inline-stat"><span>资金费率</span><span>'+plainMoney(pnlD.funding_7d||0)+'</span></div>'+
      '<div class="inline-stat"><span>交易币种</span><span>'+(pnlD.symbols_traded||0)+'</span></div>';
    document.getElementById('hint_perf').textContent='含手续费+资金费率';

    let protBySymbol={};(window._ordBySymbol||[]).forEach(s=>{protBySymbol[s.symbol]={sl:s.stop_orders,tp:s.tp_orders,total:s.total}});
    const posBody=document.getElementById('positions');
    if(!pos.error&&pos.positions&&pos.positions.length>0){
      let html='';
      pos.positions.forEach(p=>{
        const pnl=num(p.unrealized_pnl);const roi=num(p.roi_pct);
        const side=(p.side||'').toUpperCase();const lev=p.leverage||1;
        const entry=num(p.entry_price);const qty=num(p.qty);
        const prot=protBySymbol[p.symbol]||{sl:0,tp:0};
        const protHtml=(prot.sl>0||prot.tp>0)?'SL:'+prot.sl+' TP:'+prot.tp:'<span class="badge badge-err pulse">裸仓</span>';
        const slPrice=num(p.sl_price);const tpPrice=num(p.tp_price);
        let slPnl=0,tpPnl=0;
        if(side==='LONG'){slPnl=slPrice>0?(slPrice-entry)*Math.abs(qty):0;tpPnl=tpPrice>0?(tpPrice-entry)*Math.abs(qty):0}
        else{slPnl=slPrice>0?(entry-slPrice)*Math.abs(qty):0;tpPnl=tpPrice>0?(entry-tpPrice)*Math.abs(qty):0}
        const estPnlHtml=(slPrice>0?'<span class="bad">SL:'+money(slPnl)+'</span>':'--')+' / '+(tpPrice>0?'<span class="good">TP:'+money(tpPnl)+'</span>':'--');
        html+='<tr><td><b>'+esc(p.symbol)+'</b></td>'+
          '<td><span class="badge '+(side==='LONG'?'badge-long':'badge-short')+'">'+side+'</span></td>'+
          '<td class="mono">'+fmt.format(num(p.qty))+'</td><td>'+lev+'x</td>'+
          '<td class="mono">'+price(p.entry_price)+'</td><td class="mono">'+price(p.mark_price)+'</td>'+
          '<td class="'+cn(pnl)+'">'+money(pnl)+'</td><td class="'+cn(roi)+'">'+pct(roi)+'</td>'+
          '<td class="nowrap">'+estPnlHtml+'</td><td>'+protHtml+'</td></tr>';
      });
      posBody.innerHTML=html;
    }else{posBody.innerHTML='<tr><td colspan="10" class="muted">当前无持仓</td></tr>'}

    if(!sigD.error&&sigD.signals&&sigD.signals.length>0){
      let html='';
      sigD.signals.slice().reverse().slice(0,5).forEach(s=>{
        const act=s.action||'';let actCls='badge-teal';
        if(act.includes('LONG'))actCls='badge-long';else if(act.includes('SHORT'))actCls='badge-short';
        html+='<tr><td class="nowrap">'+(s.time?new Date(s.time).toLocaleTimeString():'-')+'</td>'+
          '<td><b>'+esc(s.symbol)+'</b></td>'+
          '<td><span class="badge '+actCls+'">'+esc(act)+'</span></td>'+
          '<td>'+(s.score||'-')+'</td>'+
          '<td class="truncate" title="'+esc(s.detail||'')+'">'+esc(s.detail||'-')+'</td></tr>';
      });
      document.getElementById('signal_log_body').innerHTML=html;
      document.getElementById('hint_sig').textContent=sigD.total+' 条';
    }else{document.getElementById('signal_log_body').innerHTML='<tr><td colspan="5" class="muted">暂无信号</td></tr>'}

    const candBody=document.getElementById('scoring_body');
    if(!candD.error&&candD.candidates&&candD.candidates.length>0){
      let html='';
      candD.candidates.slice(0,10).forEach(c=>{
        const changeCls=parseFloat(c.change_24h)>=0?'good':'bad';
        let dirBadge='<span class="badge badge-teal">HOLD</span>';
        if(c.direction==='LONG')dirBadge='<span class="badge badge-long">LONG</span>';
        else if(c.direction==='SHORT')dirBadge='<span class="badge badge-short">SHORT</span>';
        const totalScore=c.composite_score||c.total_score||c.score||0;
        html+='<tr><td><b>'+esc(c.symbol)+'</b></td>'+
          '<td class="mono">'+price(c.price)+'</td><td class="'+changeCls+'">'+pct(c.change_24h)+'</td>'+
          '<td>'+c.scanner_score+'</td>'+
          '<td><span class="badge badge-purple">'+Math.round(totalScore)+'</span></td>'+
          '<td>'+dirBadge+'</td>'+
          '<td>'+pct(c.confidence||0)+'</td></tr>';
      });
      candBody.innerHTML=html;
    }else{candBody.innerHTML='<tr><td colspan="7" class="muted">等待扫描器产出</td></tr>'}

    const tradeBody=document.getElementById('trade_body');
    if(!tradeD.error&&tradeD.trades&&tradeD.trades.length>0){
      let html='';
      tradeD.trades.slice(0,10).forEach(t=>{
        const side=(t.side||'').toUpperCase();const sideCls=side==='BUY'?'badge-long':'badge-short';
        html+='<tr><td class="nowrap">'+(t.filled_at?new Date(t.filled_at).toLocaleTimeString():'-')+'</td>'+
          '<td><b>'+esc(t.symbol)+'</b></td>'+
          '<td><span class="badge '+sideCls+'">'+side+'</span></td>'+
          '<td class="mono">'+price(t.price)+'</td><td>'+fmt.format(num(t.qty))+'</td>'+
          '<td>'+num(t.commission).toFixed(6)+'</td>'+
          '<td class="truncate" title="'+esc(t.strategy_name||t.type||'-')+'">'+esc(t.strategy_name||t.type||'-')+'</td></tr>';
      });
      tradeBody.innerHTML=html;
      document.getElementById('hint_trades').textContent=tradeD.total+' 笔';
    }else{tradeBody.innerHTML='<tr><td colspan="7" class="muted">暂无成交</td></tr>'}

    try{
      if(!dailyD.error&&dailyD.daily_pnl&&dailyD.daily_pnl.length>0){
        const bars=dailyD.daily_pnl;const maxAbs=Math.max(...bars.map(b=>Math.abs(b.pnl)),0.01);
        let html='<div style="display:flex;align-items:flex-end;gap:2px;height:72px;overflow-x:auto;padding:4px 0">';
        bars.forEach(b=>{const h=Math.max(4,(Math.abs(b.pnl)/maxAbs*64));html+='<div title="'+esc(b.date)+': '+money(b.pnl)+' ('+b.trades+'笔)" class="daily-bar '+(b.pnl>=0?'daily-bar-pos':'daily-bar-neg')+'" style="height:'+h+'px;flex:0 0 12px"></div>'});
        html+='</div><div style="font-size:12px;color:var(--ink-subtle);margin-top:4px;text-align:center">30天盈亏柱状图</div>';
        document.getElementById('daily_pnl').innerHTML=html;
      }
    }catch(e){}
  }catch(e){document.getElementById('status').textContent='连接异常';document.getElementById('sys_ws').innerHTML='<span class="conn-dot err"></span>连接失败'}

  async function loadLogs(){
    try{
      const r=await fetch('/health/logs?lines=40');const d=await r.json();
      if(!d.error&&d.lines&&d.lines.length>0){
        let html='';
        d.lines.forEach(l=>{const cls='log-'+esc(l.level||'INFO');html+='<div class="log-line"><span class="lt">'+esc(l.time||'')+'</span><span class="'+cls+'">'+esc(l.msg||'')+'</span></div>'});
        document.getElementById('log_lines').textContent='';document.getElementById('log_lines').innerHTML=html;
        document.getElementById('hint_log').textContent=(d.file||'')+' ('+d.lines.length+'行)';
      }
    }catch(e){}
  }
  setInterval(loadLogs,5000);loadLogs();
}
loadAll();setInterval(loadAll,REFRESH_MS);
</script>
</body>
</html>"""


def add_dashboard_route(app: FastAPI) -> None:
    """Add dashboard route to an existing FastAPI app."""
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
