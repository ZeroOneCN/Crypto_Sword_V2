"""仪表盘 HTML — CryptoPilot V2 驾驶舱 · Ferrari Design System."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CryptoPilot V2 · 驾驶舱</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'FerrariSans','Segoe UI',system-ui,-apple-system,sans-serif;background:#181818;color:#ffffff;padding:32px 48px;min-height:100vh}
  h1{font-size:36px;font-weight:500;margin-bottom:16px;color:#ffffff;display:flex;align-items:center;gap:16px;letter-spacing:-0.36px}
  h1 small{font-size:13px;color:#666;font-weight:400;margin-left:auto;letter-spacing:0}
  .top-bar{display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap}
  .stat-card{background:#303030;border:1px solid #404040;border-radius:2px;padding:20px 24px;flex:1;min-width:140px;text-align:center;transition:border-color .2s}
  .stat-card:hover{border-color:#da291c}
  .stat-card .label{font-size:11px;color:#8f8f8f;text-transform:uppercase;letter-spacing:1.1px;margin-bottom:6px;font-weight:600}
  .stat-card .value{font-size:36px;font-weight:700;letter-spacing:-0.72px;line-height:1.1}
  .stat-card .sub{font-size:12px;color:#666;margin-top:4px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:16px;margin-bottom:16px}
  .card{background:#303030;border-radius:2px;padding:24px;border:1px solid #404040}
  .card h2{font-size:16px;color:#8f8f8f;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #404040;padding-bottom:10px;font-weight:500;letter-spacing:0.08px}
  .card h2 .hint{font-weight:400;font-size:12px;color:#666}
  .badge{display:inline-block;padding:3px 10px;border-radius:2px;font-size:12px;font-weight:600;letter-spacing:0.6px;text-transform:uppercase}
  .badge-ok{background:#03904a;color:#fff}.badge-warn{background:#f6e500;color:#181818}
  .badge-err{background:#da291c;color:#fff}.badge-info{background:#4c98b9;color:#fff}
  .badge-long{background:#03904a;color:#fff}.badge-short{background:#da291c;color:#fff}
  .badge-purple{background:#6b3fa0;color:#fff}.badge-teal{background:#2d7d6f;color:#fff}
  table{width:100%;border-collapse:collapse;font-size:14px;font-weight:400}
  th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #404040}
  th{color:#8f8f8f;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:1.1px}
  tr:hover td{background:rgba(218,41,28,0.06)}
  .pnl-pos{color:#03904a}.pnl-neg{color:#da291c}.zero{color:#666}
  .footer{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#666;margin-top:16px}
  .footer .refresh{color:#da291c;cursor:pointer}
  .error{color:#da291c;font-size:14px}
  .scroll-table{overflow-x:auto;max-height:420px;overflow-y:auto}
  .conn-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
  .conn-dot.ok{background:#03904a}.conn-dot.err{background:#da291c}
  .conn-dot.warn{background:#f6e500}.conn-dot.pulse{animation:pulse 2s ease-in-out infinite}
  .nowrap{white-space:nowrap}.truncate{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .value-big{font-size:20px;font-weight:700}
  .inline-stat{display:flex;justify-content:space-between;padding:5px 0;font-size:14px;border-bottom:1px solid #404040}
  .inline-stat:last-child{border-bottom:none}
  .inline-stat span:last-child{font-weight:600}
  .daily-bar{display:inline-block;height:28px;min-width:3px;border-radius:2px;margin:0 1px}
  .daily-bar-pos{background:#03904a}.daily-bar-neg{background:#da291c}
  .tag{margin:1px 3px;display:inline-block}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  .label-tag{font-size:11px;color:#8f8f8f;background:#404040;padding:2px 8px;border-radius:2px;margin-right:4px;text-transform:uppercase;letter-spacing:0.6px}

  /* ---- 日志面板 Ferrari ---- */
  #log_panel{background:#181818;border:1px solid #404040;border-radius:2px;margin-top:16px;padding:24px}
  #log_panel h2{margin-bottom:12px;border-bottom:1px solid #404040;padding-bottom:10px}
  #log_lines{font-family:'Cascadia Code','Fira Code','JetBrains Mono',monospace;font-size:13px;line-height:1.8;max-height:360px;overflow-y:auto;color:#969696;background:#0d0d0d;border-radius:2px;padding:12px 16px;border:1px solid #404040}
  .log-line{white-space:nowrap;padding:1px 0}.log-line .lt{color:#666;margin-right:8px}
  .log-INFO{color:#969696}.log-WARNING{color:#f6e500}.log-ERROR{color:#da291c}.log-DEBUG{color:#505050}
  .log-SUCCESS{color:#03904a}
</style>
</head>
<body>
<h1>
  ⚡ CryptoPilot V2 · 驾驶舱
  <small id="timestamp">Loading...</small>
</h1>

<div class="top-bar" id="account_bar">
  <div class="stat-card"><div class="label">总余额</div><div class="value" style="color:#ffffff">--</div><div class="sub">USDT</div></div>
  <div class="stat-card"><div class="label">可用</div><div class="value" style="color:#4c98b9">--</div><div class="sub">可开仓</div></div>
  <div class="stat-card"><div class="label">浮动盈亏</div><div class="value" id="stat_upnl">--</div><div class="sub">未实现</div></div>
  <div class="stat-card"><div class="label">保证金率</div><div class="value" id="stat_margin">--</div><div class="sub">越低越安全</div></div>
  <div class="stat-card"><div class="label">持仓模式</div><div class="value" id="stat_mtype" style="font-size:24px">--</div><div class="sub">逐仓/全仓</div></div>
  <div class="stat-card"><div class="label">持仓</div><div class="value" id="stat_poscount" style="color:#6b3fa0">--</div><div class="sub">已开/上限</div></div>
  <div class="stat-card"><div class="label">风控</div><div class="value" id="stat_cb" style="font-size:24px">--</div><div class="sub">熔断/正常</div></div>
</div>

<div class="grid">
  <div class="card">
    <h2>系统状态 <span class="hint" id="hint_sys"></span></h2>
    <div class="inline-stat"><span>行情源</span><span id="sys_ws">--</span></div>
    <div class="inline-stat"><span>策略预设</span><span id="sys_preset">--</span></div>
    <div class="inline-stat"><span>评分阈值</span><span id="sys_threshold">--</span></div>
    <div class="inline-stat"><span>熔断</span><span id="sys_cb">--</span></div>
    <div class="inline-stat"><span>当日盈亏</span><span id="sys_daily_pnl">--</span></div>
    <div class="inline-stat"><span>候选池</span><span id="sys_pool">--</span></div>
    <div class="inline-stat"><span>保护单</span><span id="sys_orders">--</span></div>
    <div class="inline-stat"><span>保证金监控</span><span id="sys_margin_mon">--</span></div>
  </div>

  <div class="card">
    <h2>当前持仓 <span class="hint" id="hint_pos"></span></h2>
    <div id="positions"><p style="text-align:center;padding:24px;color:#666;">暂无持仓</p></div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>交易绩效 <span class="hint" id="hint_perf"></span></h2>
    <div id="report">
      <div class="inline-stat"><span>7天净盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>30天净盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>累计净盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>今日净盈亏</span><span>--</span></div>
      <div class="inline-stat"><span>手续费</span><span>--</span></div>
      <div class="inline-stat"><span>资金费率</span><span>--</span></div>
    </div>
  </div>

  <div class="card">
    <h2>信号日志 <span class="hint" id="hint_sig"></span></h2>
    <div id="signal_log"><p style="text-align:center;padding:24px;color:#666;">暂无信号</p></div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>候选池评分明细 <span class="hint">Top-5 多因子投票</span></h2>
    <div id="scoring_detail"><p style="text-align:center;padding:24px;color:#666;">等待扫描器产出</p></div>
  </div>
  <div class="card">
    <h2>近期成交 <span class="hint" id="hint_trades"></span></h2>
    <div id="trade_history"><p style="text-align:center;padding:24px;color:#666;">暂无成交</p></div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>每日盈亏走势 <span class="hint" id="hint_daily"></span></h2>
    <div id="daily_pnl"><p style="text-align:center;padding:24px;color:#666;">等待数据...</p></div>
  </div>
</div>

<div id="log_panel">
  <h2>服务器日志 <span class="hint" id="hint_log"></span></h2>
  <div id="log_lines"><p style="text-align:center;color:#666;">加载中...</p></div>
</div>

<div class="footer">
  <span>CryptoPilot V2 · 多因子评分引擎</span>
  <span>5s刷新 · 更新: <span id="last_update">--</span></span>
</div>

<script>
const REFRESH_MS=5000;let countdown=REFRESH_MS/1000;
function esc(s){if(typeof s!=='string')s=String(s);return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function fmtUSD(v){const n=parseFloat(v);if(isNaN(n))return'--';return n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}
function fmtPct(v){const n=parseFloat(v);if(isNaN(n))return'--';return(n>=0?'+':'')+n.toFixed(2)+'%'}
function fmtNum(v,d){d=d||2;const n=parseFloat(v);if(isNaN(n))return'--';return n.toFixed(d)}
function cn(v){const n=parseFloat(v);if(isNaN(n)||n===0)return'zero';return n>0?'pnl-pos':'pnl-neg'}
function marginLabel(t){return t==='ISOLATED'||t==='isolated'?'🔒 逐仓':'🌐 全仓'}

async function load(){
  const now=new Date();
  document.getElementById('timestamp').textContent=now.toLocaleString();
  document.getElementById('last_update').textContent=now.toLocaleTimeString();
  countdown=REFRESH_MS/1000;

  try{
    const r=await fetch('/health/account');const d=await r.json();
    if(!d.error){
      const cards=document.querySelectorAll('#account_bar .stat-card');
      cards[0].querySelector('.value').textContent=fmtUSD(d.total_balance);
      cards[1].querySelector('.value').textContent=fmtUSD(d.available_balance);
      const upnl=document.getElementById('stat_upnl');
      upnl.textContent=fmtUSD(d.unrealized_pnl);
      upnl.style.color=d.unrealized_pnl>=0?'#03904a':'#da291c';
      const mr=document.getElementById('stat_margin');
      mr.textContent=d.margin_ratio_str||d.margin_display||((d.margin_ratio||0)*100).toFixed(2)+'%';
      // 维持保证金子行
      if(d.maintenance_margin>0){
        mr.nextElementSibling.textContent='维持 '+fmtUSD(d.maintenance_margin);
      }
      // 余额卡片: 加保证金余额子行
      if(d.margin_balance>0){
        cards[0].querySelector('.sub').innerHTML='USDT <span style=\"color:#8fa4b8\">│ 保证金 '+fmtUSD(d.margin_balance)+'</span>';
      }
      document.getElementById('stat_mtype').textContent=marginLabel(d.margin_type||'cross');
    }
  }catch(e){}

  try{
    const r=await fetch('/health/positions?_='+Date.now());const d=await r.json();
    if(!d.error)document.getElementById('stat_poscount').textContent=d.count+' / '+(window.maxPositions||5);
  }catch(e){}

  try{
    const[hR,cbR,acctR,pnlR,ordR,candR,stratR]=await Promise.all([
      fetch('/health'),fetch('/health/circuit'),fetch('/health/account'),
      fetch('/health/pnl'),fetch('/health/orders?_='+Date.now()),
      fetch('/health/candidates'),fetch('/health/strategy')
    ]);
    const hD=await hR.json(),cbD=await cbR.json(),acctD=await acctR.json();
    const pnlD=await pnlR.json(),ordD=await ordR.json();
    const candD=await candR.json(),stratD=await stratR.json();

    document.getElementById('sys_ws').innerHTML=hD.websocket_connected
      ?'<span class="conn-dot ok pulse"></span>WebSocket'
      :'<span class="conn-dot err"></span>断开';
    document.getElementById('hint_sys').textContent='v'+hD.version;

    if(!stratD.error){
      document.getElementById('sys_preset').innerHTML='<span class="badge badge-purple">'+esc(stratD.preset||'composite')+'</span>';
      document.getElementById('sys_threshold').innerHTML='买入≥'+stratD.buy_threshold+' 卖出≤'+stratD.sell_threshold;
    }

    const tripped=cbD.tripped;
    document.getElementById('sys_cb').innerHTML=tripped?'<span class="badge badge-err">已熔断</span>':'<span class="badge badge-ok">正常</span>';
    document.getElementById('sys_daily_pnl').innerHTML='<span class="'+cn(pnlD.net_pnl_1d||0)+'">'+fmtUSD(pnlD.net_pnl_1d||0)+'</span>';
    document.getElementById('stat_cb').textContent=tripped?'已熔断':'正常';
    document.getElementById('stat_cb').style.color=tripped?'#da291c':'#03904a';

    document.getElementById('sys_pool').textContent=(candD&&candD.total||0)+' 个候选';

    let slCount=0,tpCount=0,totalOrders=0;
    if(!ordD.error&&ordD.by_symbol){
      ordD.by_symbol.forEach(s=>{slCount+=s.stop_orders;tpCount+=s.tp_orders;totalOrders+=s.total});
    }
    document.getElementById('sys_orders').innerHTML=(slCount>0||tpCount>0)
      ?'<span class="badge badge-ok">SL:'+slCount+' TP:'+tpCount+'</span> 共'+totalOrders+'单'
      :'<span class="badge badge-err" style="animation:pulse 1s infinite">⚠ 无保护单</span>';
    window._ordBySymbol=ordD.by_symbol||[];

    try{
      const mgR=await fetch('/health/margin');const mgD=await mgR.json();
      if(!mgD.error){
        document.getElementById('sys_margin_mon').innerHTML=mgD.running
          ?'<span class="badge badge-ok">运行</span> '+(mgD.warning_threshold*100).toFixed(0)+'%/'+(mgD.critical_threshold*100).toFixed(0)+'%'
          :'<span class="badge badge-err">未启动</span>';
      }
    }catch(e){}

    const net7=pnlD.net_pnl_7d||0,net30=pnlD.net_pnl_30d||0;
    const netTotal=pnlD.net_pnl_total||0,net1d=pnlD.net_pnl_1d||0;
    document.getElementById('report').innerHTML=
      '<div class="inline-stat"><span>7天净盈亏</span><span class="'+cn(net7)+' value-big">'+fmtUSD(net7)+'</span></div>'+
      '<div class="inline-stat"><span>30天净盈亏</span><span class="'+cn(net30)+' value-big">'+fmtUSD(net30)+'</span></div>'+
      '<div class="inline-stat"><span>累计净盈亏</span><span class="'+cn(netTotal)+' value-big">'+fmtUSD(netTotal)+'</span></div>'+
      '<div class="inline-stat"><span>今日净盈亏</span><span class="'+cn(net1d)+' value-big">'+fmtUSD(net1d)+'</span></div>'+
      '<div class="inline-stat"><span>手续费</span><span>'+fmtUSD(pnlD.commission_7d||0)+'</span></div>'+
      '<div class="inline-stat"><span>资金费率</span><span>'+fmtUSD(pnlD.funding_7d||0)+'</span></div>'+
      '<div class="inline-stat"><span>交易币种</span><span>'+(pnlD.symbols_traded||0)+'</span></div>';
    document.getElementById('hint_perf').textContent='含手续费+资金费率';
  }catch(e){document.getElementById('sys_ws').innerHTML='<span class="conn-dot err"></span>连接失败'}

  let protBySymbol={};
  (window._ordBySymbol||[]).forEach(s=>{protBySymbol[s.symbol]={sl:s.stop_orders,tp:s.tp_orders,total:s.total}});
  try{
    const r=await fetch('/health/positions?_='+Date.now());const d=await r.json();
    if(!d.error&&d.positions&&d.positions.length>0){
      let html='<div class="scroll-table"><table><tr><th>币种</th><th>方向</th><th>数量</th><th>杠杆</th><th>模式</th><th>开仓价</th><th>标记价</th><th>未实现盈亏</th><th>ROI</th><th>强平价</th><th>保护单</th><th>预估SL/TP</th></tr>';
      d.positions.forEach(p=>{
        const pnl=parseFloat(p.unrealized_pnl||0);
        const roi=parseFloat(p.roi_pct||0);
        const side=(p.side||'').toUpperCase();
        const lev=p.leverage||1;
        const mtype=p.margin_type||'cross';
        const liq=p.liquidation_price||0;
        const entry=parseFloat(p.entry_price||0);
        const qty=parseFloat(p.qty||0);
        const prot=protBySymbol[p.symbol]||{sl:0,tp:0};
        const protHtml=(prot.sl>0||prot.tp>0)
          ?'<span class="badge badge-ok">SL:'+prot.sl+' TP:'+prot.tp+'</span>'
          :'<span class="badge badge-err" style="animation:pulse 1s infinite">裸仓!</span>';
        // 预估 SL/TP 盈亏
        const slPrice=parseFloat(p.sl_price||0);
        const tpPrice=parseFloat(p.tp_price||0);
        let slPnl=0,tpPnl=0;
        if(side==='LONG'){
          slPnl=slPrice>0?(slPrice-entry)*Math.abs(qty):0;
          tpPnl=tpPrice>0?(tpPrice-entry)*Math.abs(qty):0;
        }else{
          slPnl=slPrice>0?(entry-slPrice)*Math.abs(qty):0;
          tpPnl=tpPrice>0?(entry-tpPrice)*Math.abs(qty):0;
        }
        const slPnlHtml=slPrice>0?'<span style="color:#da291c">SL:'+fmtUSD(slPnl)+'</span>':'--';
        const tpPnlHtml=tpPrice>0?'<span style="color:#03904a">TP:'+fmtUSD(tpPnl)+'</span>':'--';
        const estPnlHtml=slPnlHtml+' / '+tpPnlHtml;
        html+='<tr>'+
          '<td><strong>'+esc(p.symbol)+'</strong></td>'+
          '<td><span class="badge '+(side==='LONG'?'badge-long':'badge-short')+'">'+side+'</span></td>'+
          '<td>'+fmtNum(p.qty,3)+'</td>'+
          '<td>'+lev+'x</td>'+
          '<td>'+marginLabel(mtype)+'</td>'+
          '<td>'+fmtNum(p.entry_price,5)+'</td>'+
          '<td>'+fmtNum(p.mark_price,5)+'</td>'+
          '<td class="'+cn(pnl)+'">'+fmtUSD(pnl)+'</td>'+
          '<td class="'+cn(roi)+'">'+fmtPct(roi)+'</td>'+
          '<td style="color:#da291c">'+(liq>0?fmtNum(liq,5):'--')+'</td>'+
          '<td>'+protHtml+'</td>'+
          '<td class="nowrap">'+estPnlHtml+'</td></tr>';
      });
      html+='</table></div>';
      document.getElementById('positions').innerHTML=html;
      document.getElementById('hint_pos').textContent=d.count+' / '+(window.maxPositions||5)+' 个';
    }else{document.getElementById('positions').innerHTML='<p style="text-align:center;padding:24px;color:#666;">暂无持仓</p>'}
  }catch(e){}

  try{
    const r=await fetch('/health/trades');const d=await r.json();
    if(!d.error&&d.trades&&d.trades.length>0){
      let html='<div class="scroll-table"><table><tr><th>时间</th><th>币种</th><th>方向</th><th>价格</th><th>数量</th><th>手续费</th><th>策略</th></tr>';
      d.trades.slice(0,30).forEach(t=>{
        const side=(t.side||'').toUpperCase();
        const sideCls=side==='BUY'?'badge-long':'badge-short';
        const tm=t.filled_at?new Date(t.filled_at).toLocaleTimeString():'-';
        const strat=esc(t.strategy_name||t.type||'-');
        html+='<tr><td class="nowrap">'+tm+'</td>'+
          '<td><strong>'+esc(t.symbol)+'</strong></td>'+
          '<td><span class="badge '+sideCls+'">'+side+'</span></td>'+
          '<td>'+fmtNum(t.price,5)+'</td><td>'+fmtNum(t.qty,4)+'</td>'+
          '<td>'+fmtNum(t.commission,6)+'</td>'+
          '<td class="truncate" title="'+strat+'">'+strat+'</td></tr>';
      });
      html+='</table></div>';
      document.getElementById('trade_history').innerHTML=html;
      document.getElementById('hint_trades').textContent=d.total+' 笔';
    }
  }catch(e){}

  try{
    const r=await fetch('/health/scoring-detail');const d=await r.json();
    if(!d.error&&d.candidates&&d.candidates.length>0){
      let html='<div class="scroll-table"><table><tr><th>币种</th><th>价格</th><th>涨跌</th><th>扫描分</th><th>综合评分</th><th>方向</th><th>置信度</th></tr>';
      d.candidates.forEach(c=>{
        const changeCls=parseFloat(c.change_24h)>=0?'pnl-pos':'pnl-neg';
        let dirBadge='<span class="badge badge-info">HOLD</span>';
        if(c.direction==='LONG')dirBadge='<span class="badge badge-long">LONG</span>';
        else if(c.direction==='SHORT')dirBadge='<span class="badge badge-short">SHORT</span>';
        const totalScore=c.composite_score||c.total_score||c.score||0;
        html+='<tr><td><strong style="color:#ffffff">'+esc(c.symbol)+'</strong></td>'+
          '<td>'+fmtNum(c.price,4)+'</td>'+
          '<td class="'+changeCls+'">'+fmtPct(c.change_24h)+'</td>'+
          '<td><span class="badge badge-teal">'+c.scanner_score+'</span></td>'+
          '<td><span class="badge badge-purple">'+Math.round(totalScore)+'</span></td>'+
          '<td>'+dirBadge+'</td>'+
          '<td>'+fmtPct(c.confidence||0)+'</td></tr>';
      });
      html+='</table></div>';
      document.getElementById('scoring_detail').innerHTML=html;
    }
  }catch(e){}

  try{
    const r=await fetch('/health/signals');const d=await r.json();
    if(!d.error&&d.signals&&d.signals.length>0){
      let html='<div class="scroll-table"><table><tr><th>时间</th><th>币种</th><th>动作</th><th>评分</th><th>说明</th></tr>';
      d.signals.slice().reverse().slice(0,25).forEach(s=>{
        const act=s.action||'';let actCls='badge-info';
        if(act.includes('LONG'))actCls='badge-long';
        else if(act.includes('SHORT'))actCls='badge-short';
        const tm=s.time?new Date(s.time).toLocaleTimeString():'-';
        html+='<tr><td class="nowrap">'+tm+'</td>'+
          '<td><strong>'+esc(s.symbol)+'</strong></td>'+
          '<td><span class="badge '+actCls+'">'+esc(act)+'</span></td>'+
          '<td>'+(s.score||'-')+'</td>'+
          '<td class="truncate" title="'+esc(s.detail||'')+'">'+esc(s.detail||'-')+'</td></tr>';
      });
      html+='</table></div>';
      document.getElementById('signal_log').innerHTML=html;
      document.getElementById('hint_sig').textContent=d.total+' 条';
    }
  }catch(e){}

  try{
    const r=await fetch('/health/report/30d');const d=await r.json();
    if(!d.error&&d.daily_pnl&&d.daily_pnl.length>0){
      const bars=d.daily_pnl;const maxAbs=Math.max(...bars.map(b=>Math.abs(b.pnl)),0.01);
      let html='<div style="display:flex;align-items:flex-end;gap:2px;height:100px;overflow-x:auto;padding:6px 0">';
      bars.forEach(b=>{
        const h=Math.max(4,(Math.abs(b.pnl)/maxAbs*85));
        html+='<div title="'+esc(b.date)+': '+fmtUSD(b.pnl)+' ('+b.trades+'笔)" class="daily-bar '+(b.pnl>=0?'daily-bar-pos':'daily-bar-neg')+'" style="height:'+h+'px;flex:0 0 14px"></div>';
      });
      html+='</div><div style="font-size:12px;color:#666;margin-top:6px;text-align:center">30天盈亏柱状图</div>';
      document.getElementById('daily_pnl').innerHTML=html;
    }
  }catch(e){}
}

function tick(){countdown-=1;if(countdown<=0)countdown=REFRESH_MS/1000}

async function loadLogs(){
  try{
    const r=await fetch('/health/logs?lines=40');const d=await r.json();
    if(!d.error&&d.lines&&d.lines.length>0){
      const container=document.getElementById('log_lines');
      let html='';
      d.lines.forEach(l=>{
        const cls='log-'+esc(l.level||'INFO');
        html+='<div class="log-line"><span class="lt">'+esc(l.time||'')+'</span><span class="'+cls+'">'+esc(l.msg||'')+'</span></div>';
      });
      container.innerHTML=html;
      container.scrollTop=container.scrollHeight;
      document.getElementById('hint_log').textContent=(d.file||'')+' ('+d.lines.length+'行)';
    }
  }catch(e){}
}
setInterval(loadLogs,3000);
loadLogs();

setInterval(tick,1000);
load();setInterval(load,REFRESH_MS);
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
