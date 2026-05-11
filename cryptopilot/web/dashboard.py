"""仪表盘 HTML — CryptoPilot V2 驾驶舱 · 宙斯交易中枢 Design System."""

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
    --bg: #050608;
    --panel: #0d1015;
    --panel-3: #07090d;
    --line: #28303a;
    --line-soft: rgba(255,255,255,0.08);
    --text: #f4f6f8;
    --muted: #87919e;
    --muted-2: #5f6874;
    --m-blue: #00a3e0;
    --m-navy: #003a70;
    --m-red: #e4002b;
    --good: #20d37a;
    --bad: #ff3d55;
    --warn: #ffd23f;
    --shadow: rgba(0,0,0,0.42);
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{
    margin:0;min-height:100vh;color:var(--text);
    background:
      linear-gradient(115deg,rgba(0,163,224,0.12),transparent 28%),
      radial-gradient(circle at 86% 8%,rgba(228,0,43,0.12),transparent 24%),
      repeating-linear-gradient(135deg,rgba(255,255,255,0.025) 0 1px,transparent 1px 16px),
      var(--bg);
    font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
  }
  header{
    position:sticky;top:0;z-index:5;
    padding:18px clamp(14px,3vw,34px) 14px;
    background:rgba(5,6,8,0.88);border-bottom:1px solid var(--line);
    backdrop-filter:blur(16px);
  }
  .m-stripe{display:grid;grid-template-columns:1fr 1fr 1fr;width:132px;height:5px;margin-bottom:14px;box-shadow:0 0 24px rgba(0,163,224,0.28)}
  .m-stripe span:nth-child(1){background:var(--m-blue)}
  .m-stripe span:nth-child(2){background:var(--m-navy)}
  .m-stripe span:nth-child(3){background:var(--m-red)}
  .title-row{display:flex;justify-content:space-between;gap:14px;align-items:flex-end;flex-wrap:wrap}
  h1{margin:0;font-size:clamp(22px,4vw,36px);letter-spacing:0.08em;line-height:1;text-transform:uppercase}
  .sub{color:var(--muted);font-size:13px;margin-top:8px;letter-spacing:0.02em}
  main{padding:20px clamp(14px,3vw,34px) 36px}
  .pill,button,a.button{
    border:1px solid var(--line);color:var(--text);background:rgba(255,255,255,0.035);
    padding:8px 12px;font:inherit;font-size:13px;text-decoration:none;letter-spacing:0.02em;
  }
  button,a.button{cursor:pointer}
  button:hover,a.button:hover{border-color:var(--m-blue);background:rgba(0,163,224,0.12)}
  .status-dot{display:inline-block;width:8px;height:8px;margin-right:7px;background:var(--good);box-shadow:0 0 18px var(--good)}
  .grid{display:grid;gap:14px}
  .cards{grid-template-columns:repeat(7,minmax(132px,1fr))}
  .two{grid-template-columns:minmax(0,1.1fr) minmax(0,0.9fr)}
  .panel,.card{
    background:linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01)),var(--panel);
    border:1px solid var(--line);box-shadow:0 20px 50px var(--shadow);
    position:relative;overflow:hidden;
  }
  .card::before,.panel::before{
    content:"";position:absolute;left:0;top:0;width:3px;height:100%;
    background:linear-gradient(var(--m-blue),var(--m-navy),var(--m-red));opacity:0.9;
  }
  .card{padding:14px 14px 13px 16px;min-height:100px}
  .panel{padding:16px 16px 16px 18px;margin-top:14px}
  .label{color:var(--muted);font-size:12px;letter-spacing:0.08em;text-transform:uppercase}
  .value{font-family:"Cascadia Mono",Consolas,monospace;font-size:clamp(17px,2.5vw,26px);font-weight:800;margin-top:8px;word-break:break-word}
  .hint{margin-top:6px;color:var(--muted-2);font-size:12px}
  .panel-head{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
  .panel h2{margin:0;font-size:17px;letter-spacing:0.06em}
  .scroll{overflow-x:auto}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:10px 10px;border-bottom:1px solid var(--line-soft);text-align:left;white-space:nowrap}
  th{color:var(--muted);font-weight:600;background:var(--panel-3);letter-spacing:0.04em}
  tr:hover td{background:rgba(0,163,224,0.045)}
  .mono{font-family:"Cascadia Mono",Consolas,monospace}
  .good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.muted{color:var(--muted)}
  .badge{display:inline-block;padding:2px 8px;font-size:11px;font-weight:600;letter-spacing:0.6px;text-transform:uppercase;border:1px solid var(--line)}
  .badge-ok{color:var(--good);border-color:rgba(32,211,122,0.3);background:rgba(32,211,122,0.08)}
  .badge-warn{color:var(--warn);border-color:rgba(255,210,63,0.3);background:rgba(255,210,63,0.08)}
  .badge-err{color:var(--bad);border-color:rgba(255,61,85,0.3);background:rgba(255,61,85,0.08);animation:pulse 1.5s infinite}
  .badge-long{color:var(--good);border-color:rgba(32,211,122,0.3)}
  .badge-short{color:var(--bad);border-color:rgba(255,61,85,0.3)}
  .badge-purple{color:#9b6dff;border-color:rgba(155,109,255,0.3)}
  .badge-teal{color:#2dd4bf;border-color:rgba(45,212,191,0.3)}
  .conn-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
  .conn-dot.ok{background:var(--good)}.conn-dot.err{background:var(--bad)}
  .conn-dot.warn{background:var(--warn)}.conn-dot.pulse{animation:pulse 2s ease-in-out infinite}
  .value-big{font-size:18px;font-weight:700}
  .inline-stat{display:flex;justify-content:space-between;padding:4px 0;font-size:13px;border-bottom:1px solid var(--line-soft)}
  .inline-stat:last-child{border-bottom:none}
  .inline-stat span:last-child{font-weight:600}
  .daily-bar{display:inline-block;height:28px;min-width:3px;margin:0 1px}
  .daily-bar-pos{background:var(--good)}.daily-bar-neg{background:var(--bad)}
  .nowrap{white-space:nowrap}.truncate{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  .log{
    background:var(--panel-3);border:1px solid var(--line);
    padding:12px;max-height:320px;overflow:auto;
    font-family:"Cascadia Mono",Consolas,monospace;
    font-size:12px;line-height:1.55;color:#b8c7de;white-space:pre-wrap;
  }
  .log-INFO{color:#b8c7de}.log-WARNING{color:var(--warn)}.log-ERROR{color:var(--bad)}.log-DEBUG{color:#505050}.log-SUCCESS{color:var(--good)}
  .log-line{white-space:nowrap;padding:1px 0}.log-line .lt{color:#5f6874;margin-right:8px}
  .label-tag{font-size:10px;color:var(--muted);background:rgba(255,255,255,0.06);padding:1px 6px;border:1px solid var(--line);margin-right:3px;text-transform:uppercase;letter-spacing:0.4px}
  @media(max-width:1320px){.cards{grid-template-columns:repeat(4,minmax(0,1fr))}}
  @media(max-width:1000px){.two{grid-template-columns:1fr}}
  @media(max-width:620px){.cards{grid-template-columns:1fr}.two,.three{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <div class="m-stripe" aria-hidden="true"><span></span><span></span><span></span></div>
  <div class="title-row">
    <div>
      <h1>宙斯交易中枢</h1>
      <div class="sub">CryptoPilot V2 · 多因子评分引擎 · 统计以 Binance UTC 自然日为准</div>
    </div>
    <div>
      <span class="pill"><span class="status-dot" id="sys_dot"></span><span id="status">连接中</span></span>
      <span class="pill mono" id="clock">--</span>
      <button onclick="loadAll()">立即刷新</button>
    </div>
  </div>
</header>

<main>
  <!-- Row 1: KPI Cards -->
  <section class="grid cards">
    <div class="card"><div class="label">总余额</div><div class="value" id="kpi_balance">--</div><div class="hint">Binance Futures</div></div>
    <div class="card"><div class="label">可用余额</div><div class="value" id="kpi_avail">--</div><div class="hint">可开仓资金</div></div>
    <div class="card"><div class="label">未实现盈亏</div><div class="value" id="kpi_upnl">--</div><div class="hint">当前持仓浮动</div></div>
    <div class="card"><div class="label">保证金率</div><div class="value" id="kpi_margin">--</div><div class="hint">越低越安全</div></div>
    <div class="card"><div class="label">持仓</div><div class="value" id="kpi_pos">--</div><div class="hint">已开 / 上限</div></div>
    <div class="card"><div class="label">风控</div><div class="value" id="kpi_cb">--</div><div class="hint">熔断 / 正常</div></div>
    <div class="card"><div class="label">保护单</div><div class="value" id="kpi_orders">--</div><div class="hint">SL/TP 状态</div></div>
  </section>

  <!-- Row 2: Positions + System Status -->
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

  <!-- Row 3: Performance + Signal Log -->
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

  <!-- Row 4: Candidate Pool + Recent Trades -->
  <section class="grid two">
    <div class="panel">
      <div class="panel-head"><h2>候选池评分明细</h2><span class="pill muted">Top-5 多因子投票</span></div>
      <div class="scroll"><table>
        <thead><tr><th>币种</th><th>价格</th><th>涨跌</th><th>扫描分</th><th>综合评分</th><th>方向</th><th>置信度</th></tr></thead>
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

  <!-- Row 5: Daily PnL Chart -->
  <section class="panel">
    <div class="panel-head"><h2>30天盈亏走势</h2><span class="pill muted">每日净盈亏柱状图</span></div>
    <div id="daily_pnl" style="padding:6px 0"></div>
  </section>

  <!-- Row 6: Log Panel -->
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
const esc=v=>String(v??'').replace(/[&<>\"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[ch]));
const price=v=>num(v)?Number(v).toPrecision(8).replace(/\.?0+$/,''):'--';
const cn=v=>num(v)>0?'good':(num(v)<0?'bad':'muted');
const marginLabel=t=>t==='ISOLATED'||t==='isolated'?'🔒 逐仓':'🌐 全仓';

function setEl(id,val,className=''){const el=document.getElementById(id);el.textContent=val;if(className)el.className=className+' value';}

async function loadAll(){
  const now=new Date();
  document.getElementById('clock').textContent=now.toLocaleString();
  document.getElementById('status').textContent='自动刷新中';

  try{
    // Parallel fetch all endpoints
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

    // KPI cards
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

    // Positions
    if(!pos.error){
      setEl('kpi_pos',(pos.count||0)+' / '+(window.maxPositions||5));
    }

    // System status
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

    // Protection orders
    let slCount=0,tpCount=0,totalOrders=0;
    if(!ordD.error&&ordD.by_symbol){
      ordD.by_symbol.forEach(s=>{slCount+=s.stop_orders;tpCount+=s.tp_orders;totalOrders+=s.total});
    }
    const ordHas=(slCount>0||tpCount>0);
    document.getElementById('kpi_orders').innerHTML=ordHas
      ?'SL:'+slCount+' TP:'+tpCount
      :'<span style="color:var(--bad);animation:pulse 1.5s infinite">裸仓!</span>';
    document.getElementById('kpi_orders').style.color=ordHas?slCount>0?'var(--good)':'var(--warn)':'var(--bad)';
    document.getElementById('orderSummary').textContent=ordHas?'保护单 SL:'+slCount+' TP:'+tpCount:'⚠ 无保护单';
    window._ordBySymbol=ordD.by_symbol||[];

    // Performance
    const net7=pnlD.net_pnl_7d||0,net30=pnlD.net_pnl_30d||0;
    const netTotal=pnlD.net_pnl_total||0,net1d=pnlD.net_pnl_1d||0;
    document.getElementById('report').innerHTML=
      '<div class="inline-stat"><span>7天净盈亏</span><span class="'+cn(net7)+' value-big">'+money(net7)+'</span></div>'+
      '<div class="inline-stat"><span>30天净盈亏</span><span class="'+cn(net30)+' value-big">'+money(net30)+'</span></div>'+
      '<div class="inline-stat"><span>累计净盈亏</span><span class="'+cn(netTotal)+' value-big">'+money(netTotal)+'</span></div>'+
      '<div class="inline-stat"><span>今日净盈亏</span><span class="'+cn(net1d)+' value-big">'+money(net1d)+'</span></div>'+
      '<div class="inline-stat"><span>手续费</span><span>'+plainMoney(pnlD.commission_7d||0)+'</span></div>'+
      '<div class="inline-stat"><span>资金费率</span><span>'+plainMoney(pnlD.funding_7d||0)+'</span></div>'+
      '<div class="inline-stat"><span>交易币种</span><span>'+(pnlD.symbols_traded||0)+'</span></div>';
    document.getElementById('hint_perf').textContent='含手续费+资金费率';

    // Position table
    let protBySymbol={};
    (window._ordBySymbol||[]).forEach(s=>{protBySymbol[s.symbol]={sl:s.stop_orders,tp:s.tp_orders,total:s.total}});
    const posBody=document.getElementById('positions');
    if(!pos.error&&pos.positions&&pos.positions.length>0){
      let html='';
      pos.positions.forEach(p=>{
        const pnl=num(p.unrealized_pnl);const roi=num(p.roi_pct);
        const side=(p.side||'').toUpperCase();const lev=p.leverage||1;
        const entry=num(p.entry_price);const qty=num(p.qty);
        const mtype=p.margin_type||'cross';
        const prot=protBySymbol[p.symbol]||{sl:0,tp:0};
        const protHtml=(prot.sl>0||prot.tp>0)
          ?'SL:'+prot.sl+' TP:'+prot.tp
          :'<span class="badge-err" style="animation:pulse 1.5s infinite">裸仓</span>';
        const slPrice=num(p.sl_price);const tpPrice=num(p.tp_price);
        let slPnl=0,tpPnl=0;
        if(side==='LONG'){slPnl=slPrice>0?(slPrice-entry)*Math.abs(qty):0;tpPnl=tpPrice>0?(tpPrice-entry)*Math.abs(qty):0}
        else{slPnl=slPrice>0?(entry-slPrice)*Math.abs(qty):0;tpPnl=tpPrice>0?(entry-tpPrice)*Math.abs(qty):0}
        const estPnlHtml=(slPrice>0?'<span class="bad">SL:'+money(slPnl)+'</span>':'--')+' / '+(tpPrice>0?'<span class="good">TP:'+money(tpPnl)+'</span>':'--');
        html+='<tr>'+
          '<td><b>'+esc(p.symbol)+'</b></td>'+
          '<td><span class="badge '+(side==='LONG'?'badge-long':'badge-short')+'">'+side+'</span></td>'+
          '<td class="mono">'+fmt.format(num(p.qty))+'</td>'+
          '<td>'+lev+'x</td>'+
          '<td class="mono">'+price(p.entry_price)+'</td>'+
          '<td class="mono">'+price(p.mark_price)+'</td>'+
          '<td class="'+cn(pnl)+'">'+money(pnl)+'</td>'+
          '<td class="'+cn(roi)+'">'+pct(roi)+'</td>'+
          '<td class="nowrap">'+estPnlHtml+'</td>'+
          '<td>'+protHtml+'</td></tr>';
      });
      posBody.innerHTML=html;
    }else{posBody.innerHTML='<tr><td colspan="10" class="muted">当前无持仓，系统待命。</td></tr>'}

    // Signal log
    if(!sigD.error&&sigD.signals&&sigD.signals.length>0){
      let html='';
      sigD.signals.slice().reverse().slice(0,25).forEach(s=>{
        const act=s.action||'';let actCls='badge-teal';
        if(act.includes('LONG'))actCls='badge-long';
        else if(act.includes('SHORT'))actCls='badge-short';
        const tm=s.time?new Date(s.time).toLocaleTimeString():'-';
        html+='<tr><td class="nowrap">'+tm+'</td>'+
          '<td><b>'+esc(s.symbol)+'</b></td>'+
          '<td><span class="badge '+actCls+'">'+esc(act)+'</span></td>'+
          '<td>'+(s.score||'-')+'</td>'+
          '<td class="truncate" title="'+esc(s.detail||'')+'">'+esc(s.detail||'-')+'</td></tr>';
      });
      document.getElementById('signal_log_body').innerHTML=html;
      document.getElementById('hint_sig').textContent=sigD.total+' 条';
    }else{document.getElementById('signal_log_body').innerHTML='<tr><td colspan="5" class="muted">暂无信号</td></tr>'}

    // Candidate pool
    const candBody=document.getElementById('scoring_body');
    if(!candD.error&&candD.candidates&&candD.candidates.length>0){
      let html='';
      candD.candidates.forEach(c=>{
        const changeCls=parseFloat(c.change_24h)>=0?'good':'bad';
        let dirBadge='<span class="badge badge-teal">HOLD</span>';
        if(c.direction==='LONG')dirBadge='<span class="badge badge-long">LONG</span>';
        else if(c.direction==='SHORT')dirBadge='<span class="badge badge-short">SHORT</span>';
        const totalScore=c.composite_score||c.total_score||c.score||0;
        html+='<tr><td><b>'+esc(c.symbol)+'</b></td>'+
          '<td class="mono">'+price(c.price)+'</td>'+
          '<td class="'+changeCls+'">'+pct(c.change_24h)+'</td>'+
          '<td><span class="badge badge-teal">'+c.scanner_score+'</span></td>'+
          '<td><span class="badge badge-purple">'+Math.round(totalScore)+'</span></td>'+
          '<td>'+dirBadge+'</td>'+
          '<td>'+pct(c.confidence||0)+'</td></tr>';
      });
      candBody.innerHTML=html;
    }else{candBody.innerHTML='<tr><td colspan="7" class="muted">等待扫描器产出</td></tr>'}

    // Recent trades
    const tradeBody=document.getElementById('trade_body');
    if(!tradeD.error&&tradeD.trades&&tradeD.trades.length>0){
      let html='';
      tradeD.trades.slice(0,30).forEach(t=>{
        const side=(t.side||'').toUpperCase();
        const sideCls=side==='BUY'?'badge-long':'badge-short';
        const tm=t.filled_at?new Date(t.filled_at).toLocaleTimeString():'-';
        const strat=esc(t.strategy_name||t.type||'-');
        html+='<tr><td class="nowrap">'+tm+'</td>'+
          '<td><b>'+esc(t.symbol)+'</b></td>'+
          '<td><span class="badge '+sideCls+'">'+side+'</span></td>'+
          '<td class="mono">'+price(t.price)+'</td><td>'+fmt.format(num(t.qty))+'</td>'+
          '<td>'+num(t.commission).toFixed(6)+'</td>'+
          '<td class="truncate" title="'+strat+'">'+strat+'</td></tr>';
      });
      tradeBody.innerHTML=html;
      document.getElementById('hint_trades').textContent=tradeD.total+' 笔';
    }else{tradeBody.innerHTML='<tr><td colspan="7" class="muted">暂无成交</td></tr>'}

    // Daily PnL bars
    try{
      if(!dailyD.error&&dailyD.daily_pnl&&dailyD.daily_pnl.length>0){
        const bars=dailyD.daily_pnl;const maxAbs=Math.max(...bars.map(b=>Math.abs(b.pnl)),0.01);
        let html='<div style="display:flex;align-items:flex-end;gap:2px;height:80px;overflow-x:auto;padding:4px 0">';
        bars.forEach(b=>{
          const h=Math.max(4,(Math.abs(b.pnl)/maxAbs*70));
          html+='<div title="'+esc(b.date)+': '+money(b.pnl)+' ('+b.trades+'笔)" class="daily-bar '+(b.pnl>=0?'daily-bar-pos':'daily-bar-neg')+'" style="height:'+h+'px;flex:0 0 12px"></div>';
        });
        html+='</div><div style="font-size:12px;color:var(--muted);margin-top:4px;text-align:center">30天盈亏柱状图</div>';
        document.getElementById('daily_pnl').innerHTML=html;
      }
    }catch(e){}

  }catch(e){
    document.getElementById('status').textContent='连接异常: '+e.message;
    document.getElementById('sys_ws').innerHTML='<span class="conn-dot err"></span>连接失败';
  }
}

async function loadLogs(){
  try{
    const r=await fetch('/health/logs?lines=40');const d=await r.json();
    if(!d.error&&d.lines&&d.lines.length>0){
      let html='';
      d.lines.forEach(l=>{
        const cls='log-'+esc(l.level||'INFO');
        html+='<div class="log-line"><span class="lt">'+esc(l.time||'')+'</span><span class="'+cls+'">'+esc(l.msg||'')+'</span></div>';
      });
      document.getElementById('log_lines').textContent='';
      document.getElementById('log_lines').innerHTML=html;
      document.getElementById('hint_log').textContent=(d.file||'')+' ('+d.lines.length+'行)';
    }
  }catch(e){}
}

setInterval(loadLogs,5000);
loadLogs();
loadAll();
setInterval(loadAll,REFRESH_MS);
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
