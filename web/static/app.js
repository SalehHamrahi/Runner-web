const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const get = async url => { const r = await fetch(url); const j = await r.json(); if (!r.ok) throw new Error(j.error || 'Request failed'); return j; };
const state = { match:null, visuals:null, tab:'overview', view:'dashboard' };
const THEMES={
  midnight:{a:'#22d3ee',b:'#f59e0b'},
  emerald:{a:'#34d399',b:'#60a5fa'},
  royal:{a:'#60a5fa',b:'#c084fc'},
  sunset:{a:'#fb7185',b:'#fbbf24'},
  mono:{a:'#e5e7eb',b:'#9ca3af'}
};
function teamColors(){const root=getComputedStyle(document.documentElement);return [root.getPropertyValue('--team-a').trim()||'#22d3ee',root.getPropertyValue('--team-b').trim()||'#f59e0b']}
let TEAM_COLORS=teamColors();
function applyTheme(name){const safe=THEMES[name]?name:'midnight';document.documentElement.dataset.theme=safe;localStorage.setItem('runner-theme',safe);requestAnimationFrame(()=>{TEAM_COLORS=teamColors();const s=document.querySelector('#theme-select');if(s)s.value=safe; if(state.view==='match'&&state.match){renderMatch()} else if(state.view==='dashboard'){loadDashboard()}})}
function initTheme(){applyTheme(localStorage.getItem('runner-theme')||'midnight');const s=document.querySelector('#theme-select');if(s)s.addEventListener('change',e=>applyTheme(e.target.value));}

function toast(message){const t=$('#toast');t.textContent=message;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200)}
function setView(name){state.view=name; $$('.page').forEach(p=>p.classList.toggle('active',p.id===name)); $$('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===name)); const title={dashboard:'Dashboard',matches:'Matches',tournaments:'Tournaments',match:'Match Intelligence'}[name]||'Runner'; $('#page-title').textContent=title}
function teamColor(name, teams=[]){const i=teams.indexOf(name);return TEAM_COLORS[i<0?0:i%2]}
function fmtPct(v){return v==null?'—':`${Number(v).toFixed(1)}%`}
function fmt(n,d=0){return n==null?'—':Number(n).toFixed(d)}
function matchRow(m){return `<div class="list-row match-item" data-id="${m.id}"><div><strong>${esc(m.team1)}</strong> <span class="muted">vs</span> <strong>${esc(m.team2)}</strong><div class="meta"><span>#${m.match_number??m.id}</span><span>${esc(m.status)}</span><span>${esc(m.data_status||'pending')}</span></div></div><div class="score">${m.score1??'–'} : ${m.score2??'–'}</div></div>`}
function bindMatchRows(){ $$('.match-item').forEach(x=>x.onclick=()=>openMatch(Number(x.dataset.id))) }
function bindTournamentRows(){ $$('.tournament-item').forEach(x=>x.onclick=()=>openTournament(x.dataset.id)) }

function renderDashboard(data){
  const c=data.counts;
  $('#dashboard').innerHTML=`
  <div class="grid grid-4">
    <div class="stat-card"><div class="label">Tournaments</div><div class="value">${c.tournaments}</div><div class="hint">Recorded runs</div></div>
    <div class="stat-card"><div class="label">Matches</div><div class="value">${c.matches}</div><div class="hint">All match records</div></div>
    <div class="stat-card"><div class="label">Teams</div><div class="value">${c.teams}</div><div class="hint">Unique team names</div></div>
    <div class="stat-card"><div class="label">Completed</div><div class="value">${c.completed_matches}</div><div class="hint">Finished matches</div></div>
  </div>
  <div class="grid grid-main" style="margin-top:14px">
    <section class="panel"><div class="split-actions"><div><h2>Recent Matches</h2><div class="tiny muted">Click a match to inspect its analytics.</div></div><button class="small-btn" id="go-matches">View all</button></div><div class="list" style="margin-top:12px">${data.recent_matches.length?data.recent_matches.map(matchRow).join(''):'<div class="empty">No matches recorded yet.</div>'}</div></section>
    <section class="panel"><div class="split-actions"><div><h2>Tournaments</h2><div class="tiny muted">Latest tournament runs</div></div><button class="small-btn" id="go-tournaments">View all</button></div><div class="list" style="margin-top:12px">${data.tournaments.length?data.tournaments.map(t=>`<div class="list-row tournament-item" data-id="${esc(t.id)}"><div><strong>${esc(t.id)}</strong><div class="meta"><span>${esc(t.type)}</span><span>${esc(t.status)}</span></div></div><span class="badge">${t.matches} matches</span></div>`).join(''):'<div class="empty">No tournaments yet.</div>'}</div></section>
  </div>`;
  bindMatchRows();bindTournamentRows();$('#go-matches').onclick=()=>loadMatches();$('#go-tournaments').onclick=()=>loadTournaments();
}

async function loadDashboard(){try{const data=await get('/api/summary');renderDashboard(data);setView('dashboard')}catch(e){$('#dashboard').innerHTML=`<div class="error">${esc(e.message)}</div>`}}
async function loadMatches(){try{const d=await get('/api/summary');$('#matches').innerHTML=`<section class="panel"><div class="split-actions"><div><h2>Matches</h2><div class="tiny muted">Every stored match, with data readiness.</div></div><input id="match-search" class="search" placeholder="Search team…"></div><div id="match-list" class="list" style="margin-top:14px">${d.recent_matches.map(matchRow).join('')}</div></section>`;const list=d.recent_matches;const filter=()=>{const q=$('#match-search').value.toLowerCase();$('#match-list').innerHTML=list.filter(m=>`${m.team1} ${m.team2}`.toLowerCase().includes(q)).map(matchRow).join('')||'<div class="empty">No matches match your search.</div>';bindMatchRows()};$('#match-search').oninput=filter;bindMatchRows();setView('matches')}catch(e){$('#matches').innerHTML=`<div class="error">${esc(e.message)}</div>`}}
async function loadTournaments(){try{const d=await get('/api/tournaments');$('#tournaments').innerHTML=`<section class="panel"><div class="split-actions"><div><h2>Tournaments</h2><div class="tiny muted">Historical tournament state and match counts.</div></div></div><div class="list" style="margin-top:14px">${d.length?d.map(t=>`<div class="list-row tournament-item" data-id="${esc(t.id)}"><div><strong>${esc(t.id)}</strong><div class="meta"><span>${esc(t.type)}</span><span>${esc(t.status)}</span><span>${t.completed_matches||0}/${t.matches} completed</span></div></div><span class="badge ${t.status==='finished'?'good':''}">${esc(t.status)}</span></div>`).join(''):'<div class="empty">No tournaments yet.</div>'}</div></section>`;bindTournamentRows();setView('tournaments')}catch(e){$('#tournaments').innerHTML=`<div class="error">${esc(e.message)}</div>`}}

function pitchSVG(visuals, mode='shape'){
  const teams=visuals.team_names||[];
  const players=(mode==='final'?visuals.final_players:visuals.average_players)||[];
  const ball=visuals.ball?.[visuals.ball.length-1];
  const sx=x=>Number(x);
  const sy=y=>-Number(y);
  const paths=[];
  if(mode==='ball' && visuals.ball){
    const d=visuals.ball.map((p,i)=>`${i?'L':'M'} ${sx(p.x).toFixed(2)} ${sy(p.y).toFixed(2)}`).join(' ');
    paths.push(`<path d="${d}" fill="none" stroke="#67e8f9" stroke-opacity=".35" stroke-width=".65"/>`);
  }
  let shots='';
  if(mode==='shots'){
    shots=(visuals.shots||[]).map(s=>{
      const goal=s.event_type==='goal', c=teamColor(s.team,teams), x=sx(s.x||0), y=sy(s.y||0);
      const label=s.unum?`<text x="${x+1.5}" y="${y-1.2}" fill="${c}" font-size="2.0" font-weight="700">#${s.unum}</text>`:'';
      return goal
        ? `<text x="${x}" y="${y+2}" class="goal-star" fill="${c}" text-anchor="middle">★</text>${label}`
        : `<line x1="${x-.8}" y1="${y-.8}" x2="${x+.8}" y2="${y+.8}" stroke="${c}" stroke-width=".55"/><line x1="${x-.8}" y1="${y+.8}" x2="${x+.8}" y2="${y-.8}" stroke="${c}" stroke-width=".55"/>${label}`;
    }).join('');
  }
  let passSvg='';
  if(mode==='passing'){
    const map=new Map((visuals.average_players||[]).map(p=>[`${p.team}|${p.unum}`,{x:sx(p.x),y:sy(p.y)}]));
    const counts={};
    (visuals.passes||[]).forEach(p=>{const k=`${p.team}|${p.unum}|${p.receiver_team}|${p.receiver_unum}`;counts[k]=(counts[k]||0)+1});
    passSvg=Object.entries(counts).map(([k,count])=>{
      const [st,su,dt,du]=k.split('|'); const a=map.get(`${st}|${su}`), b=map.get(`${dt}|${du}`); if(!a||!b) return '';
      const c=teamColor(st,teams), markerId=teams.indexOf(st)===1?'arrow-1':'arrow-0';
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${c}" stroke-width="${Math.min(1.35,.28+count*.16).toFixed(2)}" stroke-opacity="${Math.min(.72,.20+count*.07).toFixed(2)}" marker-end="url(#${markerId})"/><text x="${(a.x+b.x)/2}" y="${(a.y+b.y)/2-1}" fill="#dbeafe" font-size="2.0" text-anchor="middle">${count}</text>`;
    }).join('');
  }
  const playerSvg=players.map(p=>{
    const c=teamColor(p.team,teams), x=sx(p.x), y=sy(p.y);
    return `<g class="pitch-player"><circle cx="${x}" cy="${y}" r="1.15" fill="${c}" stroke="#08111b" stroke-width=".30"/><text x="${x}" y="${y+.50}" text-anchor="middle" fill="#061018" font-size="1.12" font-weight="800">${p.unum}</text></g>`;
  }).join('');
  const ballSvg=ball?`<circle cx="${sx(ball.x)}" cy="${sy(ball.y)}" r=".62" fill="#f8fafc" stroke="#08111b" stroke-width=".25"/>`:'';
  return `<svg viewBox="-56 -38 112 76" class="pitch-svg" role="img" aria-label="Football pitch">
    <defs>
      <marker id="arrow-0" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0,0 L5,2.5 L0,5 z" fill="${TEAM_COLORS[0]}"/></marker>
      <marker id="arrow-1" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0,0 L5,2.5 L0,5 z" fill="${TEAM_COLORS[1]}"/></marker>
    </defs>
    <rect x="-52.5" y="-34" width="105" height="68" rx="1.5" fill="#0a2d26" stroke="#7ea0a5" stroke-opacity=".82" stroke-width=".65"/>
    <line x1="0" y1="-34" x2="0" y2="34" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/>
    <circle cx="0" cy="0" r="9.15" fill="none" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/><circle cx="0" cy="0" r=".7" fill="#7ea0a5"/>
    <rect x="-52.5" y="-20.16" width="16.5" height="40.32" fill="none" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/>
    <rect x="-52.5" y="-9.16" width="5.5" height="18.32" fill="none" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/>
    <rect x="36" y="-20.16" width="16.5" height="40.32" fill="none" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/>
    <rect x="47" y="-9.16" width="5.5" height="18.32" fill="none" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/>
    <circle cx="-41" cy="0" r=".7" fill="#7ea0a5"/><circle cx="41" cy="0" r=".7" fill="#7ea0a5"/>
    <path d="M-36,-9 A9.15,9.15 0 0 1 -36,9" fill="none" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/>
    <path d="M36,-9 A9.15,9.15 0 0 0 36,9" fill="none" stroke="#7ea0a5" stroke-opacity=".72" stroke-width=".65"/>
    ${paths.join('')}${shots}${passSvg}${ballSvg}${playerSvg}
  </svg>`;
}

function compareBar(a,b,label,key,unit=''){const av=Number(a?.[key]||0),bv=Number(b?.[key]||0);const total=av+bv||1;return `<div class="metric-line"><span>${label}</span><div class="bar"><i class="a" style="width:${(av/total)*100}%"></i><i class="b" style="width:${(bv/total)*100}%"></i></div><span>${fmt(Math.max(av,bv),unit?1:0)}${unit}</span></div>`}
function matchKpis(d){const a=d.team_statistics?.[0],b=d.team_statistics?.[1];if(!a||!b)return '';return `<div class="kpis">
  <div class="kpi"><div class="label">Possession</div><div class="numbers"><span style="color:var(--cyan)">${fmtPct(a.possession_pct)}</span><span style="color:var(--orange)">${fmtPct(b.possession_pct)}</span></div><div class="sub">${esc(a.team)} · ${esc(b.team)}</div></div>
  <div class="kpi"><div class="label">Passes</div><div class="numbers"><span>${a.passes_completed}</span><span>${b.passes_completed}</span></div><div class="sub">${fmt(a.pass_accuracy_pct,1)}% · ${fmt(b.pass_accuracy_pct,1)}%</div></div>
  <div class="kpi"><div class="label">Shots</div><div class="numbers"><span>${a.shots}</span><span>${b.shots}</span></div><div class="sub">${a.goals} · ${b.goals} goals</div></div>
  <div class="kpi"><div class="label">Territory</div><div class="numbers"><span>${fmtPct(a.avg_territory*100)}</span><span>${fmtPct(b.avg_territory*100)}</span></div><div class="sub">average control</div></div>
  <div class="kpi"><div class="label">Space</div><div class="numbers"><span>${fmtPct(a.avg_space_control*100)}</span><span>${fmtPct(b.avg_space_control*100)}</span></div><div class="sub">average control</div></div>
  <div class="kpi"><div class="label">Pressure</div><div class="numbers"><span>${fmt(a.avg_ball_pressure,3)}</span><span>${fmt(b.avg_ball_pressure,3)}</span></div><div class="sub">ball pressure</div></div>
</div>`}

function overviewHtml(d,v){const a=d.team_statistics?.[0],b=d.team_statistics?.[1];return `${matchKpis(d)}<div class="grid grid-main">
  <section class="panel"><div class="split-actions"><div><h2>Match shape</h2><div class="tiny muted">Average player positions · click another view for tactics.</div></div><div class="filters"><span class="badge" style="color:${TEAM_COLORS[0]}">${esc(a?.team||'Team A')}</span><span class="badge" style="color:${TEAM_COLORS[1]}">${esc(b?.team||'Team B')}</span></div></div><div class="pitch-panel" style="margin-top:12px"><div class="pitch-wrap">${pitchSVG(v,'shape')}</div></div></section>
  <section class="panel"><h2>Match intelligence</h2><div class="metric-list" style="margin-top:15px">
    ${a&&b?compareBar(a,b,'Possession','possession_pct','%'):''}
    ${a&&b?compareBar(a,b,'Passes','passes_completed'):''}
    ${a&&b?compareBar(a,b,'Shots','shots'):''}
    ${a&&b?compareBar(a,b,'Goals','goals'):''}
    ${a&&b?compareBar(a,b,'Territory','avg_territory'):''}
    ${a&&b?compareBar(a,b,'Space','avg_space_control'):''}
  </div><div class="callout" style="margin-top:14px"><strong>State → Action → Outcome</strong><span>${d.analytics?.state_action_outcomes??0} correlated action records are ready for deeper analysis and future learning.</span></div><div class="callout" style="margin-top:8px"><strong>Possession changes</strong><span>${d.analytics?.possession_changes??0} transitions across ${d.analytics?.possession_segments??0} possession segments.</span></div></section>
</div>`}

function tacticsHtml(d,v){return `${matchKpis(d)}<div class="grid grid-3">
  <section class="panel"><h2>Territory</h2><div class="callout" style="margin-top:12px"><strong>${esc(d.team_statistics?.[0]?.team||'A')} · ${fmtPct((d.team_statistics?.[0]?.avg_territory||0)*100)}</strong><span>Share of cycles with the team occupying the attacking half according to match data layer spatial metrics.</span></div><div class="callout" style="margin-top:8px"><strong>${esc(d.team_statistics?.[1]?.team||'B')} · ${fmtPct((d.team_statistics?.[1]?.avg_territory||0)*100)}</strong><span>Comparable territory share for the second team.</span></div></section>
  <section class="panel"><h2>Pressure</h2><div class="metric-list" style="margin-top:12px">${compareBar(d.team_statistics?.[0],d.team_statistics?.[1],'Ball pressure','avg_ball_pressure')}</div><div class="tiny muted" style="margin-top:10px">Pressure is a spatial metric; it should be read comparatively rather than as a percentage.</div></section>
  <section class="panel"><h2>Space control</h2><div class="metric-list" style="margin-top:12px">${compareBar(d.team_statistics?.[0],d.team_statistics?.[1],'Controlled space','avg_space_control')}</div><div class="tiny muted" style="margin-top:10px">A higher value indicates more of the sampled field control metric.</div></section>
</div><section class="panel" style="margin-top:14px"><div class="split-actions"><div><h2>Spatial frame</h2><div class="tiny muted">The same interactive pitch is used as the visual anchor for tactical analysis.</div></div><div class="filters"><span class="badge">Last cycle ${v.last_cycle??'—'}</span></div></div><div class="pitch-panel" style="margin-top:12px"><div class="pitch-wrap">${pitchSVG(v,'shape')}</div></div></section>`}

function passingHtml(v){const teams=v.team_names||[];const counts={};(v.passes||[]).forEach(p=>{const k=`${p.team}|${p.unum}|${p.receiver_team}|${p.receiver_unum}`;counts[k]=(counts[k]||0)+1});const top=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,10);return `<section class="panel"><div class="split-actions"><div><h2>Passing Network</h2><div class="tiny muted">Players use their average pitch position · line width follows inferred pass frequency.</div></div><div class="filters"><span class="badge" style="color:${TEAM_COLORS[0]}">${esc(teams[0]||'Team A')}</span><span class="badge" style="color:${TEAM_COLORS[1]}">${esc(teams[1]||'Team B')}</span></div></div><div class="pitch-panel" style="margin-top:12px"><div class="pitch-wrap">${pitchSVG(v,'passing')}</div></div></section><section class="panel" style="margin-top:14px"><h2>Top passing links</h2><div class="table-wrap" style="margin-top:10px"><table class="table"><thead><tr><th>From</th><th>To</th><th class="num">Passes</th></tr></thead><tbody>${top.map(([k,n])=>{const [a,au,b,bu]=k.split('|');return `<tr><td style="color:${teamColor(a,teams)}">${esc(a)} #${au}</td><td style="color:${teamColor(b,teams)}">${esc(b)} #${bu}</td><td class="num">${n}</td></tr>`}).join('')||'<tr><td colspan="3">No inferred passing links.</td></tr>'}</tbody></table></div></section>`}

function shootingHtml(v){const teams=v.team_names||[];return `<section class="panel"><div class="split-actions"><div><h2>Shot Map</h2><div class="tiny muted">× = shot · ★ = goal · player number appears beside the marker.</div></div><div class="filters"><span class="badge" style="color:${TEAM_COLORS[0]}">${esc(teams[0]||'Team A')}</span><span class="badge" style="color:${TEAM_COLORS[1]}">${esc(teams[1]||'Team B')}</span></div></div><div class="pitch-panel" style="margin-top:12px"><div class="pitch-wrap">${pitchSVG(v,'shots')}</div></div></section><section class="panel" style="margin-top:14px"><h2>Shots</h2><div class="table-wrap" style="margin-top:10px"><table class="table"><thead><tr><th>Cycle</th><th>Team</th><th>Player</th><th>Position</th><th>Type</th><th>Confidence</th></tr></thead><tbody>${(v.shots||[]).map(s=>`<tr><td>${s.cycle}</td><td style="color:${teamColor(s.team,teams)}">${esc(s.team)}</td><td>#${s.unum??'—'}</td><td>${fmt(s.x,1)}, ${fmt(s.y,1)}</td><td>${s.event_type==='goal'?'<span class="badge good">GOAL</span>':'<span class="badge">SHOT</span>'}</td><td>${esc(s.confidence||'—')}</td></tr>`).join('')||'<tr><td colspan="6">No shots detected.</td></tr>'}</tbody></table></div></section>`}

function momentumSvg(advanced){
  const m=advanced?.momentum||[], teams=advanced?.teams||[];
  if(!m.length||teams.length<2)return '<div class="empty">No momentum data.</div>';
  const w=900,h=240,p=28;
  const maxCycle=Math.max(...m.map(x=>x.cycle_end),1);
  const series=teams.map((team,idx)=>m.filter(x=>x.team===team).sort((a,b)=>a.cycle_start-b.cycle_start));
  const colors=[TEAM_COLORS[0],TEAM_COLORS[1]];
  const polylines=series.map((arr,idx)=>{
    const pts=arr.map(x=>`${p+(x.cycle_start/maxCycle)*(w-2*p)},${h-p-(x.score/100)*(h-2*p)}`).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${colors[idx]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
  }).join('');
  const grid=[25,50,75].map(v=>{const y=h-p-(v/100)*(h-2*p);return `<line x1="${p}" y1="${y}" x2="${w-p}" y2="${y}" stroke="#31415f" stroke-width="1" stroke-dasharray="4 6"/><text x="8" y="${y+4}" fill="#7183a0" font-size="11">${v}</text>`}).join('');
  return `<svg viewBox="0 0 ${w} ${h}" class="mini-chart" role="img" aria-label="Momentum chart">${grid}<line x1="${p}" y1="${h-p}" x2="${w-p}" y2="${h-p}" stroke="#3a4b68"/><line x1="${p}" y1="${p}" x2="${p}" y2="${h-p}" stroke="#3a4b68"/>${polylines}</svg>`;
}
function intelligenceHtml(d){
  const a=d.advanced, teams=a?.teams||[d.match.team1,d.match.team2];
  if(!a)return '<section class="panel"><div class="empty">Advanced analytics are not available for this match yet.</div></section>';
  const styles=a.team_styles||[];
  const comp=a.comparison||[];
  const ratings=(a.player_ratings||[]).slice(0,12);
  const form=a.recent_form||{};
  return `<div class="grid grid-main">
    <section class="panel">
      <div class="split-actions"><div><h2>Momentum</h2><div class="tiny muted">Comparative momentum score from possession, territory, space, pressure and attacking events.</div></div><div class="filters"><span class="badge" style="color:${TEAM_COLORS[0]}">${esc(teams[0])}</span><span class="badge" style="color:${TEAM_COLORS[1]}">${esc(teams[1])}</span></div></div>
      <div class="chart-wrap" style="margin-top:12px">${momentumSvg(a)}</div>
    </section>
    <section class="panel">
      <h2>Team style</h2><div class="style-grid" style="margin-top:12px">${styles.map((st,i)=>`<div class="style-card"><div class="style-team" style="color:${TEAM_COLORS[i]}">${esc(st.team)}</div><div class="style-name">${esc(st.primary_style)}</div><div class="style-bars">${Object.entries(st.scores||{}).slice(0,4).map(([k,v])=>`<div class="style-line"><span>${esc(k)}</span><b>${fmt(v,0)}</b><i><em style="width:${Math.min(100,Number(v))}%;background:${TEAM_COLORS[i]}"></em></i></div>`).join('')}</div></div>`).join('')}</div>
    </section>
  </div>
  <section class="panel" style="margin-top:14px"><div class="split-actions"><div><h2>Tactical comparison</h2><div class="tiny muted">Difference between the two teams' advanced metrics.</div></div><span class="badge">${comp.length} metrics</span></div><div class="advanced-compare" style="margin-top:14px">${comp.map(c=>{const av=Number(c.team1),bv=Number(c.team2),max=Math.max(Math.abs(av),Math.abs(bv),.001);return `<div class="compare-row"><div class="compare-head"><span>${esc(c.label)}</span><span>${fmt(av, c.label.includes('%')?1:2)} · ${fmt(bv,c.label.includes('%')?1:2)}</span></div><div class="compare-track"><i style="width:${Math.min(100,Math.abs(av)/max*48)}%;background:${TEAM_COLORS[0]}"></i><i style="width:${Math.min(100,Math.abs(bv)/max*48)}%;background:${TEAM_COLORS[1]}" ></i></div><div class="tiny muted">Leader: ${esc(c.leader||'Even')}</div></div>`}).join('')}</div></section>
  <div class="grid grid-main" style="margin-top:14px">
    <section class="panel"><div class="panel-title-row"><h3>Top players</h3><span class="badge">heuristic rating</span></div><div class="rating-list">${ratings.map(p=>`<div class="rating-row"><div><strong style="color:${teamColor(p.team,teams)}">#${p.unum}</strong><span>${esc(p.team)}</span></div><b>${fmt(p.rating,2)}</b></div>`).join('')||'<div class="empty">No player ratings.</div>'}</div></section>
    <section class="panel"><div class="panel-title-row"><h3>Recent form</h3><span class="badge">last 5</span></div><div class="form-grid">${teams.map((team,i)=>`<div class="form-card"><strong style="color:${TEAM_COLORS[i]}">${esc(team)}</strong><div class="form-string">${esc(form[team]?.string||'—')}</div><div class="tiny muted">${(form[team]?.results||[]).map(x=>`${esc(x.result)} vs ${esc(x.opponent)}`).join(' · ')||'No previous completed matches'}</div></div>`).join('')}</div></section>
  </div>
  <section class="panel" style="margin-top:14px"><div class="panel-title-row"><h3>Transitions</h3><span class="badge">${a.transitions?.possession_changes??0} changes</span></div><div class="grid grid-3" style="margin-top:10px"><div class="kpi mini"><div class="label">Quick shot transitions</div><div class="value">${a.transitions?.quick_shot_transitions??0}</div></div><div class="kpi mini"><div class="label">Transitions / 1000 cycles</div><div class="value">${fmt(a.transitions?.transitions_per_1000_cycles,2)}</div></div><div class="kpi mini"><div class="label">Top player</div><div class="value">${a.records?.top_player?`#${a.records.top_player.unum}`:'—'}</div></div></div></section>`;
}

function eventsHtml(v){const icon={goal:'★',shot:'×',pass:'→',turnover:'!',interception:'↘',playmode:'•'};return `<section class="panel"><div class="split-actions"><div><h2>Event Timeline</h2><div class="tiny muted">Key events extracted from RCG + RCL.</div></div><span class="badge">${v.events?.length||0} events</span></div><div class="event-list" style="margin-top:12px">${(v.events||[]).map(e=>`<div class="event-row"><div class="event-cycle">${e.cycle}</div><div><div class="event-title">${icon[e.event_type]||'•'} ${esc(e.event_type)}</div><div class="event-meta">${esc(e.team||'')} ${e.unum?`· #${e.unum}`:''} · ${esc(e.confidence||'')}</div></div><span class="event-pill">${e.details?.playmode?esc(e.details.playmode):e.details?.outcome?esc(e.details.outcome):''}</span></div>`).join('')||'<div class="empty">No events.</div>'}</div></section>`}

function playersHtml(d){return `<section class="panel"><div class="split-actions"><div><h2>Player Analytics</h2><div class="tiny muted">Aggregate performance from analytics.</div></div></div><div class="table-wrap" style="margin-top:12px"><table class="table"><thead><tr><th>Team</th><th>#</th><th>Actions</th><th>Touches</th><th>Passes</th><th>Shots</th><th>Goals</th><th>Distance</th><th>Pressure</th></tr></thead><tbody>${(d.player_statistics||[]).map(p=>`<tr><td style="color:${teamColor(p.team,[d.match.team1,d.match.team2])}">${esc(p.team)}</td><td>${p.unum}</td><td>${p.actions}</td><td>${p.touch_cycles}</td><td>${p.passes_completed}</td><td>${p.shots}</td><td>${p.goals}</td><td>${fmt(p.movement_distance,1)}</td><td>${fmt(p.avg_pressure_when_possessed,3)}</td></tr>`).join('')||'<tr><td colspan="9">No player analytics available.</td></tr>'}</tbody></table></div></section>`}

function actionsHtml(d){return `<section class="panel"><div class="split-actions"><div><h2>Agent Actions</h2><div class="tiny muted">Raw RCL commands are shown alongside correlated outcomes.</div></div><span class="badge">${d.action_outcomes?.length||0} outcomes</span></div><div class="table-wrap" style="margin-top:12px"><table class="table"><thead><tr><th>Cycle</th><th>Team</th><th>Player</th><th>Action</th><th>Outcome</th><th>Pressure</th><th>Space</th></tr></thead><tbody>${(d.action_outcomes||[]).map(a=>`<tr><td>${a.cycle}</td><td>${esc(a.team)}</td><td>#${a.unum}</td><td><span class="badge">${esc(a.action_type)}</span></td><td>${esc(a.outcome)}</td><td>${fmt(a.pressure,3)}</td><td>${fmt(a.space_control,3)}</td></tr>`).join('')||'<tr><td colspan="7">No state/action/outcome records.</td></tr>'}</tbody></table></div></section>`}

async function loadGraphics(matchId){try{const g=await get(`/api/matches/${matchId}/graphics`);return `<div class="panel report-tools"><div><h2>Export report</h2><div class="tiny muted">Download the complete Match report or its source datasets.</div></div><div class="export-actions"><a class="small-btn" href="/api/reports/match/${matchId}/html" download>HTML</a><a class="small-btn" href="/api/reports/match/${matchId}/json" download>JSON</a><a class="small-btn" href="/api/reports/match/${matchId}/csv" download>CSV ZIP</a><a class="small-btn" href="/api/reports/match/${matchId}/graphics" download>Graphics ZIP</a><a class="small-btn" href="/api/reports/match/${matchId}/pdf" download>PDF</a></div></div><div class="graphics-grid"><article class="panel report-card wide"><div><h2>Report Overview</h2><div class="tiny muted">High-resolution export from the updated Analyzer.</div></div><img class="report-img" src="${g.overview}" loading="lazy"></article><article class="panel report-card"><div><h2>Shot Report</h2></div><img class="report-img" src="${g.shots}" loading="lazy"></article><article class="panel report-card"><div><h2>Passing Report</h2></div><img class="report-img" src="${g.passing}" loading="lazy"></article></div>`}catch(e){return `<div class="error">${esc(e.message)}</div>`}}

function hero(d){const m=d.match;const winner=m.winner;return `<div class="hero"><div class="hero-main" style="width:100%"><div class="eyebrow">MATCH #${m.match_number??m.id} · ${esc(m.status)}</div><div class="teams" style="margin-top:10px"><div class="team" style="color:${TEAM_COLORS[0]}">${esc(m.team1)}</div><div class="scoreline">${m.score1??'–'} <span class="versus">—</span> ${m.score2??'–'}</div><div class="team" style="color:${TEAM_COLORS[1]}">${esc(m.team2)}</div></div><div style="text-align:center;margin-top:7px" class="small muted">Winner: <span class="${winner?'winner':''}">${esc(winner||'Draw')}</span> · Data: ${esc(m.data_status||'pending')}</div></div></div>`}

async function openMatch(id){try{const [d,v]=await Promise.all([get(`/api/matches/${id}`),get(`/api/matches/${id}/visuals`)]);state.match=d;state.visuals=v;state.tab='overview';setView('match');renderMatch()}catch(e){setView('match');$('#match').innerHTML=`<div class="error">${esc(e.message)}</div>`}}
function renderMatch(){const d=state.match,v=state.visuals;$('#page-title').textContent=`${d.match.team1} ${d.match.score1??'–'} — ${d.match.score2??'–'} ${d.match.team2}`;const tabs=[['overview','Overview'],['intelligence','Intelligence'],['tactics','Tactics'],['passing','Passing'],['shooting','Shooting'],['players','Players'],['events','Events'],['actions','Actions'],['reports','Reports']];$('#match').innerHTML=`${hero(d)}<div class="tabs">${tabs.map(([id,label])=>`<button class="tab ${state.tab===id?'active':''}" data-tab="${id}">${label}</button>`).join('')}</div><div id="match-body"></div>`;$$('.tab',$('#match')).forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;renderMatch()});const body=$('#match-body');body.innerHTML=state.tab==='overview'?overviewHtml(d,v):state.tab==='intelligence'?intelligenceHtml(d):state.tab==='tactics'?tacticsHtml(d,v):state.tab==='passing'?passingHtml(v):state.tab==='shooting'?shootingHtml(v):state.tab==='players'?playersHtml(d):state.tab==='events'?eventsHtml(v):state.tab==='actions'?actionsHtml(d):'<div class="loading">Generating report graphics…</div>';if(state.tab==='reports'){loadGraphics(d.match.id).then(html=>$('#match-body').innerHTML=html)}
}

async function openTournament(id){try{const [d,info]=await Promise.all([get(`/api/tournaments/${encodeURIComponent(id)}`),get(`/api/tournaments/${encodeURIComponent(id)}/intelligence`).catch(()=>null)]);setView('match');$('#page-title').textContent=`Tournament · ${id}`;const rows=info?.ranking||[];const records=info?.records||{};$('#match').innerHTML=`<div class="panel"><div class="split-actions"><div><div class="eyebrow">TOURNAMENT INTELLIGENCE</div><h2 style="font-size:24px;margin-top:8px">${esc(id)}</h2><div class="small muted" style="margin-top:4px">${esc(d.tournament.type)} · ${esc(d.tournament.status)} · ${d.matches.length} matches</div></div><div class="export-actions"><a class="small-btn" href="/api/reports/tournament/${encodeURIComponent(id)}/html" download>HTML</a><a class="small-btn" href="/api/reports/tournament/${encodeURIComponent(id)}/json" download>JSON</a><a class="small-btn" href="/api/reports/tournament/${encodeURIComponent(id)}/csv" download>CSV ZIP</a><a class="small-btn" href="/api/reports/tournament/${encodeURIComponent(id)}/graphics" download>Graphics ZIP</a><a class="small-btn" href="/api/reports/tournament/${encodeURIComponent(id)}/pdf" download>PDF</a></div></div></div><div class="grid grid-main" style="margin-top:14px"><section class="panel"><h2>Standings & form</h2><div class="table-wrap" style="margin-top:10px"><table class="table"><thead><tr><th>#</th><th>Team</th><th>GP</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Pts</th><th>Elo</th><th>Form</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${i+1}</td><td><strong>${esc(r.team)}</strong></td><td>${r.played}</td><td>${r.wins}</td><td>${r.draws}</td><td>${r.losses}</td><td>${r.gd}</td><td><strong>${r.points}</strong></td><td>${fmt(r.elo,1)}</td><td class="form-string" style="font-size:12px;letter-spacing:.08em">${esc(r.form||'—')}</td></tr>`).join('')||'<tr><td colspan="10">No completed matches yet.</td></tr>'}</tbody></table></div></section><section class="panel"><h2>Tournament records</h2><div class="metric-list" style="margin-top:12px"><div class="callout"><strong>Largest win</strong><span>${records.largest_win?`${esc(records.largest_win.winner)} · ${esc(records.largest_win.score)}`:'—'}</span></div><div class="callout"><strong>Highest scoring match</strong><span>${records.highest_scoring_match?esc(records.highest_scoring_match.score):'—'}</span></div><div class="callout"><strong>Most goals</strong><span>${esc(records.most_goals||'—')}</span></div><div class="callout"><strong>Best possession</strong><span>${esc(records.best_possession||'—')}</span></div></div></section></div><section class="panel" style="margin-top:14px"><div class="split-actions"><div><h2>Monte Carlo simulation</h2><div class="tiny muted">Estimate champion and top-3 probability from current Elo and scoring history.</div></div><button class="small-btn" id="run-sim">Run 10,000 simulations</button></div><div id="simulation-box" class="empty" style="margin-top:12px">No simulation run yet.</div></section><section class="panel" style="margin-top:14px"><h2>Matches</h2><div class="list" style="margin-top:10px">${d.matches.map(matchRow).join('')}</div></section>`;bindMatchRows();$('#run-sim').onclick=async()=>{const b=$('#run-sim'),box=$('#simulation-box');b.disabled=true;b.textContent='Simulating…';box.className='loading';box.textContent='Running 10,000 reproducible simulations…';try{const sim=await get(`/api/tournaments/${encodeURIComponent(id)}/simulation?runs=10000&seed=42`);box.className='';box.innerHTML=`<div class="table-wrap"><table class="table"><thead><tr><th>#</th><th>Team</th><th>Champion</th><th>Top 3</th><th>Exp. points</th><th>Exp. rank</th><th>Elo</th></tr></thead><tbody>${(sim.ranking||[]).map((r,i)=>`<tr><td>${i+1}</td><td><strong>${esc(r.team)}</strong></td><td>${fmt(r.champion_probability,1)}%</td><td>${fmt(r.top3_probability,1)}%</td><td>${fmt(r.expected_points,2)}</td><td>${fmt(r.expected_rank,2)}</td><td>${fmt(r.elo,1)}</td></tr>`).join('')}</tbody></table></div>`}catch(e){box.className='error';box.textContent=e.message}finally{b.disabled=false;b.textContent='Run 10,000 simulations'}}}catch(e){$('#match').innerHTML=`<div class="error">${esc(e.message)}</div>`}}

$$('.nav-btn').forEach(b=>b.onclick=()=>{const v=b.dataset.view;if(v==='dashboard')loadDashboard();if(v==='matches')loadMatches();if(v==='tournaments')loadTournaments()});$('#refresh').onclick=()=>{if(state.view==='match'&&state.match)openMatch(state.match.match.id);else loadDashboard()};
loadDashboard();

/* =========================
   simulation · Web Replay
   ========================= */
state.replay = { meta:null, frames:[], cursor:0, playing:false, timer:null, start:0, end:0, step:1, chunk:400, loading:false, speed:1, trail:true, overlay:'clean' };

async function loadReplayMeta(matchId){
  state.replay = { meta: await get(`/api/matches/${matchId}/replay/meta`), frames:[], cursor:0, playing:false, timer:null, start:0, end:0, step:1, chunk:400, loading:false, speed:1, trail:true, overlay:'clean' };
  return state.replay.meta;
}

async function loadReplayChunk(matchId, start){
  const r=state.replay;
  if(r.loading) return;
  const end=Math.min(r.meta?.last_cycle ?? start+r.chunk, start+r.chunk);
  if(r.frames.some(f=>f.cycle>=start && f.cycle<=end)) return;
  r.loading=true;
  try{
    const d=await get(`/api/matches/${matchId}/replay?start=${start}&end=${end}&step=${r.step}`);
    const merged=new Map(r.frames.map(f=>[f.cycle,f]));
    (d.frames||[]).forEach(f=>merged.set(f.cycle,f));
    r.frames=[...merged.values()].sort((a,b)=>a.cycle-b.cycle);
    r.end=Math.max(r.end,end);
  }finally{r.loading=false;}
}

function currentReplayFrame(){return state.replay.frames[state.replay.cursor]||null}
function frameIndexForCycle(c){
  const a=state.replay.frames; if(!a.length) return 0;
  let lo=0,hi=a.length-1,ans=0;
  while(lo<=hi){const m=(lo+hi)>>1;if(a[m].cycle<=c){ans=m;lo=m+1}else hi=m-1}
  return ans;
}
function replayFmtTime(cycle){
  const sec=Math.max(0, Number(cycle||0))*0.1;
  const m=Math.floor(sec/60), s=Math.floor(sec%60), e=Math.floor((sec-Math.floor(sec))*10);
  return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${e}`;
}
function replayPitchSVG(frame, visuals, opts={}){
  const teams=visuals.team_names||[]; const players=frame?.players||[]; const ball=frame?.ball;
  const teamA=teams[0], teamB=teams[1];
  const ca=teamColor(teamA,teams), cb=teamColor(teamB,teams);
  const selected=opts.selectedTeam || '';
  const spatial=frame?.spatial||{};
  const trail=opts.trail && state.replay.frames.length ? state.replay.frames.slice(Math.max(0,state.replay.cursor-24), state.replay.cursor+1) : [];
  const ballTrail=trail.filter(f=>f.ball).map(f=>`${f===trail[0]?'M':'L'} ${Number(f.ball.x).toFixed(2)} ${(-Number(f.ball.y)).toFixed(2)}`).join(' ');
  const possessionTeam=spatial.possession_team;
  const pressureA=Number(spatial.left_ball_pressure||0), pressureB=Number(spatial.right_ball_pressure||0);
  const possessionPlayer=spatial.possession_unum;
  const pressureHalo=ball ? `<circle cx="${ball.x}" cy="${-ball.y}" r="${(2+Math.min(5,Math.max(0,Math.max(pressureA,pressureB))*1.15)).toFixed(2)}" fill="none" stroke="${possessionTeam===teamB?cb:ca}" stroke-opacity=".16" stroke-width=".60"/>` : '';
  const possessionBand = possessionTeam ? `<g class="possession-banner"><rect x="-24" y="-36.3" width="48" height="3.1" rx="1.55" fill="${possessionTeam===teamB?cb:ca}" opacity=".16"/><text x="0" y="-34.2" text-anchor="middle" fill="#e6f1ff" font-size="1.8" font-weight="700">POSSESSION · ${esc(possessionTeam)}${possessionPlayer?` #${possessionPlayer}`:''}</text></g>` : '';
  const recentFrames=state.replay.frames.slice(Math.max(0,state.replay.cursor-120), state.replay.cursor+1);
  const playerPos=new Map(players.map(p=>[`${p.team}|${p.unum}`,{x:Number(p.x),y:-Number(p.y)}]));
  let analysisSvg='';
  if(opts.analysis==='passing'){
    const linksMap=new Map();
    recentFrames.forEach(rf=>(rf.events||[]).filter(e=>e.event_type==='pass'&&e.team&&e.unum).forEach(e=>{
      const d=e.details||{}, key=`${e.team}|${e.unum}|${d.receiver_team}|${d.receiver_unum}`;
      const to=(rf.players||[]).find(p=>`${p.team}|${p.unum}`===`${d.receiver_team}|${d.receiver_unum}`);
      if(to && e.x!=null && e.y!=null){
        const item=linksMap.get(key)||{x1:Number(e.x),y1:-Number(e.y),x2:Number(to.x),y2:-Number(to.y),c:teamColor(e.team,teams),n:0};
        item.x1=(item.x1*item.n+Number(e.x))/(item.n+1); item.y1=(item.y1*item.n-Number(e.y))/(item.n+1);
        item.x2=(item.x2*item.n+Number(to.x))/(item.n+1); item.y2=(item.y2*item.n-Number(to.y))/(item.n+1); item.n++; linksMap.set(key,item);
      }
    }));
    const links=[...linksMap.values()].sort((a,b)=>b.n-a.n).filter(l=>l.n>1 || linksMap.size<=8).slice(0,8);
    analysisSvg=links.map(l=>{
      const marker=teams.indexOf(l.c===teamColor(teams[1],teams)?teams[1]:teams[0])===1?'b':'a';
      return `<line x1="${l.x1.toFixed(2)}" y1="${l.y1.toFixed(2)}" x2="${l.x2.toFixed(2)}" y2="${l.y2.toFixed(2)}" stroke="${l.c}" stroke-opacity=".58" stroke-width="${Math.min(.72,.24+l.n*.06).toFixed(2)}" marker-end="url(#replay-arrow-${marker})"/>`;
    }).join('');
  } else if(opts.analysis==='shots'){
    analysisSvg=recentFrames.flatMap(rf=>rf.events||[]).filter(e=>['shot','goal'].includes(e.event_type)&&e.x!=null&&e.y!=null).slice(-18).map(e=>{const c=teamColor(e.team,teams);return e.event_type==='goal'?`<circle cx="${e.x}" cy="${-e.y}" r="1.35" fill="none" stroke="${c}" stroke-width=".45"/><text x="${e.x}" y="${-e.y}" fill="#fef08a" font-size="2.8" text-anchor="middle">★</text>`:`<text x="${e.x}" y="${-e.y}" fill="${c}" font-size="2.15" text-anchor="middle">×</text>`}).join('');
  }
  const eventDots=(frame?.events||[]).filter(e=>e.x!=null&&e.y!=null).map(e=>{
    const c=teamColor(e.team,teams), symbol=e.event_type==='goal'?'★':e.event_type==='shot'?'×':e.event_type==='pass'?'•':'·';
    return `<text x="${Number(e.x)}" y="${-Number(e.y)}" fill="${c}" font-size="${e.event_type==='goal'?3.0:2.1}" text-anchor="middle" dominant-baseline="middle" opacity="${opts.analysis==='clean'?'.95':'.3'}">${symbol}</text>`;
  }).join('');
  const psvg=players.map(p=>{
    const c=p.team===teamB?cb:ca, x=Number(p.x),y=-Number(p.y), isPoss=(p.team===possessionTeam&&Number(p.unum)===Number(possessionPlayer));
    const hi=selected && p.team!==selected ? .35 : 1;
    return `<g opacity="${hi}" class="replay-player" data-team="${esc(p.team)}" data-unum="${p.unum}">
      ${isPoss?`<circle cx="${x}" cy="${y}" r="1.65" fill="none" stroke="#fef08a" stroke-width=".32" opacity=".95"/>`:''}
      <circle cx="${x}" cy="${y}" r="1.05" fill="${c}" stroke="#07111b" stroke-width=".28"/>
      <text x="${x}" y="${y+.72}" text-anchor="middle" fill="#031018" font-size="1.02" font-weight="900">${p.unum}</text>
    </g>`;
  }).join('');
  return `<svg viewBox="-56 -38 112 76" class="pitch-svg replay-pitch" role="img" aria-label="Match replay pitch">
    <defs>
      <linearGradient id="pitch-bg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#0b392d"/><stop offset="1" stop-color="#08291f"/></linearGradient>
      <filter id="glow"><feGaussianBlur stdDeviation="1.0" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter><marker id="replay-arrow-a" markerWidth="2.8" markerHeight="2.8" refX="2.2" refY="1.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L2.6,1.4 L0,2.8 Z" fill="${ca}"/></marker><marker id="replay-arrow-b" markerWidth="2.8" markerHeight="2.8" refX="2.2" refY="1.4" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L2.6,1.4 L0,2.8 Z" fill="${cb}"/></marker>
    </defs>
    <rect x="-52.5" y="-34" width="105" height="68" rx="1.8" fill="url(#pitch-bg)" stroke="#5f8c85" stroke-width=".65"/>
    <path d="M0 -34V34 M-52.5 0H52.5" stroke="#6b958e" stroke-width=".45" opacity=".75"/>
    <circle cx="0" cy="0" r="9.15" fill="none" stroke="#6b958e" stroke-width=".45" opacity=".75"/>
    <circle cx="0" cy="0" r=".7" fill="#b8d8d1"/>
    <path d="M-52.5 -16.5H-36.5V16.5H-52.5 M52.5 -16.5H36.5V16.5H52.5" fill="none" stroke="#6b958e" stroke-width=".45"/>
    <path d="M-52.5 -8.5H-46V8.5H-52.5 M52.5 -8.5H46V8.5H52.5" fill="none" stroke="#6b958e" stroke-width=".45"/>
    <path d="M-52.5 -7.3A6.3 6.3 0 0 0 -46.2 0A6.3 6.3 0 0 0 -52.5 7.3 M52.5 -7.3A6.3 6.3 0 0 1 46.2 0A6.3 6.3 0 0 1 52.5 7.3" fill="none" stroke="#6b958e" stroke-width=".45"/>
    <text x="-49.5" y="-31" fill="#a7c7c1" font-size="1.8" font-weight="700">${esc(teamA||'TEAM A')}</text>
    <text x="49.5" y="-31" fill="#a7c7c1" font-size="1.8" font-weight="700" text-anchor="end">${esc(teamB||'TEAM B')}</text>
    ${ballTrail?`<path d="${ballTrail}" fill="none" stroke="#f8fafc" stroke-opacity=".20" stroke-width=".55" stroke-linecap="round"/>`:''}
    ${pressureHalo}${analysisSvg}${eventDots}${psvg}
    ${ball?`<circle cx="${ball.x}" cy="${-ball.y}" r=".58" fill="#fff" stroke="#0b1420" stroke-width=".26" filter="url(#glow)"/>`:''}
    ${possessionBand}
  </svg>`;
}

function replayControls(){
  const r=state.replay, m=r.meta||{}, frame=currentReplayFrame(), idx=r.cursor, total=Math.max(1,r.frames.length);
  const current=frame?.cycle??m.first_cycle??0, last=m.last_cycle??0;
  const pct=last?Math.min(100,Math.max(0,current/last*100)):0;
  return `<div class="replay-controls panel">
    <div class="replay-main-controls">
      <button class="play-btn" id="replay-play">${r.playing?'❚❚':'▶'}</button>
      <button class="icon-btn" id="replay-prev">‹</button><button class="icon-btn" id="replay-next">›</button>
      <div class="replay-clock"><strong>${replayFmtTime(current)}</strong><span>/ ${replayFmtTime(last)}</span></div>
      <div class="speed-group">${[0.5,1,2,4].map(s=>`<button class="speed-btn ${r.speed===s?'active':''}" data-speed="${s}">${s}×</button>`).join('')}</div>
      <button class="toggle ${r.trail?'active':''}" id="replay-trail">Trail</button><div class="replay-overlay-group">${[['clean','Clean'],['passing','Passing'],['shots','Shots']].map(([id,label])=>`<button class="overlay-btn ${r.overlay===id?'active':''}" data-overlay="${id}">${label}</button>`).join('')}</div>
    </div>
    <div class="timeline-wrap"><input id="replay-seek" class="replay-range" type="range" min="0" max="${last}" value="${current}" step="1" style="--progress:${pct}%"></div>
    <div class="timeline-meta"><span>Cycle ${current.toLocaleString()}</span><span>${frame?.playmode?esc(frame.playmode):'play_on'}</span><span>${r.loading?'Loading…':`${idx+1}/${total} rendered frames`}</span></div>
  </div>`;
}

function replaySidePanel(d, frame){
  const s=frame?.spatial||{}, teams=[d.match.team1,d.match.team2], a=teams[0], b=teams[1];
  const events=frame?.events||[], actions=frame?.actions||[];
  const pressureA=Number(s.left_ball_pressure||0), pressureB=Number(s.right_ball_pressure||0);
  return `<div class="replay-side-stack">
    <section class="panel replay-score-card"><div class="mini-eyebrow">LIVE REPLAY</div><div class="replay-score"><span style="color:${TEAM_COLORS[0]}">${esc(a)}</span><strong>${frame?.score?.left??d.match.score1??0}</strong><i>:</i><strong>${frame?.score?.right??d.match.score2??0}</strong><span style="color:${TEAM_COLORS[1]}">${esc(b)}</span></div><div class="replay-mode">${esc(frame?.playmode||'play_on')}</div></section>
    <section class="panel"><div class="panel-title-row"><h3>Live Metrics</h3><span class="tiny muted">cycle ${frame?.cycle??'—'}</span></div>
      ${liveBar('Possession',s.possession_team,[a,b],[s.possession_team===a?100:0,s.possession_team===b?100:0],teams)}
      ${liveMetric('Pressure',pressureA,pressureB,teams)}
      ${liveMetric('Territory',Number(s.left_territory||0),Number(s.right_territory||0),teams,true)}
      ${liveMetric('Space',Number(s.left_space_control||0),Number(s.right_space_control||0),teams,true)}
    </section>
    <section class="panel replay-events-panel"><div class="panel-title-row"><h3>Current Events</h3><span class="badge">${events.length}</span></div><div class="mini-events">${events.length?events.map(e=>`<div class="mini-event"><span class="event-dot" style="background:${teamColor(e.team,teams)}"></span><div><strong>${esc(e.event_type)}</strong><small>${esc(e.team||'')} ${e.unum?`#${e.unum}`:''}</small></div></div>`).join(''):'<div class="tiny muted">No event at this cycle.</div>'}</div></section>
    <section class="panel replay-actions-panel"><div class="panel-title-row"><h3>Agent Actions</h3><span class="badge">${actions.length}</span></div><div class="mini-actions">${actions.slice(0,8).map(a=>`<div class="action-row"><span style="color:${teamColor(a.team,teams)}">#${a.unum}</span><code>${esc(a.action_type)}</code></div>`).join('')||'<div class="tiny muted">No sampled action.</div>'}</div></section>
  </div>`;
}
function liveBar(label,currentTeam,teams,vals){const a=vals[0],b=vals[1];return `<div class="live-stat"><div class="live-label"><span>${label}</span><span>${currentTeam?esc(currentTeam):'—'}</span></div><div class="duo-bar"><i style="width:${a}%;background:${TEAM_COLORS[0]}"></i><i style="width:${b}%;background:${TEAM_COLORS[1]}"></i></div></div>`}
function liveMetric(label,a,b,teams,percent=false){const max=Math.max(0.001,a+b), ap=percent?a/max*100:a/max*100, bp=percent?b/max*100:b/max*100;const av=percent?fmt(a,1)+'%':fmt(a,3),bv=percent?fmt(b,1)+'%':fmt(b,3);return `<div class="live-stat"><div class="live-label"><span>${label}</span><span><b style="color:${TEAM_COLORS[0]}">${av}</b> · <b style="color:${TEAM_COLORS[1]}">${bv}</b></span></div><div class="duo-bar"><i style="width:${ap}%;background:${TEAM_COLORS[0]}"></i><i style="width:${bp}%;background:${TEAM_COLORS[1]}"></i></div></div>`}

async function renderReplayTab(d,v){
  const m=state.replay.meta||await loadReplayMeta(d.match.id);
  if(!state.replay.frames.length) await loadReplayChunk(d.match.id,m.first_cycle||0);
  const frame=currentReplayFrame()||state.replay.frames[0];
  const teamA=d.match.team1,teamB=d.match.team2;
  const scrollY = window.scrollY;
  $('#match-body').innerHTML=`<div class="replay-layout"><section class="replay-panel"><div class="replay-head"><div><div class="mini-eyebrow">FULL MATCH REPLAY</div><h2>${esc(teamA)} <span>vs</span> ${esc(teamB)}</h2><div class="tiny muted">RCG world state + RCL actions + analytics analysis · sampled every ${state.replay.step} cycle</div></div><div class="replay-legend"><span><i style="background:${TEAM_COLORS[0]}"></i>${esc(teamA)}</span><span><i style="background:${TEAM_COLORS[1]}"></i>${esc(teamB)}</span></div></div><div class="replay-pitch-shell">${replayPitchSVG(frame,v,{trail:state.replay.trail,analysis:state.replay.overlay})}</div>${replayControls()}</section>${replaySidePanel(d,frame)}</div>`;
  requestAnimationFrame(()=>window.scrollTo(0, scrollY));
  $('#replay-play').onclick=toggleReplay;
  $('#replay-prev').onclick=()=>seekReplay(Math.max(0, currentReplayFrame()?currentReplayFrame().cycle-state.replay.step:0));
  $('#replay-next').onclick=()=>seekReplay((currentReplayFrame()?.cycle||0)+state.replay.step);
  $('#replay-trail').onclick=()=>{state.replay.trail=!state.replay.trail;renderReplayTab(d,v)};
  $$('.overlay-btn').forEach(b=>b.onclick=()=>{state.replay.overlay=b.dataset.overlay;renderReplayTab(d,v)});
  $('#replay-seek').oninput=e=>seekReplay(Number(e.target.value));
  $$('.speed-btn').forEach(b=>b.onclick=()=>{state.replay.speed=Number(b.dataset.speed);renderReplayTab(d,v)});
}

function seekReplay(cycle){
  const r=state.replay; if(!r.meta) return;
  const c=Math.max(r.meta.first_cycle||0,Math.min(r.meta.last_cycle||cycle,cycle));
  r.cursor=frameIndexForCycle(c); const f=r.frames[r.cursor];
  if(f && c>=(r.end-r.chunk*0.25) && r.end<r.meta.last_cycle) loadReplayChunk(state.match.match.id,r.end+1).then(()=>{r.cursor=frameIndexForCycle(c);renderReplayTab(state.match,state.visuals)});
  else renderReplayTab(state.match,state.visuals);
}

function stopReplay(){if(state.replay.timer){clearInterval(state.replay.timer);state.replay.timer=null}state.replay.playing=false}
async function toggleReplay(){
  const r=state.replay;
  if(r.playing){stopReplay();renderReplayTab(state.match,state.visuals);return;}
  r.playing=true;
  renderReplayTab(state.match,state.visuals);
  if(r.timer) clearInterval(r.timer);
  r.timer=setInterval(async()=>{
    if(!r.playing) return;
    if(r.cursor>=r.frames.length-1){
      if(r.end<r.meta.last_cycle){try{await loadReplayChunk(state.match.match.id,r.end+1)}catch(e){stopReplay();toast(e.message);return}}
      if(r.cursor>=r.frames.length-1){stopReplay();renderReplayTab(state.match,state.visuals);return}
    }
    r.cursor=Math.min(r.cursor+1,r.frames.length-1);
    if(state.tab==='replay') renderReplayTab(state.match,state.visuals);
  }, Math.max(25,100/r.speed));
}

/* Replaced match navigation/render with replay-aware version. */
async function openMatch(id){
  try{
    stopReplay();
    const [d,v,m]=await Promise.all([get(`/api/matches/${id}`),get(`/api/matches/${id}/visuals`),get(`/api/matches/${id}/replay/meta`)]);
    state.match=d;state.visuals=v;state.tab='replay';state.replay={meta:m,frames:[],cursor:0,playing:false,timer:null,start:m.first_cycle||0,end:0,step:1,chunk:400,loading:false,speed:1,trail:true,overlay:'clean'};
    setView('match');renderMatch();
  }catch(e){setView('match');$('#match').innerHTML=`<div class="error">${esc(e.message)}</div>`}
}
function renderMatch(){
  const d=state.match,v=state.visuals,m=d.match;
  $('#page-title').textContent=`${m.team1} ${m.score1??'–'} — ${m.score2??'–'} ${m.team2}`;
  const tabs=[['replay','▶ Replay'],['overview','Overview'],['intelligence','Intelligence'],['tactics','Tactics'],['passing','Passing'],['shooting','Shooting'],['players','Players'],['events','Events'],['actions','Actions'],['reports','Reports']];
  $('#match').innerHTML=`${hero(d)}<div class="tabs">${tabs.map(([id,label])=>`<button class="tab ${state.tab===id?'active':''}" data-tab="${id}">${label}</button>`).join('')}</div><div id="match-body"></div>`;
  $$('.tab',$('#match')).forEach(b=>b.onclick=()=>{stopReplay();state.tab=b.dataset.tab;renderMatch()});
  const body=$('#match-body');
  if(state.tab==='replay'){body.innerHTML='<div class="loading">Loading replay…</div>';renderReplayTab(d,v)}
  else body.innerHTML=state.tab==='overview'?overviewHtml(d,v):state.tab==='intelligence'?intelligenceHtml(d):state.tab==='tactics'?tacticsHtml(d,v):state.tab==='passing'?passingHtml(v):state.tab==='shooting'?shootingHtml(v):state.tab==='players'?playersHtml(d):state.tab==='events'?eventsHtml(v):state.tab==='actions'?actionsHtml(d):'<div class="loading">Generating report graphics…</div>';
  if(state.tab==='reports') loadGraphics(d.match.id).then(html=>$('#match-body').innerHTML=html);
}

window.addEventListener('DOMContentLoaded',initTheme);
