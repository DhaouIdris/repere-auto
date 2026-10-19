'use strict';
const $ = (id) => document.getElementById(id);
const money = (c) => c == null ? 'Non renseigné' : new Intl.NumberFormat('fr-FR', {style:'currency',currency:'EUR',maximumFractionDigits:0}).format(c/100);
const number = (n) => n == null ? '—' : new Intl.NumberFormat('fr-FR').format(n);
const filterNames={brand:'Marque',model:'Modèle',fuel:'Énergie',gearbox:'Boîte',seller:'Vendeur',region:'Région',max_price_eur:'Budget maximum (€)',max_mileage:'Kilométrage maximum',min_year:'Année minimum',min_discount:'Remise minimum (%)',radius_km:'Rayon (km)',latitude:'Latitude',longitude:'Longitude',sort:'Tri',only_deals:'Écarts retenus uniquement'};
const stamp = (d) => d ? new Intl.DateTimeFormat('fr-FR',{dateStyle:'short',timeStyle:'short'}).format(new Date(d)) : 'Jamais';
let csrf = '', mode = 'demo', currentFilters = {}, offset = 0, visibleRows = [], requestSerial = 0;
const node = (tag, text, cls) => { const el = document.createElement(tag); if(text != null) el.textContent = text; if(cls) el.className=cls; return el; };
function error(message) { $('global-error').textContent=message; $('global-error').hidden=!message; }
async function api(path, options={}) {
  const headers = {'Accept':'application/json',...options.headers};
  if(options.body) headers['Content-Type']='application/json';
  if(csrf) headers['X-CSRF-Token']=csrf;
  const r = await fetch(path,{...options,headers,signal:AbortSignal.timeout(15000)});
  let data; try {data=await r.json();} catch {throw new Error('Réponse du service illisible');}
  if(!r.ok) {if(r.status===401) login(); throw new Error(data.error || `Erreur ${r.status}`);}
  return data;
}
function login() { $('login').hidden=false; $('app').hidden=true; }
function busy(target) {target.replaceChildren(node('p','Chargement des données…','loading'));}
function empty(target,message) {target.replaceChildren(node('div',message,'empty'));}
async function view(name) {
  error('');
  document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==`view-${name}`);
  document.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===name));
  $('breadcrumb').textContent='Votre espace / '+({dashboard:'Vue d’ensemble',search:'Explorer',saved:'Mes recherches',sources:'Sources & imports'}[name]);
  try { if(name==='dashboard') await dashboard(); if(name==='search') await search(); if(name==='saved') await saved(); if(name==='sources') await sources(); }
  catch(e) {error(e.message);}
}
function table(target,rows) {
  if(!rows.length) return empty(target,'Aucun véhicule pour ces critères. Élargissez votre recherche ou importez un jeu de données autorisé.');
  const wrap=node('div',null,'table-wrap'), t=node('table'), head=node('thead'), hr=node('tr');
  ['Véhicule','Prix demandé','Référence annonces','Écart','Indicateurs',''].forEach(s=>hr.append(node('th',s)));
  head.append(hr);t.append(head); const body=node('tbody');
  for(const r of rows) {
    const tr=node('tr'),car=node('td'), vehicle=node('div',null,'vehicle'), icon=node('span','↗','car-icon'), title=node('div');
    title.append(node('strong',`${r.brand||'Marque inconnue'} ${r.model||''}`),node('small',`${r.engine||'Moteur inconnu'} · ${r.year||'Année inconnue'} · ${number(r.mileage_km)} km`));
    title.append(node('small',r.valuation.opportunity?'À examiner':'Critères non réunis','mobile-state'));
    vehicle.append(icon,title);car.append(vehicle);tr.append(car,node('td',money(r.price_cents)),node('td',r.valuation.market_price_cents==null?'Non estimable':money(r.valuation.market_price_cents)));
    const pct=r.valuation.discount_pct, discount=node('td');discount.append(node('span',pct==null?'—':`${number(pct)} %`,'discount'+(r.valuation.opportunity?'':' warn')));tr.append(discount);
    const status=node('td');status.append(node('span',r.valuation.opportunity?'À examiner':(pct==null?'Données insuffisantes':'Critères non réunis'),'tag'+(r.valuation.opportunity?'':' warn')));
    status.append(node('small',`${r.valuation.effective_comparables} réf. · ${r.city||'Lieu inconnu'}${r.distance_km==null?'':` · ${r.distance_km} km`}`));
    const action=node('td'),button=node('button','Voir ↗','open-detail');button.type='button';button.addEventListener('click',()=>detail(r.id));action.append(button);tr.append(status,action);body.append(tr);
  }
  t.append(body);wrap.append(t);target.replaceChildren(wrap);
}
async function dashboard() {
  busy($('dashboard-table'));
  const [summary,data]=await Promise.all([api('/api/summary'),api('/api/listings?only_deals=true&limit=8')]);
  $('kpi-vehicles').textContent=number(summary.vehicles);$('kpi-estimated').textContent=number(summary.estimated);
  $('kpi-deals').textContent=number(summary.opportunities);$('kpi-alerts').textContent=number(summary.pending_alerts);
  $('kpi-raw').textContent=`${summary.raw_listings} annonces avant regroupement probable`;
  $('hero-discount').textContent=summary.best_discount==null?'—':`${number(summary.best_discount)} %`;
  $('updated').textContent='Calculé le '+stamp(summary.as_of);table($('dashboard-table'),data.listings);
}
function readFilters() {
  const f={};for(const [key,value] of new FormData($('filters'))) {if(value!=='')f[key]=key==='only_deals'?true:value;}
  return f;
}
async function search(append=false) {
  const serial=++requestSerial;
  if(!append) {offset=0;visibleRows=[];busy($('search-table'));currentFilters=readFilters();}
  const q=new URLSearchParams({...currentFilters,offset:String(offset),limit:'60'});
  const result=await api('/api/listings?'+q);
  if(serial!==requestSerial) return;
  visibleRows.push(...result.listings);offset=visibleRows.length;
  table($('search-table'),visibleRows);$('result-count').textContent=`${number(result.total)} véhicule${result.total>1?'s':''}`;
  $('load-more').hidden=offset>=result.total;
}
async function detail(id) {
  const target=$('detail-content');busy(target);if(!$('detail').open)$('detail').showModal();
  try {
    const r=await api('/api/listings/'+encodeURIComponent(id)),v=r.valuation;
    target.replaceChildren(node('span',mode==='demo'?'FICHE SYNTHÉTIQUE':'PRIX DEMANDÉ OBSERVÉ','eyebrow'),node('h1',`${r.brand||'Véhicule'} ${r.model||''}`),node('p',`${r.generation||'Génération inconnue'} · ${r.trim||'Finition inconnue'} · ${r.engine||'Moteur inconnu'}`,'intro'));
    const prices=node('div',null,'detail-prices');
    for(const [label,value] of [['Prix demandé',money(r.price_cents)],['Référence annonces',v.market_price_cents==null?'Indisponible':money(v.market_price_cents)],['Écart estimé',v.discount_pct==null?'—':`${number(v.discount_pct)} %`]]) {const box=node('div',label);box.append(node('strong',value));prices.append(box);}target.append(prices);
    const reasons=node('div',null,'reasons');v.reasons.forEach(s=>reasons.append(node('div','• '+s)));target.append(reasons);
    const metadata=node('dl',null,'detail-meta');
    for(const [label,value] of [['Kilométrage',`${number(r.mileage_km)} km`],['Énergie',r.fuel],['Boîte',r.gearbox],['Vendeur',r.seller],['Localisation',`${r.postal_code||''} ${r.city||''}`],['Crit’Air',r.critair??'Non déterminé'],['Références effectives',v.effective_comparables],['Confiance descriptive',v.confidence],['Publication',stamp(r.published_at)],['Observation',stamp(r.observed_at)],['Première ingestion',stamp(r.first_seen)],['Dernier changement',stamp(r.last_price_change)]]){const box=node('div');box.append(node('dt',label),node('dd',String(value??'Non renseigné')));metadata.append(box);}target.append(metadata);
    if(v.market_price_cents!=null){target.append(node('p',`Quartiles observés : ${money(v.q25_cents)} à ${money(v.q75_cents)}. Dispersion IQR / médiane : ${number(100*v.iqr_ratio)} %. Ces quartiles ne constituent pas un intervalle de confiance.`,'muted'));if(v.sensitivity_discount_range)target.append(node('p',`En retirant une référence à la fois, la remise varie de ${number(v.sensitivity_discount_range[0])} à ${number(v.sensitivity_discount_range[1])} %.`, 'muted'));}
    target.append(node('h2','Historique du groupe probable'));const history=node('ul',null,'history');(r.group_price_history||r.price_history).forEach(p=>{const li=node('li');li.append(node('span',stamp(p.observed_at)+(p.source?' · '+p.source:'')),node('strong',money(p.price_cents)));history.append(li);});target.append(history);
    target.append(node('h2','Annonces de référence'));if(!v.comparables.length)target.append(node('p','Aucune référence compatible disponible.','muted'));else{const list=node('ul',null,'history');v.comparables.forEach(p=>{const li=node('li'),b=node('button',`${p.year} · ${number(p.mileage_km)} km · ${money(p.price_cents)}`,'open-detail');b.addEventListener('click',()=>detail(p.id));li.append(b,node('span',p.source));list.append(li);});target.append(list);}
    target.append(node('h2','Informations déclarées'));for(const key of ['defects','maintenance','inspection','accident_claim','warranty','description'])if(r[key])target.append(node('p',r[key],'muted'));
    target.append(node('p',`Provenance : ${r.source} · ${r.rights_reference}. ${r.duplicates.length} republication(s) probable(s) regroupée(s). Champs indispensables manquants : ${v.missing_fields.join(', ')||'aucun'}.`,'muted'));
    if(r.flags.length)target.append(node('p','Drapeaux : '+r.flags.join(', '),'muted'));
    if(r.url){const a=node('a','Ouvrir l’annonce d’origine ↗','button dark');a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';target.append(a);}
    target.append(node('p','Cette fiche ne remplace ni l’inspection ni la vérification des documents. Les prix de vente finaux ne sont pas connus.','footnote'));
  } catch(e){target.replaceChildren(node('p',e.message,'error'));}
}
async function saved() {
  busy($('saved-list'));const [s,a]=await Promise.all([api('/api/searches'),api('/api/alerts')]);
  $('saved-list').replaceChildren();
  if(!s.searches.length)empty($('saved-list'),'Aucune recherche enregistrée. Choisissez des filtres dans Explorer, puis sauvegardez-les.');
  for(const search of s.searches){const card=node('article',null,'info-card');card.append(node('h3',search.name),node('p',Object.entries(search.filters).map(([k,v])=>`${filterNames[k]||k} : ${v===true?'oui':v}`).join(' · ')||'Tous les véhicules compatibles avec les règles générales'));const actions=node('div',null,'actions'),apply=node('button','Explorer ↗','button light'),remove=node('button','Supprimer','button light');apply.addEventListener('click',()=>{ $('filters').reset();for(const [k,v] of Object.entries(search.filters)){const el=$('filters').elements.namedItem(k);if(el){if(el.type==='checkbox')el.checked=!!v;else el.value=v;}}view('search');});remove.addEventListener('click',async()=>{try{await api('/api/searches/'+search.id,{method:'DELETE'});await saved();}catch(e){error(e.message);}});actions.append(apply,remove);card.append(actions);$('saved-list').append(card);}
  $('alert-list').replaceChildren();if(!a.alerts.length)empty($('alert-list'),'Aucune alerte créée. Les correspondances apparaîtront ici.');
    for(const item of a.alerts){const row=node('article',null,'alert-row'),left=node('div'),p=item.payload;left.append(node('strong',p.vehicle),node('small',`${p.search_name} · ${p.event} · ${money(p.price_cents)} · ${p.discount_pct} %`),node('small',item.last_error||stamp(item.created_at)));row.append(left,node('span',({pending:'En attente',inflight:'En cours',sent:'Traitée',failed:'Échec',cancelled:'Annulée'}[item.state])||item.state,'tag'+(item.state==='failed'?' bad':'')));$('alert-list').append(row);}
}
async function sources() {
  busy($('source-list'));const data=await api('/api/sources');$('source-list').replaceChildren();
  for(const source of data.sources){const card=node('article',null,'info-card');card.append(node('h3',({demo:'Jeu synthétique',leboncoin:'Leboncoin',lacentrale:'La Centrale',autoscout24:'AutoScout24 France',paruvendu:'ParuVendu',export:'Exports autorisés'}[source.source])),node('span',source.live_status==='blocked_permission'?'LIVE INDISPONIBLE':source.live_status==='synthetic'?'DÉMONSTRATION':'IMPORT LOCAL','tag'+(source.live_status==='blocked_permission'?' warn':'')),node('p',source.message),node('p',`Dernier import réussi : ${stamp(source.import?.last_success)} · ${source.import?.imported||0} observations · ${source.import?.freshness==='perime'?'Données périmées':source.import?.freshness==='recent'?'Import récent':'Aucun import'}`));if(source.import?.last_error)card.append(node('p',`Échecs : ${source.import.failures}. ${source.import.last_error}`,'error'));$('source-list').append(card);}
  $('import-help').textContent=mode==='demo'?'Base synthétique uniquement. Les imports réels nécessitent un lancement séparé en mode import.':'Base de données réelles autorisées. Aucune donnée synthétique ne sera acceptée.';
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
$('explore').addEventListener('click',()=>view('search'));
$('close-detail').addEventListener('click',()=>$('detail').close());
$('filters').addEventListener('submit',e=>{e.preventDefault();search().catch(e=>error(e.message));});
$('filters').addEventListener('reset',()=>queueMicrotask(()=>search().catch(e=>error(e.message))));
$('load-more').addEventListener('click',()=>search(true).catch(e=>error(e.message)));
$('save-current').addEventListener('click',()=>{currentFilters=readFilters();view('saved');$('search-name').focus();});
$('save-form').addEventListener('submit',async e=>{e.preventDefault();try{currentFilters=readFilters();const result=await api('/api/searches',{method:'POST',body:JSON.stringify({name:$('search-name').value,filters:currentFilters})});$('saved-feedback').textContent=`Recherche sauvegardée. ${result.queued} correspondance(s) créée(s).`;$('search-name').value='';await saved();}catch(e){error(e.message);}});
$('simulate').addEventListener('click',async()=>{try{$('simulate').disabled=true;const r=await api('/api/run-alerts',{method:'POST'});$('saved-feedback').textContent=`Simulation locale : ${r.delivery.simulated||0} alerte(s) prévisualisée(s), aucun message externe envoyé. Les envois réels restent en attente.`;await saved();}catch(e){error(e.message);}finally{$('simulate').disabled=false;}});
$('import-file').addEventListener('change',async()=>{const f=$('import-file').files[0];if(!f)return;if(f.size>1048576){error('Fichier limité à 1 Mio');return;}$('import-body').value=await f.text();});
$('import-form').addEventListener('submit',async e=>{e.preventDefault();try{let data;if($('import-format').value==='json')data=JSON.parse($('import-body').value);else data={schema_version:1,source:$('import-source').value,rights_reference:$('import-rights').value,format:'csv',csv:$('import-body').value};data.authorized=$('import-authorized').checked;const result=await api('/api/import',{method:'POST',body:JSON.stringify(data)});$('import-result').textContent=`Import terminé : ${result.inserted} ajout(s), ${result.updated} mise(s) à jour, ${result.price_changes} changement(s) de prix.`;await sources();}catch(e){$('import-result').textContent=e.message;}});
$('login-form').addEventListener('submit',async e=>{e.preventDefault();try{const data=await api('/api/login',{method:'POST',body:JSON.stringify({token:$('token').value})});csrf=data.csrf;$('token').value='';await initialize();}catch(e){$('login-error').textContent=e.message;}});
$('logout').addEventListener('click',async()=>{try{await api('/api/logout',{method:'POST'});csrf='';login();}catch(e){error(e.message);}});
async function initialize(){try{const session=await api('/api/session');mode=session.mode;if(!session.authenticated){login();return;}csrf=session.csrf;$('login').hidden=true;$('app').hidden=false;$('demo-banner').hidden=mode!=='demo';$('mode-badge').textContent=mode==='demo'?'DÉMO SYNTHÉTIQUE':'IMPORTS AUTORISÉS';await view('dashboard');}catch(e){login();$('login-error').textContent=e.message;}}
initialize();
