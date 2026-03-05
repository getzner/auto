"""
dashboard.py &#8212; Cost & Performance Dashboard
Served via FastAPI at /dashboard
Beautiful dark-mode HTML with charts for LLM costs per agent.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trade Server &#8212; Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    --bg:       #0a0e1a;
    --surface:  #111827;
    --border:   #1f2937;
    --accent:   #6366f1;
    --accent2:  #10b981;
    --warn:     #f59e0b;
    --danger:   #ef4444;
    --text:     #f1f5f9;
    --muted:    #64748b;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 24px;
  }

  header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 32px;
  }
  header .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--accent2);
    box-shadow: 0 0 8px var(--accent2);
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  h1 { font-size: 1.4rem; font-weight: 600; }
  .subtitle { color: var(--muted); font-size: .85rem; margin-top: 2px; }

  .stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }

  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }
  .stat-card::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: var(--accent);
  }
  .stat-card.green::before { background: var(--accent2); }
  .stat-card.warn::before  { background: var(--warn); }

  .stat-label { font-size: .75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
  .stat-value { font-size: 2rem; font-weight: 700; margin: 6px 0 2px; font-family: 'JetBrains Mono', monospace; }
  .stat-sub   { font-size: .8rem; color: var(--muted); }

  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 28px;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }
  .card-title {
    font-size: .85rem;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .06em;
    margin-bottom: 16px;
  }

  .agent-table { width: 100%; border-collapse: collapse; font-size: .875rem; }
  .agent-table th {
    text-align: left; padding: 8px 10px;
    color: var(--muted); font-weight: 500; font-size: .75rem;
    border-bottom: 1px solid var(--border);
  }
  .agent-table td {
    padding: 10px 10px;
    border-bottom: 1px solid rgba(255,255,255,.04);
    font-family: 'JetBrains Mono', monospace;
    font-size: .8rem;
  }
  .agent-table tr:hover td { background: rgba(99,102,241,.06); }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: .7rem;
    font-weight: 600;
  }
  .badge-green { background: rgba(16,185,129,.15); color: var(--accent2); }
  .badge-purple { background: rgba(99,102,241,.15); color: var(--accent); }
  .badge-warn { background: rgba(245,158,11,.15); color: var(--warn); }

  .bar-wrap { background: rgba(255,255,255,.05); border-radius: 4px; height: 6px; width: 100%; }
  .bar-fill  { height: 6px; border-radius: 4px; background: var(--accent); }

  /* &#9472;&#9472; Service Status Spheres &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472; */
  .services-bar {
    display: flex;
    gap: 16px;
    align-items: center;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 18px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }
  .service-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: .8rem;
    color: var(--muted);
  }
  .sphere {
    width: 12px; height: 12px;
    border-radius: 50%;
    position: relative;
    flex-shrink: 0;
  }
  .sphere.ok {
    background: #10b981;
    box-shadow: 0 0 0 0 rgba(16,185,129,0.7);
    animation: ripple-green 1.8s ease-in-out infinite;
  }
  .sphere.error {
    background: #ef4444;
    box-shadow: 0 0 0 0 rgba(239,68,68,0.7);
    animation: ripple-red 1.8s ease-in-out infinite;
  }
  .sphere.checking {
    background: #f59e0b;
    animation: blink-warn .8s step-start infinite;
  }
  @keyframes ripple-green {
    0%   { box-shadow: 0 0 0 0 rgba(16,185,129,0.7); }
    70%  { box-shadow: 0 0 0 8px rgba(16,185,129,0); }
    100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
  }
  @keyframes ripple-red {
    0%   { box-shadow: 0 0 0 0 rgba(239,68,68,0.7); }
    70%  { box-shadow: 0 0 0 8px rgba(239,68,68,0); }
    100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
  }
  @keyframes blink-warn { 50% { opacity: 0.2; } }
  .services-label {
    font-size: .7rem;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-right: 4px;
  }
  .services-divider {
    width: 1px; height: 20px;
    background: var(--border);
  }

  canvas { max-height: 220px; }

  /* &#9472;&#9472; Skill Marketplace &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472; */
  .skill-card {
    border: 1px dashed var(--accent);
    background: rgba(99,102,241,.03);
  }
  .skill-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px;
    background: rgba(255,255,255,.05);
    border-radius: 8px;
    border: 1px solid var(--border);
    transition: transform .2s;
  }
  .skill-item:hover { transform: translateY(-2px); border-color: var(--accent); }
  .skill-item.active { border-color: var(--accent2); background: rgba(16,185,129,.05); }

  /* &#9472;&#9472; Live Log Viewer &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472; */
  .log-viewer {
    background: #060a0f;
    border: 1px solid #1f2937;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 28px;
    font-family: 'JetBrains Mono', monospace;
    font-size: .7rem; /* Smaller as requested */
    line-height: 1.5;
    overflow-y: auto;
    max-height: 400px;
    position: relative;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }
  .log-viewer::-webkit-scrollbar { width: 6px; }
  .log-viewer::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
  
  .log-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  .log-line { padding: 2px 0; white-space: pre-wrap; word-break: break-all; border-bottom: 1px solid rgba(255,255,255,0.02); }
  
  .log-scanner  { color: #a78bfa; }
  .log-monitor  { color: #34d399; }
  .log-risk-ok  { color: #10b981; font-weight: 600; }
  .log-risk-err { color: #f87171; font-weight: 600; }
  .log-orc      { color: #6366f1; }
  .log-llm      { color: #f59e0b; font-style: italic; }
  .log-skill    { color: #ec4899; }
  .log-other    { color: #94a3b8; }

  .log-blink {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--accent2);
    box-shadow: 0 0 8px var(--accent2);
    animation: blink-dot 1s step-start infinite;
  }
  @keyframes blink-dot { 50% { opacity: 0; } }

  /* &#9472;&#9472; Config Styles (Missing from last edit) &#9472;&#9472; */
  .config-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
  }
  .config-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px;
    background: rgba(255,255,255,.02);
    border-radius: 8px;
    border: 1px solid var(--border);
  }
  .config-item select, .config-item input {
    background: #1f2937;
    color: var(--text);
    border: 1px solid var(--border);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: .75rem;
    outline: none;
  }
  .btn-save {
    background: var(--accent);
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    font-size: .8rem;
    font-weight: 600;
    cursor: pointer;
    transition: all .2s;
  }
  .btn-save:hover { background: #4f46e5; transform: translateY(-1px); }
  .btn-save:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-save:disabled { opacity: 0.4; cursor: not-allowed; }

  /* &#9472;&#9472; Trade Journal Cards &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472; */
  .journal-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 20px;
    margin-bottom: 32px;
  }
  .journal-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    border-top: 4px solid var(--accent);
  }
  .journal-card.high-score { border-top-color: var(--accent2); }
  .journal-card.low-score  { border-top-color: var(--danger); }
  
  .journal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  .journal-score {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.2rem;
    font-weight: 700;
  }
  .journal-summary { font-size: .85rem; line-height: 1.5; color: var(--text); margin-bottom: 12px; }
  .journal-lessons {
    list-style: none;
    font-size: .75rem;
    color: var(--muted);
    padding-left: 0;
  }
  .journal-lessons li {
    margin-bottom: 4px;
    padding-left: 14px;
    position: relative;
  }
  .journal-lessons li::before {
    content: '&#8594;';
    position: absolute; left: 0; color: var(--accent);
  }
  .journal-critique {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(255,255,255,.05);
    font-size: .75rem;
    font-style: italic;
    color: var(--muted);
  }

  /* &#129514; Skill Evolution UI &#129514; */
  .btn-feedback {
    background: none;
    border: 1px solid var(--border);
    color: var(--muted);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
    margin-right: 4px;
  }
  .btn-feedback:hover { border-color: var(--accent); color: var(--accent); background: rgba(0, 243, 255, 0.05); }
  .btn-feedback.active { background: var(--accent); color: black; border-color: var(--accent); }
  .btn-feedback.down:hover { border-color: var(--danger); color: var(--danger); background: rgba(239, 68, 68, 0.05); }
  .btn-feedback.down.active { background: var(--danger); color: white; border-color: var(--danger); }

  .skill-group {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
  }
  .skill-model-select {
    background: #1a1b1e;
    border: 1px solid #333;
    color: var(--text);
    font-size: 0.75rem;
    padding: 2px 4px;
    border-radius: 4px;
    outline: none;
    margin-left: 8px;
    flex-shrink: 0;
  }
</style>
</head>
<body>

<header>
  <div class="dot"></div>
  <div>
    <h1>Trade Server Dashboard</h1>
    <div class="subtitle" id="lastUpdate">Loading...</div>
  </div>
</header>

<!-- Service Status Bar -->
<div class="services-bar" id="servicesBar">
  <span class="services-label">Services</span>
  <div class="services-divider"></div>
  <div class="service-item"><div class="sphere checking" id="sphere-main"></div><span id="label-main">Main Engine</span></div>
  <div class="service-item"><div class="sphere checking" id="sphere-server"></div><span id="label-server">API Server</span></div>
  <div class="service-item"><div class="sphere checking" id="sphere-postgres"></div><span id="label-postgres">Postgres</span></div>
  <div class="service-item"><div class="sphere checking" id="sphere-redis"></div><span id="label-redis">Redis</span></div>
  <div class="service-item"><div class="sphere checking" id="sphere-ollama"></div><span id="label-ollama">Ollama</span></div>
  <div class="services-divider"></div>
  <span class="services-label">Mode</span>
  <div class="service-item"><div class="sphere" id="sphere-mode"></div><span id="label-mode">Initializing...</span></div>
  <div class="services-divider"></div>
  <span class="services-label" style="color:var(--accent)">Macro Regime</span>
  <div class="service-item"><span id="label-regime" style="color:var(--accent); font-weight:700; text-transform:uppercase; letter-spacing:1px">&#8212;</span></div>
  <div class="services-divider"></div>
  <span class="services-label">Agents</span>
  <div class="service-item"><div class="sphere checking" id="sphere-stop_monitor"></div><span id="label-stop_monitor">Stop Monitor</span></div>
  <div class="service-item"><div class="sphere checking" id="sphere-scanner"></div><span id="label-scanner">Scanner</span></div>
  <div class="services-divider"></div>
  <span style="font-size:.75rem;color:var(--muted)" id="healthTs">Checking...</span>
</div>

<!-- Stats row -->
<div class="stats-row" id="statsRow">
  <div class="stat-card"><div class="stat-label">Total LLM Cost</div><div class="stat-value" id="totalCost">&#8212;</div><div class="stat-sub">all time</div></div>
  <div class="stat-card warn"><div class="stat-label">Total LLM Calls</div><div class="stat-value" id="totalCalls">&#8212;</div><div class="stat-sub">all agents</div></div>
  <div class="stat-card green"><div class="stat-label">Portfolio Equity</div><div class="stat-value" id="equity">&#8212;</div><div class="stat-sub" id="totalPnl">&#8212;</div></div>
  <div class="stat-card green"><div class="stat-label">Today P&L</div><div class="stat-value" id="todayPnl">&#8212;</div><div class="stat-sub">paper trading</div></div>
</div>

<!-- Trade Performance stats -->
<div class="stats-row" style="margin-bottom:28px">
  <div class="stat-card green"><div class="stat-label">Win Rate</div><div class="stat-value" id="winRate">&#8212;</div><div class="stat-sub" id="winRateSub">&#8212; trades</div></div>
  <div class="stat-card warn"><div class="stat-label">Est. Bybit Fees</div><div class="stat-value" id="tradeFees">&#8212;</div><div class="stat-sub">0.06% taker &#215; 2</div></div>
  <div class="stat-card"><div class="stat-label">Closed P&L</div><div class="stat-value" id="closedPnl">&#8212;</div><div class="stat-sub">after fees</div></div>
  <div class="stat-card warn"><div class="stat-label">Net (P&L &#8722; Fees)</div><div class="stat-value" id="netPnl">&#8212;</div><div class="stat-sub">all closed trades</div></div>
</div>

<!-- Model Settings & Skill Marketplace -->
<div class="grid-2">
  <div class="card">
    <div class="card-title">Core Model Switcher</div>
    <div class="config-grid" id="modelConfigGrid" style="grid-template-columns: 1fr;">
      <div style="color:var(--muted); font-size:.8rem">Loading core models...</div>
    </div>
  </div>
  
  <div class="card skill-card">
    <div class="card-title">Skill Marketplace &#8212; Additional Analysts</div>
    <div class="config-grid" id="skillConfigGrid" style="grid-template-columns: 1fr;">
      <div style="color:var(--muted); font-size:.8rem">Loading skills...</div>
    </div>
  </div>
</div>

<!-- &#9881;&#65039; NEW: System Strategy & Risk Tuning &#9881;&#65039; -->
<div class="card" style="margin-bottom:28px; border-top: 4px solid var(--accent2)">
  <div class="card-title" style="display:flex; justify-content:space-between">
    <span>&#9881;&#65039; System Strategy & Risk Tuning</span>
    <span id="systemConfigStatus" style="font-size:.7rem; text-transform:none; color:var(--accent2)"></span>
  </div>
  <div class="config-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px;">
    <div class="config-group">
      <div class="stat-label" style="margin-bottom:8px">Risk Management</div>
      <div class="config-item"><span>Min Confidence (0-10)</span><input type="number" step="0.5" id="conf-min" oninput="enableSysSave()"></div>
      <div class="config-item"><span>Max Risk %</span><input type="number" step="0.1" id="risk-max" oninput="enableSysSave()"></div>
      <div class="config-item"><span>Max Positions</span><input type="number" id="pos-max" oninput="enableSysSave()"></div>
    </div>
    <div class="config-group">
      <div class="stat-label" style="margin-bottom:8px">Scanner Thresholds</div>
      <div class="config-item"><span>Volume Spike Multi</span><input type="number" step="0.1" id="scan-vol" oninput="enableSysSave()"></div>
      <div class="config-item"><span>Trigger Threshold</span><input type="number" id="scan-trig" oninput="enableSysSave()"></div>
      <div class="config-item"><span>Volatility Z-Score</span><input type="number" step="0.1" id="scan-z" oninput="enableSysSave()"></div>
    </div>
  </div>
  <div style="margin-top:16px; text-align:right">
    <button class="btn-save" id="saveSysConfigBtn" onclick="saveSystemConfig()" disabled>Apply Parameters</button>
  </div>
</div>

<!-- &#129351; Agent Debate & Sparring Room &#129351; -->
<div class="card" style="margin-bottom:28px; border-top: 4px solid var(--accent)">
  <div class="card-title" style="display:flex; justify-content:space-between; align-items:center">
    <span>&#129351; Agent Debate & Sparring Room</span>
    <span id="agentMemoryBadge" style="font-size:.65rem; padding:3px 8px; border-radius:12px; background:rgba(16,185,129,0.15); color:var(--accent2); border:1px solid var(--accent2); display:none">Memory Loaded</span>
  </div>
  <p style="font-size: 0.8rem; color: var(--muted); margin-bottom: 15px;">
    Spar, debatteer en train rechtstreeks met een agent. De agent verdedigt zijn visie maar leert van jou.
    Alles wat gesaved wordt, gaat naar zijn <strong>MD geheugen</strong> &#233;n <strong>ChromaDB</strong> (semantisch geheugen).
  </p>

  <!-- Agent selector met expertise badge -->
  <div style="display:flex; gap:12px; align-items:center; margin-bottom:15px; flex-wrap:wrap">
    <select id="agentSelect" style="flex-grow:1; max-width:280px; padding:8px 12px; border-radius:6px;
      background:rgba(0,0,0,0.5); color:var(--text); border:1px solid var(--border); font-size:.85rem"
      onchange="onAgentChange()">
      <option value="orchestrator">&#127932; Orchestrator (Opperbaas)</option>
      <option value="gametheory_analyst">&#128051; GameTheory Analyst</option>
      <option value="volume_analyst">&#128200; Volume & CVD Analyst</option>
      <option value="orderflow_analyst">&#9889; Orderflow Analyst</option>
      <option value="news_analyst">&#128240; News & Sentiment Analyst</option>
      <option value="vp_analyst">&#127919; Volume Profile Analyst</option>
      <option value="onchain_analyst">&#9939; On-Chain Detective</option>
      <option value="risk_manager">&#128737;&#65039; Risk Manager</option>
      <option value="meta_agent">&#129504; Meta-Agent</option>
    </select>
    <div id="agentExpertise" style="font-size:.75rem; color:var(--muted); font-style:italic; flex:1; min-width:200px"></div>
  </div>

  <!-- Chat history -->
  <div id="chatHistory" style="height:380px; overflow-y:auto; background:rgba(0,0,0,0.35);
    border:1px solid var(--border); border-radius:8px; padding:16px;
    display:flex; flex-direction:column; gap:12px; margin-bottom:12px; scroll-behavior:smooth">
    <div id="chatPlaceholder" style="text-align:center; color:var(--muted); font-size:.8rem; margin:auto">
      Selecteer een agent en start het debat...
    </div>
  </div>

  <!-- Input area -->
  <div style="display:flex; gap:8px; margin-bottom:10px">
    <textarea id="chatInput" rows="2"
      placeholder="Stel een vraag, daag uit, spar... (Enter = verstuur, Shift+Enter = nieuwe regel)"
      style="flex-grow:1; padding:10px 14px; border-radius:6px; background:rgba(0,0,0,0.5);
        color:var(--text); border:1px solid var(--border); resize:vertical; font-size:.85rem; font-family:inherit"
      onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault(); sendChatMessage();}"></textarea>
    <div style="display:flex; flex-direction:column; gap:6px">
      <button class="btn-save" onclick="sendChatMessage()"
        style="background:var(--accent2); color:black; height:50%; font-size:.8rem">&#9654; Stuur</button>
      <button class="btn-save" onclick="clearChat()"
        style="background:rgba(255,255,255,0.08); font-size:.8rem">&#128465; Wis</button>
    </div>
  </div>

  <!-- Save to memory -->
  <div style="display:flex; justify-content:space-between; align-items:center;
    border-top:1px solid var(--border); padding-top:12px">
    <div>
      <span id="chatStatus" style="font-size:.78rem; color:var(--muted)"></span>
    </div>
    <button class="btn-save" onclick="saveChatToMemory()"
      style="background:var(--accent); color:white">
      &#128190; Sla op als Geheugen (MD + ChromaDB)
    </button>
  </div>
</div>


<!-- &#128736; System Control Center &#128736; -->
<div class="card" style="margin-bottom:28px; border-top: 4px solid var(--warn)">
  <div class="card-title">&#128736; System Control Center</div>
  <div style="display:flex; gap:16px; align-items:center; flex-wrap:wrap">
    <button class="btn-save" style="background:var(--warn); color:black" onclick="confirmRestart()">Restart All Services</button>
    <button class="btn-save" style="background:var(--danger); color:white" onclick="confirmKillGhosts()">Kill Ghost Processes &#128123;</button>
    <button class="btn-save" onclick="reloadConfig()">Reload Configuration</button>
    <div style="flex-grow:1"></div>
    <div style="font-size:.75rem; color:var(--muted)">
       PID: <span id="serverPid" style="font-family:monospace; color:var(--text)">&#8212;</span> | 
       Uptime: <span id="uptime" style="color:var(--text)">&#8212;</span>
    </div>
  </div>
  <div id="controlStatus" style="font-size:.75rem; margin-top:12px; height:1rem"></div>
</div>

<div style="margin-bottom: 28px; display: flex; justify-content: space-between; align-items: center;">
    <div>
        <button class="btn-save" style="background: var(--danger); border: 2px solid #ff0000; box-shadow: 0 0 10px rgba(239, 68, 68, 0.3);" id="killSwitchBtn" onclick="toggleKillSwitch()">
            EMERGENCY KILL SWITCH
        </button>
        <span id="safetyStatus" style="font-size: .85rem; font-weight: 700; margin-left:12px; text-transform:uppercase"></span>
    </div>
    <div style="text-align: right;">
        <span id="saveStatus" style="font-size: .8rem; margin-right:16px"></span>
        <button class="btn-save" id="saveConfigBtn" onclick="saveAllConfig()" disabled>Save All Configurations</button>
    </div>
</div>

<!-- Charts row -->
<div class="grid-2">
  <div class="card">
    <div class="card-title">Daily LLM Cost (30 days)</div>
    <canvas id="dailyChart"></canvas>
  </div>
  <div class="card">
    <div class="card-title">Cost per Agent</div>
    <canvas id="agentChart"></canvas>
  </div>
</div>

<!-- Agent breakdown table -->
<div class="card" style="margin-bottom:28px">
  <div class="card-title">Agent Cost Breakdown</div>
  <table class="agent-table">
    <thead>
      <tr>
        <th>Agent</th>
        <th>Model</th>
        <th>Calls</th>
        <th>Input tokens</th>
        <th>Output tokens</th>
        <th>Cost (USD)</th>
        <th>Share</th>
      </tr>
    </thead>
    <tbody id="agentTableBody"></tbody>
  </table>
</div>

<!-- Live Log Viewer -->
<div style="margin-bottom:28px">
  <div class="log-header">
    <div style="display:flex;align-items:center;gap:10px">
      <div class="log-blink"></div>
      <span style="font-size:.8rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em">Live Log</span>
      <span style="font-size:.7rem;color:var(--muted)" id="logFilter">SCANNER | MONITOR | RISK</span>
    </div>
    <span style="font-size:.7rem;color:var(--muted)" id="logTs">Loading...</span>
  </div>
  <div class="log-viewer" id="logViewer" onmouseenter="logPaused=true" onmouseleave="logPaused=false"></div>
</div>

<!-- &#128373;&#65039; NEW: Challenger Performance (Shadow Mode) &#128373;&#65039; -->
<div class="card" style="margin-bottom:28px">
  <div class="card-title">&#128373;&#65039; Challenger Performance (Shadow Mode)</div>
  <table class="agent-table">
    <thead>
      <tr>
        <th>TS</th>
        <th>Symbol</th>
        <th>Challenger</th>
        <th>Signal</th>
        <th>Confidence</th>
        <th>Reasoning</th>
      </tr>
    </thead>
    <tbody id="challengerTableBody">
        <tr><td colspan="6" style="text-align:center; padding:20px; color:var(--muted)">Checking shadow signals...</td></tr>
    </tbody>
  </table>
</div>

<!-- Recent Trades table -->
<div class="card" style="margin-bottom:28px">
  <div class="card-title">Laatste Trades</div>
  <table class="agent-table">
    <thead>
      <tr>
        <th>#</th>
        <th>Symbol</th>
        <th>Side</th>
        <th>Entry</th>
        <th>Close</th>
        <th>Size</th>
        <th>P&L (USDT)</th>
        <th>P&L %</th>
        <th>Fee</th>
        <th>Reden</th>
        <th>Gesloten</th>
      </tr>
    </thead>
    <tbody id="tradesTableBody"></tbody>
  </table>
</div>

<!-- Trade Journal Section -->
<div style="margin-top: 32px; margin-bottom: 24px;">
  <div style="display:flex; align-items:center; gap:10px">
    <span style="font-size:.85rem; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em">&#129504; Trade Journal (AI Post-Mortems)</span>
  </div>
</div>
<div class="journal-grid" id="journalGrid">
  <div style="color:var(--muted); font-size:.8rem; padding: 20px;">Analyzing past performance...</div>
</div>

<script>
const fmt    = (n) => '$' + (parseFloat(n)||0).toFixed(4);
const fmtBig = (n) => '$' + (parseFloat(n)||0).toFixed(2);
const fmtNum = (n) => (parseInt(n)||0).toLocaleString();
const fmtPnl = (n) => {
  const v = parseFloat(n)||0;
  return (v >= 0 ? '+' : '') + v.toFixed(2);
};

let dailyChartInst, agentChartInst;
let currentConfig = {};
let logPaused = false;

async function load() {
  try {
    // Independent fetches &#8212; a single failure won't break the rest
    const safeFetch = (url, fallback) => fetch(url).then(r => r.ok ? r.json() : fallback).catch(() => fallback);
    const [costs, status, trades, challengers, sconfig] = await Promise.all([
      safeFetch('/costs',             { total_usd: 0, total_calls: 0, by_day: [], by_agent: [] }),
      safeFetch('/status',            { equity_usdt: 0, pnl_total: 0, pnl_today: 0 }),
      safeFetch('/recent-trades',     { trades: [], total: 0, wins: 0, win_rate: 0, total_pnl: 0, total_fees: 0 }),
      safeFetch('/api/config/challengers', []),
      safeFetch('/api/config/system',      {})
    ]);

    // &#9472;&#9472; Top stats &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    document.getElementById('totalCost').textContent  = fmtBig(costs.total_usd);
    document.getElementById('totalCalls').textContent = fmtNum(costs.total_calls);
    document.getElementById('equity').textContent     = fmtBig(status.equity_usdt);
    document.getElementById('totalPnl').textContent   = `Total P&L: ${fmtBig(status.pnl_total)}`;
    const pnlToday = status.pnl_today || 0;
    const el = document.getElementById('todayPnl');
    el.textContent = fmtBig(pnlToday);
    el.style.color = pnlToday >= 0 ? 'var(--accent2)' : 'var(--danger)';
    document.getElementById('lastUpdate').textContent = 'Updated ' + new Date().toLocaleTimeString();

    // &#9472;&#9472; System Info &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    if (status.pid) document.getElementById('serverPid').textContent = status.pid;
    if (status.uptime) document.getElementById('uptime').textContent = status.uptime;

    // &#9472;&#9472; Challenger Table &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    const ctbody = document.getElementById('challengerTableBody');
    ctbody.innerHTML = '';
    challengers.forEach(c => {
        const sigColor = c.signal === 'BULLISH' ? 'var(--accent2)' : (c.signal === 'BEARISH' ? 'var(--danger)' : 'var(--muted)');
        ctbody.innerHTML += `<tr>
            <td style="color:var(--muted)">${new Date(c.ts).toLocaleTimeString()}</td>
            <td><strong>${c.symbol}</strong></td>
            <td><span class="badge badge-purple">${c.challenger_name}</span></td>
            <td style="color:${sigColor}; font-weight:700">${c.signal}</td>
            <td>${c.confidence}/10</td>
            <td>
                <div style="display:flex; justify-content:space-between; align-items:center; gap:10px">
                    <span style="font-size:.7rem; color:var(--muted); max-width:250px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="${c.reasoning}">${c.reasoning}</span>
                    <div style="display:flex; gap:4px; flex-shrink:0">
                        <button class="btn-feedback" onclick="submitFeedback('${c.challenger_name}', 1, this)">&#128077;</button>
                        <button class="btn-feedback down" onclick="submitFeedback('${c.challenger_name}', -1, this)">&#128078;</button>
                    </div>
                </div>
            </td>
        </tr>`;
    });
    if (!challengers.length) ctbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--muted)">No challenger signals yet.</td></tr>';

    // &#9472;&#9472; System Config Hydration &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    if (Object.keys(sconfig).length > 0) {
        const rl = sconfig.risk_limits || {};
        const st = sconfig.scanner_thresholds || {};
        
        // Only update if not currently editing (basic prevention)
        if (document.activeElement.id !== 'conf-min') document.getElementById('conf-min').value = rl.min_confidence || 7.0;
        if (document.activeElement.id !== 'risk-max') document.getElementById('risk-max').value = rl.max_risk_pct || 2.0;
        if (document.activeElement.id !== 'pos-max')  document.getElementById('pos-max').value  = rl.max_positions || 3;
        
        if (document.activeElement.id !== 'scan-vol')  document.getElementById('scan-vol').value  = st.volume_spike_multi || 3.0;
        if (document.activeElement.id !== 'scan-trig') document.getElementById('scan-trig').value = st.trigger_threshold || 2;
        if (document.activeElement.id !== 'scan-z')    document.getElementById('scan-z').value    = st.volatility_zscore || 2.0;
    }

    // &#9472;&#9472; Trade performance stats &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    const wr       = trades.win_rate || 0;
    const fees     = trades.total_fees || 0;
    const closedPnl= trades.total_pnl || 0;
    const netPnl   = closedPnl - fees;

    document.getElementById('winRate').textContent     = wr.toFixed(1) + '%';
    document.getElementById('winRate').style.color     = wr >= 50 ? 'var(--accent2)' : 'var(--danger)';
    document.getElementById('winRateSub').textContent  = `${trades.wins || 0}/${trades.total || 0} trades`;
    document.getElementById('tradeFees').textContent   = fmtBig(fees);
    const cpEl = document.getElementById('closedPnl');
    cpEl.textContent = fmtBig(Math.abs(closedPnl));
    cpEl.style.color = closedPnl >= 0 ? 'var(--accent2)' : 'var(--danger)';
    const npEl = document.getElementById('netPnl');
    npEl.textContent = (netPnl >= 0 ? '+' : '') + netPnl.toFixed(2);
    npEl.style.color = netPnl >= 0 ? 'var(--accent2)' : 'var(--danger)';

    // &#9472;&#9472; Daily chart &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    const days  = costs.by_day.map(d => d.day.slice(5));
    const dCost = costs.by_day.map(d => parseFloat(d.cost).toFixed(5));
    try {
      if (dailyChartInst) dailyChartInst.destroy();
      dailyChartInst = new Chart(document.getElementById('dailyChart'), {
        type: 'bar',
        data: { labels: days, datasets: [{ label: 'USD', data: dCost, backgroundColor: 'rgba(99,102,241,.6)', borderColor: '#6366f1', borderWidth: 1, borderRadius: 4 }] },
        options: { plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#64748b',font:{size:10}}},y:{ticks:{color:'#64748b',font:{size:10}},grid:{color:'rgba(255,255,255,.05)'}}}, responsive:true, maintainAspectRatio:true }
      });
    } catch(chartErr) { console.warn('Daily chart error:', chartErr); }

    // Agent donut
    const agents = costs.by_agent.map(a => a.agent_name);
    const aCosts = costs.by_agent.map(a => parseFloat(a.total_cost_usd));
    const colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#84cc16','#f97316'];
    try {
      if (agentChartInst) agentChartInst.destroy();
      agentChartInst = new Chart(document.getElementById('agentChart'), {
        type: 'doughnut',
        data: { labels: agents, datasets:[{ data: aCosts, backgroundColor: colors, borderWidth: 0 }] },
        options: { plugins:{legend:{position:'right',labels:{color:'#94a3b8',font:{size:11},boxWidth:12}}}, responsive:true, maintainAspectRatio:true }
      });
    } catch(chartErr) { console.warn('Agent chart error:', chartErr); }

    // &#9472;&#9472; Agent cost table &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    const total_usd = costs.total_usd || 0.000001;
    const tbody = document.getElementById('agentTableBody');
    tbody.innerHTML = '';
    costs.by_agent.forEach((a) => {
      const pct = (parseFloat(a.total_cost_usd)/total_usd*100).toFixed(1);
      const isLocal = a.model.includes('llama') || a.model.includes('mistral');
      tbody.innerHTML += `<tr>
        <td><strong>${a.agent_name}</strong></td>
        <td><span class="badge ${isLocal?'badge-green':'badge-purple'}">${a.model}</span></td>
        <td>${fmtNum(a.calls)}</td>
        <td>${fmtNum(a.total_input_tokens)}</td>
        <td>${fmtNum(a.total_output_tokens)}</td>
        <td style="color:${parseFloat(a.total_cost_usd)>0.01?'#f59e0b':'#f1f5f9'}">${fmt(a.total_cost_usd)}</td>
        <td style="min-width:80px">
          <div style="display:flex;align-items:center;gap:6px">
            <div class="bar-wrap"><div class="bar-fill" style="width:${pct}%"></div></div>
            <span style="font-size:.7rem;color:var(--muted)">${pct}%</span>
          </div>
        </td>
      </tr>`;
    });
    if (!costs.by_agent.length) tbody.innerHTML = '<tr><td colspan="7" style="color:var(--muted);text-align:center;padding:24px">No data yet &#8212; run the first agent cycle.</td></tr>';

    // &#9472;&#9472; Recent trades table &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    const ttbody = document.getElementById('tradesTableBody');
    ttbody.innerHTML = '';
    (trades.trades || []).forEach(t => {
      const pnlColor = t.pnl_usdt >= 0 ? 'var(--accent2)' : 'var(--danger)';
      const sideClass = t.side === 'long' ? 'badge-green' : 'badge-warn';
      const reasonBadge = {
        tp1: 'badge-green', tp2: 'badge-green',
        sl: 'badge-warn', trailing_stop: 'badge-warn'
      }[t.reason] || 'badge-purple';
      const closedAt = t.closed_at ? new Date(t.closed_at).toLocaleString('nl-BE',{dateStyle:'short',timeStyle:'short'}) : '&#8212;';
      ttbody.innerHTML += `<tr>
        <td style="color:var(--muted)">${t.id}</td>
        <td><strong>${t.symbol}</strong></td>
        <td><span class="badge ${sideClass}">${t.side.toUpperCase()}</span></td>
        <td>$${t.entry.toLocaleString()}</td>
        <td>$${t.close.toLocaleString()}</td>
        <td>$${t.size_usdt}</td>
        <td style="color:${pnlColor};font-weight:600">${fmtPnl(t.pnl_usdt)}</td>
        <td style="color:${pnlColor}">${fmtPnl(t.pnl_pct)}%</td>
        <td style="color:var(--muted)">$${t.fee_usdt}</td>
        <td><span class="badge ${reasonBadge}">${t.reason}</span></td>
        <td style="color:var(--muted);font-size:.75rem">${closedAt}</td>
      </tr>`;
    });
    if (!trades.trades || !trades.trades.length) {
      ttbody.innerHTML = '<tr><td colspan="11" style="color:var(--muted);text-align:center;padding:24px">Nog geen gesloten trades.</td></tr>';
    }

    // &#9472;&#9472; Trade Journal &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
    const journalEntries = await safeFetch('/journal?limit=6', []);
    const jGrid = document.getElementById('journalGrid');
    jGrid.innerHTML = '';
    
    journalEntries.forEach(j => {
      const score = j.performance_score || 0;
      const scoreClass = score >= 70 ? 'high-score' : (score < 40 ? 'low-score' : '');
      const lessons = JSON.parse(j.lessons_learned || '[]');
      const pnl = parseFloat(j.pnl_usdt) || 0;
      
      const card = document.createElement('div');
      card.className = `journal-card ${scoreClass}`;
      card.innerHTML = `
        <div class="journal-header">
          <div>
            <strong style="font-size: .9rem">${j.symbol}</strong>
            <span class="badge ${j.side === 'long' ? 'badge-green' : 'badge-warn'}" style="margin-left:6px">${j.side.toUpperCase()}</span>
          </div>
          <div class="journal-score" style="color:${score >= 70 ? 'var(--accent2)' : (score < 40 ? 'var(--danger)' : 'var(--warn)')}">
            ${score}/100
          </div>
        </div>
        <div class="journal-summary">${j.summary}</div>
        <ul class="journal-lessons">
          ${lessons.map(l => `<li>${l}</li>`).join('')}
        </ul>
        <div class="journal-critique">
          <strong>Analyst Critique:</strong> ${j.agent_critique}
        </div>
        <div style="margin-top:12px; font-size:.7rem; color:var(--muted); display:flex; justify-content:space-between">
          <span>Profit: <span style="color:${pnl >= 0 ? 'var(--accent2)' : 'var(--danger)'}">${fmtPnl(pnl)} USDT</span></span>
          <span>${new Date(j.ts).toLocaleDateString()}</span>
        </div>
        <div style="margin-top:16px; display:flex; flex-direction:column; gap:8px;">
            <input type="text" id="fb-${j.decision_id}" placeholder="Provide feedback (e.g. You closed too early because...)" style="width:100%; font-size: 0.75rem; padding: 6px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); color: var(--text); outline: none;">
            <button class="btn-save" style="font-size: 0.7rem; padding: 4px; align-self: flex-end;" onclick="sendFeedback(${j.decision_id})">Send to Meta-Optimizer</button>
        </div>
      `;
      jGrid.appendChild(card);
    });
    
    if (!journalEntries.length) {
      jGrid.innerHTML = '<div style="color:var(--muted); font-size:.8rem; padding: 20px; grid-column: 1/-1; text-align:center">No journal entries yet. Close a trade to generate one!</div>';
    }

  } catch(e) { 
    console.error("DASHBOARD ERROR:", e); 
    document.getElementById('lastUpdate').textContent = '&#9888; Render Error: ' + e.message;
  }
}

async function loadConfig() {
    try {
        const data = await fetch('/api/config/models').then(r => r.json());
        currentConfig = data;
        renderConfig();
    } catch(e) { console.error("Error loading config:", e); }
}

function renderConfig() {
    // 1. Core Models
    const modelGrid = document.getElementById('modelConfigGrid');
    const agents = ['volume_analyst', 'orderflow_analyst', 'news_analyst', 'vp_analyst', 'onchain_analyst', 'gametheory_analyst'];
    const providers = currentConfig.available_providers || [];
    
    const activeCoreAgents = currentConfig.active_core_agents || agents; // Default all active
    modelGrid.innerHTML = '';
    agents.forEach(agent => {
        const active = currentConfig.overrides[agent] || currentConfig.defaults[agent];
        const isAgentActive = activeCoreAgents.includes(agent);
        const item = document.createElement('div');
        item.className = 'config-item';
        item.innerHTML = `
            <div style="font-size:.8rem; font-weight:600; display:flex; justify-content:space-between; align-items:center;">
                <span>${agent.split('_')[0].toUpperCase()}</span>
                <label style="display:flex; align-items:center; gap:4px; font-weight:normal; cursor:pointer;" title="Enable/Disable Analyst">
                    <input type="checkbox" id="active-${agent}" ${isAgentActive ? 'checked' : ''} onchange="enableSave()"> Active
                </label>
            </div>
            <div style="display:flex; gap:6px">
                <select id="prov-${agent}" onchange="enableSave()">
                    ${providers.map(p => `<option value="${p}" ${p === active.provider ? 'selected' : ''}>${p}</option>`).join('')}
                </select>
                <input id="mod-${agent}" type="text" value="${active.model}" oninput="enableSave()">
            </div>
        `;
        modelGrid.appendChild(item);
    });

    // 2. Skill Marketplace
    const skillGrid = document.getElementById('skillConfigGrid');
    const available = currentConfig.available_skills || {};
    const active = currentConfig.active_skills || [];
    
    skillGrid.innerHTML = '';
    Object.keys(available).forEach(id => {
        const skill = available[id];
        const isActive = active.includes(id);
        const currentModel = skill.model_override || '';
        const item = document.createElement('div');
        item.className = 'skill-item' + (isActive ? ' active' : '');
        item.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center">
                <div style="display:flex; align-items:center; gap:10px">
                    <input type="checkbox" id="skill-${id}" ${isActive ? 'checked' : ''} onchange="toggleSkillUI('${id}')">
                    <div>
                        <div style="font-size:.85rem; font-weight:600">${skill.name}</div>
                        <div style="font-size:.7rem; color:var(--muted)">${skill.description}</div>
                    </div>
                </div>
                <select class="skill-model-select" data-skill="${id}" onchange="enableSave()">
                    <option value="">(Default)</option>
                    ${providers.map(p => `
                        <optgroup label="${p}">
                            <option value="${p}:standard" ${currentModel===p+':standard'?'selected':''}>${p}/std</option>
                            <option value="${p}:chat" ${currentModel===p+':chat'?'selected':''}>${p}/chat</option>
                        </optgroup>
                    `).join('')}
                </select>
            </div>
        `;
        skillGrid.appendChild(item);
    });
}

function toggleSkillUI(id) {
    const el = document.getElementById(`skill-${id}`).parentElement.parentElement;
    el.classList.toggle('active');
    enableSave();
}

function enableSysSave() {
    document.getElementById('saveSysConfigBtn').disabled = false;
}

async function saveSystemConfig() {
    const btn = document.getElementById('saveSysConfigBtn');
    const status = document.getElementById('systemConfigStatus');
    btn.disabled = true;
    status.textContent = 'Updating...';
    
    const payload = {
        "risk_limits": {
            "min_confidence": parseFloat(document.getElementById('conf-min').value),
            "max_risk_pct":   parseFloat(document.getElementById('risk-max').value),
            "max_positions":  parseInt(document.getElementById('pos-max').value)
        },
        "scanner_thresholds": {
            "volume_spike_multi": parseFloat(document.getElementById('scan-vol').value),
            "trigger_threshold":  parseInt(document.getElementById('scan-trig').value),
            "volatility_zscore": parseFloat(document.getElementById('scan-z').value)
        }
    };
    
    try {
        const res = await fetch('/api/config/system', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            status.textContent = '&#9989; Updated live!';
            setTimeout(() => { status.textContent = ''; }, 3000);
        } else { throw new Error("Fail"); }
    } catch(e) {
        status.textContent = '&#10060; Error';
        btn.disabled = false;
    }
}

function enableSave() {
    document.getElementById('saveConfigBtn').disabled = false;
}

async function saveAllConfig() {
    const btn = document.getElementById('saveConfigBtn');
    const status = document.getElementById('saveStatus');
    btn.disabled = true;
    status.textContent = 'Saving...';
    
    // 1. Core Models & Core Agents Activity
    const overrides = {};
    const coreAgents = ['volume_analyst', 'orderflow_analyst', 'news_analyst', 'vp_analyst', 'onchain_analyst', 'gametheory_analyst'];
    const active_core_agents = [];
    
    coreAgents.forEach(agent => {
        overrides[agent] = {
            provider: document.getElementById(`prov-${agent}`).value,
            model: document.getElementById(`mod-${agent}`).value
        };
        if (document.getElementById(`active-${agent}`).checked) {
            active_core_agents.push(agent);
        }
    });

    // 2. Active Skills
    const active_skills = [];
    const available = currentConfig.available_skills || {};
    Object.keys(available).forEach(id => {
        if (document.getElementById(`skill-${id}`).checked) {
            active_skills.push(id);
        }
    });

    // 3. Skill Model Overrides
    const skill_model_overrides = {};
    document.querySelectorAll('.skill-model-select').forEach(sel => {
        const sid = sel.getAttribute('data-skill');
        if (sel.value) skill_model_overrides[sid] = sel.value;
    });
    
    try {
        const res = await fetch('/api/config/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ overrides, active_skills, skill_model_overrides, active_core_agents })
        });
        if (res.ok) {
            status.textContent = '&#9989; Saved! Changes active next cycle.';
            status.style.color = 'var(--accent2)';
            setTimeout(() => { status.textContent = ''; }, 5000);
            loadConfig(); // Refresh local state
        } else { throw new Error("Fail"); }
    } catch(e) {
        status.textContent = '&#10060; Error saving';
        status.style.color = 'var(--danger)';
        btn.disabled = false;
    }
}
async function submitFeedback(skill_id, rating, btn) {
    try {
        const parent = btn.parentElement;
        parent.querySelectorAll('button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        console.log(`Feedback for ${skill_id}: ${rating}`);
        // Endpoint will be implemented to save to skill_outcomes
    } catch(e) { console.error(e); }
}

document.addEventListener('DOMContentLoaded', () => {
  load();
  loadConfig();
});
setInterval(load, 30000);

// &#9472;&#9472; Service status polling &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function pollHealth() {
  const services = ['main','server','postgres','redis','ollama','stop_monitor','scanner'];
  services.forEach(s => {
    const el = document.getElementById('sphere-'+s);
    if (el) el.className = 'sphere checking';
  });
  try {
    const h = await fetch('/health').then(r => r.json());
    services.forEach(s => {
      const el = document.getElementById('sphere-'+s);
      if (!el) return;
      const st = h.services?.[s] || 'error';
      el.className = 'sphere ' + (st === 'ok' ? 'ok' : 'error');
      const label = document.getElementById('label-'+s);
      if (label) {
        const name = s === 'stop_monitor' ? 'Stop Monitor' : s === 'scanner' ? 'Scanner' : s.charAt(0).toUpperCase()+s.slice(1);
        label.textContent = name + (st !== 'ok' ? ' &#9888;' : '');
      }
    });
    document.getElementById('healthTs').textContent = 'Last checked ' + new Date().toLocaleTimeString();
  } catch(e) {
    services.forEach(s => {
      const el = document.getElementById('sphere-'+s);
      if (el) el.className = 'sphere error';
    });
    document.getElementById('healthTs').textContent = '&#9888; Health check failed';
  }
}

// &#9472;&#9472; System Control Functions &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
function confirmKillGhosts() {
    if (confirm("Dit zal alle achtergrondprocessen die momenteel de web-poort (8000) vasthouden geforceerd afsluiten (kill -9) en de servers herstarten via systemd. Alleen gebruiken bij persistente 'loop' of 'port in use' fouten. Doorgaan?")) {
        killGhosts();
    }
}

async function killGhosts() {
    const status = document.getElementById('controlStatus');
    status.innerHTML = '<span style="color:var(--warn)">&#128123; Ghostbusters geactiveerd... Processen worden vernietigd.</span>';
    try {
        const res = await fetch('/api/config/system/kill-ghosts', { method: 'POST' });
        if (res.ok) {
            status.innerHTML = '<span style="color:var(--accent2)">&#9989; Achtergrondprocessen zijn vernietigd. Dashboard herlaadt over 15s...</span>';
            setTimeout(() => location.reload(), 15000);
        } else { throw new Error("API Fout"); }
    } catch(e) {
        status.innerHTML = '<span style="color:var(--danger)">&#10060; Mislukt: ' + e.message + '</span>';
    }
}

function confirmRestart() {
    if (confirm("Weet je zeker dat je alle services wilt herstarten? Het dashboard zal tijdelijk onbereikbaar zijn.")) {
        restartSystem();
    }
}

async function restartSystem() {
    const status = document.getElementById('controlStatus');
    status.innerHTML = '<span style="color:var(--warn)">&#128260; Herstarten wordt uitgevoerd...</span>';
    try {
        const res = await fetch('/api/config/system/restart', { method: 'POST' });
        if (res.ok) {
            status.innerHTML = '<span style="color:var(--accent2)">&#9989; Herstart signaal verzonden. Pagina herlaadt over 10s...</span>';
            setTimeout(() => location.reload(), 10000);
        } else { throw new Error("Restart failed"); }
    } catch(e) {
        status.innerHTML = '<span style="color:var(--danger)">&#10060; Herstart mislukt: ' + e.message + '</span>';
    }
}

async function reloadConfig() {
    const status = document.getElementById('controlStatus');
    status.innerHTML = '<span style="color:var(--accent)">&#128260; Configuratie herladen...</span>';
    try {
        const res = await fetch('/api/config/system/reload-config', { method: 'POST' });
        if (res.ok) {
            status.innerHTML = '<span style="color:var(--accent2)">&#9989; Configuratie succesvol herladen bij alle actieve processen.</span>';
            setTimeout(() => { status.textContent = ''; }, 5000);
        } else { throw new Error("Reload failed"); }
    } catch(e) {
        status.innerHTML = '<span style="color:var(--danger)">&#10060; Herlaad mislukt: ' + e.message + '</span>';
    }
}

// &#9472;&#9472; Safety / Kill Switch &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function pollSafety() {
    try {
        const data = await fetch('/api/config/safety').then(r => r.json());
        const btn = document.getElementById('killSwitchBtn');
        const st = document.getElementById('safetyStatus');
        
        if (data.kill_switch) {
            btn.textContent = 'CANCEL KILL SWITCH (RESUME)';
            btn.style.background = 'var(--accent2)';
            btn.style.borderColor = 'var(--accent2)';
            st.textContent = '&#128721; TRADING HALTED';
            st.style.color = 'var(--danger)';
        } else {
            btn.textContent = 'EMERGENCY KILL SWITCH';
            btn.style.background = 'var(--danger)';
            btn.style.borderColor = '#ff0000';
            st.textContent = '&#128994; SYSTEM ARMED';
            st.style.color = 'var(--accent2)';
        }
        currentConfig.kill_switch = data.kill_switch;

        // Update Mode Indicator
        const modeSphere = document.getElementById('sphere-mode');
        const modeLabel = document.getElementById('label-mode');
        if (modeSphere && modeLabel) {
            if (data.trade_mode === 'paper') {
                modeSphere.className = 'sphere checking';
                modeLabel.textContent = '&#128196; Paper Only';
            } else if (data.bybit_demo) {
                modeSphere.className = 'sphere ok';
                modeLabel.textContent = '&#129514; Bybit DEMO';
            } else if (data.bybit_testnet) {
                modeSphere.className = 'sphere error'; // Red for testnet? Or maybe create a class
                modeLabel.textContent = '&#128736; Bybit Testnet';
            } else {
                modeSphere.className = 'sphere ok';
                modeLabel.textContent = '&#128176; LIVE Production';
            }
        }
    } catch(e) { console.error("Safety poll failed"); }
}

async function toggleKillSwitch() {
    const newState = !currentConfig.kill_switch;
    const msg = newState ? "STOP ALL TRADING IMMEDIATELY?" : "Resume system operations?";
    if (!confirm(msg)) return;
    
    try {
        const res = await fetch('/api/config/safety', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kill_switch: newState })
        });
        if (res.ok) pollSafety();
    } catch(e) { alert("Kill switch failed!"); }
}

// &#9472;&#9472; Agent Debate & Sparring Room &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
let chatMessages = [];

const AGENT_EXPERTISE = {
  orchestrator:       "Synthethiseert alle rapporten. Heeft het laatste woord over elke trade. Denkt in portefeuille-risico.",
  gametheory_analyst: "Denkt als een predatoire walvis. Obsessie: retail stop-losses opsporen en liquidatie-traps voorspellen.",
  volume_analyst:     "CVD is zijn heilige schrift. Vertrouwt niks zonder volume-bevestiging. Sceptisch van aard.",
  orderflow_analyst:  "Leest bid/ask imbalans als bladmuziek. Ziet patronen in microseconden. Delta-divergentie is zijn edge.",
  news_analyst:       "Cynische journalist. 90% van nieuws is ruis. Maar 10% beweegt markten voor dagen.",
  vp_analyst:         "POC, VAH, VAL zijn zijn heilige niveaus. Prijs wordt altijd magnetisch aangetrokken naar hoge volumezones.",
  onchain_analyst:    "On-chain detective. Miners en whales bewegen eerst. Fear & Greed is zijn polsslag.",
  risk_manager:       "Paranoid kapitaalbewaker. Denkt altijd eerst in maximaal verlies. Keurt trades spaarzaam goed.",
  meta_agent:         "Beoordeelt ALLE andere agents. Meedogenloos analytisch. Schrijft en valideert verbeterplannen.",
};

function onAgentChange() {
  const agent = document.getElementById('agentSelect').value;
  const expertiseEl = document.getElementById('agentExpertise');
  const badge = document.getElementById('agentMemoryBadge');
  if (expertiseEl) expertiseEl.textContent = AGENT_EXPERTISE[agent] || '';
  if (badge) badge.style.display = 'none';
  clearChat();
}

function clearChat() {
  chatMessages = [];
  const hist = document.getElementById('chatHistory');
  if (!hist) return;
  hist.innerHTML = '<div id="chatPlaceholder" style="text-align:center;color:var(--muted);font-size:.8rem;margin:auto">Stel een vraag, daag de agent uit, spar...</div>';
  const st = document.getElementById('chatStatus');
  if (st) st.textContent = '';
}

function appendMessage(role, content, agentLabel) {
  const ph = document.getElementById('chatPlaceholder');
  if (ph) ph.remove();
  const hist = document.getElementById('chatHistory');
  if (!hist) return;

  const isUser = role === 'user';
  const time = new Date().toLocaleTimeString('nl-NL', {hour:'2-digit', minute:'2-digit'});
  const label = isUser ? 'Jij' : (agentLabel || 'Agent');

  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;flex-direction:column;max-width:88%;align-self:' + (isUser ? 'flex-end' : 'flex-start');
  wrap.innerHTML =
    '<div style="font-size:.62rem;color:var(--muted);margin-bottom:3px;padding:0 4px">' + label + ' &#183; ' + time + '</div>' +
    '<div style="background:' + (isUser ? 'var(--accent)' : 'rgba(255,255,255,0.09)') + ';color:' + (isUser ? 'white' : 'var(--text)') + ';' +
    'border-radius:' + (isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px') + ';' +
    'padding:10px 14px;font-size:.85rem;line-height:1.55;' +
    'border:1px solid ' + (isUser ? 'transparent' : 'var(--border)') + ';white-space:pre-wrap;word-break:break-word">' +
    content.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div>';
  hist.appendChild(wrap);
  hist.scrollTop = hist.scrollHeight;
}

async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  const agentSel = document.getElementById('agentSelect');
  const agent = agentSel.value;
  const agentLabel = agentSel.options[agentSel.selectedIndex].text;
  const status = document.getElementById('chatStatus');

  appendMessage('user', text);
  chatMessages.push({role:'user', content:text});
  input.value = '';

  // Typing indicator
  const hist = document.getElementById('chatHistory');
  const typing = document.createElement('div');
  typing.id = 'typingIndicator';
  typing.style.cssText = 'align-self:flex-start;color:var(--muted);font-size:.73rem;font-style:italic;padding:4px 8px';
  typing.textContent = agentLabel + ' denkt na...';
  hist.appendChild(typing);
  hist.scrollTop = hist.scrollHeight;
  if (status) status.textContent = '';

  try {
    const res = await fetch('/api/config/agent/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({agent_name: agent, messages: chatMessages, debate_mode: true})
    });
    const t = document.getElementById('typingIndicator');
    if (t) t.remove();
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    appendMessage('assistant', data.reply, agentLabel);
    chatMessages.push({role:'assistant', content:data.reply});
  } catch(e) {
    const t = document.getElementById('typingIndicator');
    if (t) t.remove();
    if (status) status.innerHTML = '<span style="color:var(--danger)">&#10060; Fout: ' + e.message + '</span>';
  }
}

async function saveChatToMemory() {
  if (chatMessages.length === 0) {
    document.getElementById('chatStatus').innerHTML = '<span style="color:var(--warn)">&#9888; Geen gesprek om op te slaan.</span>';
    return;
  }
  const agent = document.getElementById('agentSelect').value;
  const status = document.getElementById('chatStatus');
  status.innerHTML = '<span style="color:var(--muted)">&#128190; Opslaan naar MD + ChromaDB...</span>';

  const ts = new Date().toLocaleString('nl-NL');
  const lines = ['# Debat & Training Sessie &#8212; ' + ts + '\n'];
  for (const m of chatMessages) {
    lines.push('**' + (m.role === 'user' ? 'Werner' : 'Agent') + ':** ' + m.content + '\n');
  }
  const memoryText = lines.join('\n');

  try {
    const res = await fetch('/api/config/agent/save-memory', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({agent_name: agent, memory_text: memoryText})
    });
    const data = await res.json();
    const mdOk = data.md_file ? '&#9989; MD' : '&#10060; MD';
    const chromaOk = data.chromadb ? '&#9989; ChromaDB' : '&#9888; ChromaDB';
    status.innerHTML = '<span style="color:var(--accent2)">' + mdOk + ' | ' + chromaOk + ' \u2014 Opgeslagen!</span>';
    const badge = document.getElementById('agentMemoryBadge');
    if (badge) badge.style.display = 'inline-block';
  } catch(e) {
    status.innerHTML = '<span style="color:var(--danger)">&#10060; Mislukt: ' + e.message + '</span>';
  }
}

document.addEventListener('DOMContentLoaded', () => { onAgentChange(); });

// &#9472;&#9472; Live Log Viewer &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function pollLogs() {
  if (logPaused) return;
  try {
    const data = await fetch('/logs?n=40').then(r => r.json());
    const viewer = document.getElementById('logViewer');
    const wasAtBottom = viewer.scrollHeight - viewer.scrollTop <= viewer.clientHeight + 40;
    
    viewer.innerHTML = data.lines.map(l => {
      let cls = 'log-other';
      if (l.includes('[SCANNER]')) cls = 'log-scanner';
      else if (l.includes('[MONITOR]')) cls = 'log-monitor';
      else if (l.includes('[RISK] &#9989;')) cls = 'log-risk-ok';
      else if (l.includes('[RISK] &#10060;')) cls = 'log-risk-err';
      else if (l.includes('[ORC]'))     cls = 'log-orc';
      else if (l.includes('[LLM]'))     cls = 'log-llm';
      else if (l.includes('[SKILL]'))   cls = 'log-skill';
      
      return `<div class="log-line ${cls}">${l.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>`;
    }).join('');
    
    if (wasAtBottom) viewer.scrollTop = viewer.scrollHeight;
    document.getElementById('logTs').textContent = 'Last update ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('logTs').textContent = '&#9888; Logs offline';
  }
}

async function pollRegime() {
    try {
        const res = await fetch('/api/regime/BTC%2FUSDT').then(r => r.json());
        const el = document.getElementById('label-regime');
        if (el && res.regime) {
            let color = "var(--accent)";
            if (res.regime.includes("BULL")) color = "#10b981";
            else if (res.regime.includes("BEAR")) color = "#ef4444";
            else if (res.regime.includes("RANGING")) color = "#f59e0b";
            el.style.color = color;
            el.textContent = `${res.regime} (Vol: ${res.volatility})`;
        }
    } catch(e) {}
}

pollLogs();
setInterval(pollLogs, 3000);

pollHealth();
setInterval(pollHealth, 10000);
pollSafety();
setInterval(pollSafety, 5000);
pollRegime();
setInterval(pollRegime, 60000);
</script>
</body>
</html>
"""


def get_dashboard_router():
    from fastapi import APIRouter
    from fastapi.responses import HTMLResponse
    from data.cost_tracker import get_cost_summary

    router = APIRouter()

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return HTMLResponse(content=DASHBOARD_HTML)

    @router.get("/costs")
    async def get_costs():
        return await get_cost_summary()

    return router
