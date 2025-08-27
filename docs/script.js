async function load(){
  const resp = await fetch('../report/compliance-report.json');
  const data = await resp.json();
  const rows = Object.entries(data).map(([path,obj])=>buildRowObj(path,obj));
  window._allRows = rows;
  render(rows);
  attachFilters();
}

function buildRowObj(path,obj){
  // Parse filename tokens (assuming underscores separate DRS style pieces near end)
  const fname = path.split('/').pop();
  // Example pattern variable_DOMAIN_DRIVINGSRC_DRIVINGEXP_variant_INSTITUTION_RCM_version_frequency_timerange.nc
  const base = fname.replace('.nc','');
  const parts = base.split('_');
  // Heuristic mapping (adjust if needed):
  let variable = parts[0];
  let domain = parts[1];
  let driving_source = parts[2];
  let driving_experiment = parts[3];
  let variant = parts[4];
  let institution = parts[5];
  let rcm = parts[6];
  let version = parts[7];
  let frequency = parts[8];
  let timerange = parts[9] || '';
  const cc6 = obj.cc6||{}; const cf = obj.cf||{};
  const cc6Pct = pct(cc6.scored_points, cc6.possible_points);
  const cfPct = pct(cf.scored_points, cf.possible_points);
  // Collect msgs (Required only for now)
  const msgs = [];
  (cc6.high_priorities||[]).forEach(p=>{ if(p.msgs && p.msgs.length){ msgs.push(`[${p.name}] `+p.msgs.join(' | ')); } });
  return {path,variable,domain,driving_source,driving_experiment,variant,institution,rcm,version,frequency,timerange,cc6Pct,cfPct,cc6high:cc6.high_count,cc6medium:cc6.medium_count,msgs};
}

function pct(a,b){ if(!a||!b) return 0; return +(100*a/b).toFixed(1); }

function render(rows){
  const tbody = document.querySelector('#results tbody');
  tbody.innerHTML='';
  const tmpl = document.querySelector('#row-template');
  rows.forEach(r=>{
    const clone = tmpl.content.cloneNode(true);
    setText(clone,'.var', r.variable);
    setText(clone,'.activity', 'CORDEX-CMIP6'); // static or parse if added
    setText(clone,'.domain', r.domain);
    setText(clone,'.institution', r.institution);
    setText(clone,'.driving_source', r.driving_source);
    setText(clone,'.driving_experiment', r.driving_experiment);
    setText(clone,'.variant', r.variant);
    setText(clone,'.rcm', r.rcm);
    setText(clone,'.frequency', r.frequency);
    setText(clone,'.years', r.timerange.slice(0,4)+'-'+r.timerange.slice(13,17));
    setScore(clone,'.cc6score', r.cc6Pct);
    setScore(clone,'.cfscore', r.cfPct);
    setText(clone,'.cc6high', r.cc6high);
    setText(clone,'.cc6medium', r.cc6medium);
    const msgCell = clone.querySelector('.msgs');
    if(r.msgs.length){
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = r.msgs.length + ' msgs';
      details.appendChild(summary);
      const list = document.createElement('div');
      list.className='msgs-list';
      r.msgs.forEach(m=>{
        const d = document.createElement('div'); d.textContent = m; list.appendChild(d);
      });
      details.appendChild(list);
      msgCell.appendChild(details);
    }
    tbody.appendChild(clone);
  });
  updateSummary(rows);
}

function setText(root,sel,val){ const el = root.querySelector(sel); if(el) el.textContent = val==null?'':val; }
function setScore(root,sel,val){ const el = root.querySelector(sel); if(!el) return; el.textContent = val.toFixed(1)+'%'; el.className=sel.slice(1)+' '+scoreClass(val);}
function scoreClass(v){ if(v>=95) return 'good'; if(v>=80) return 'ok'; return 'bad'; }

function attachFilters(){
  document.getElementById('btn-clear').addEventListener('click',()=>{ document.querySelectorAll('#controls input').forEach(i=>i.value=''); applyFilters(); });
  document.querySelectorAll('#controls input').forEach(i=> i.addEventListener('input', debounce(applyFilters,250)) );
}

function applyFilters(){
  const f = id=>document.getElementById(id).value.trim().toLowerCase();
  const minCc6 = parseFloat(document.getElementById('f-cc6-min').value)||0;
  const maxCc6 = parseFloat(document.getElementById('f-cc6-max').value)||100;
  const minCf = parseFloat(document.getElementById('f-cf-min').value)||0;
  const maxCf = parseFloat(document.getElementById('f-cf-max').value)||100;
  const priority = f('f-priority');
  const checkSub = f('f-check');
  const rows = window._allRows.filter(r=>{
    if(f('f-domain') && !r.domain.toLowerCase().includes(f('f-domain'))) return false;
    if(f('f-institution') && !r.institution.toLowerCase().includes(f('f-institution'))) return false;
    if(f('f-driving_source') && !r.driving_source.toLowerCase().includes(f('f-driving_source'))) return false;
    if(f('f-driving_experiment') && !r.driving_experiment.toLowerCase().includes(f('f-driving_experiment'))) return false;
    if(f('f-rcm') && !r.rcm.toLowerCase().includes(f('f-rcm'))) return false;
    if(f('f-variant') && !r.variant.toLowerCase().includes(f('f-variant'))) return false;
    if(f('f-frequency') && !r.frequency.toLowerCase().includes(f('f-frequency'))) return false;
    if(f('f-variable') && !r.variable.toLowerCase().includes(f('f-variable'))) return false;
    if(r.cc6Pct<minCc6 || r.cc6Pct>maxCc6) return false;
    if(r.cfPct<minCf || r.cfPct>maxCf) return false;
    if(checkSub){ const match = r.msgs.some(m=> m.toLowerCase().includes(checkSub)); if(!match) return false; }
    if(priority){ const p = priority; const match = r.msgs.some(m=> m.toLowerCase().includes(p)); if(!match) return false; }
    if(f('f-activity')){ /* static currently */ }
    return true;
  });
  render(rows);
}

function debounce(fn,ms){ let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn.apply(this,args),ms); } }

function updateSummary(rows){
  const el = document.getElementById('summary');
  const total = rows.length;
  const avgCc6 = avg(rows.map(r=>r.cc6Pct));
  const avgCf = avg(rows.map(r=>r.cfPct));
  el.innerHTML = '';
  el.appendChild(badge('Files', total));
  el.appendChild(badge('Avg cc6', avgCc6.toFixed(1)+'%'));
  el.appendChild(badge('Avg CF', avgCf.toFixed(1)+'%'));
}
function badge(label,val){ const d=document.createElement('div'); d.className='badge'; d.innerHTML = `<span>${label}</span> ${val}`; return d; }
function avg(arr){ return arr.length?arr.reduce((a,b)=>a+b,0)/arr.length:0; }

load();
