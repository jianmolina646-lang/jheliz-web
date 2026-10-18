const paths={overview:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',connections:'M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9H13a8.5 8.5 0 0 1 8 8v.5z',commands:'m8 5-7 7 7 7m8-14 7 7-7 7m-3-17-2 20',catalog:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',inventory:'m3 7 9-4 9 4v10l-9 4-9-4V7zm0 0 9 4 9-4m-9 4v10',orders:'M7 3h10l3 4v14H4V7l3-4zm-3 4h16M9 12h6m-6 4h4',reports:'M4 3h16v18H4zM4 9h16M10 9v12m5-12v12M4 15h16',support:'M4 13v-2a8 8 0 0 1 16 0v2M4 11H2v7h4v-7H4zm16 0h2v7h-4v-7h2zm0 7v3h-7',events:'m2 12 5 0 3-8 4 16 3-8h5',team:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m18 0v-2a4 4 0 0 0-3-4M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m7-8a4 4 0 0 1 0 8',audit:'M6 3h12v18H6zM9 8h6m-6 4h6m-6 4h4',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2'};
const icon=name=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.overview}"/></svg>`;
Object.assign(paths,{deliveries:'M1 3h13v13H1zM14 8h4l4 5v3h-8M5 16a3 3 0 1 0 0 6 3 3 0 0 0 0-6m13 0a3 3 0 1 0 0 6 3 3 0 0 0 0-6',customers:paths.team,renewals:'M3 10a9 9 0 0 1 16-5l2 3M21 2v6h-6M21 14a9 9 0 0 1-16 5l-2-3M3 22v-6h6'});
export function brandKey(value){const v=String(value??'').trim().toLowerCase().replace(/[_-]+/g,' ').replace(/\s+/g,' ');return /^netflix\b/.test(v)?'netflix':/^(prime(?:video)?|amazon prime(?: video)?)\b/.test(v)?'prime':/^crunchy\s?roll\b/.test(v)?'crunchyroll':/^disney\b/.test(v)?'disney':/^(hbo\s*)?max\b/.test(v)?'max':null;}
const tone=text=>/^(Entregado|Disponible|Vendida|Registrado|Resuelto|Activo|Sí)$/.test(text)?'good':/Rechazado|Retirada|Revisar|Error|Vencida/.test(text)?'bad':/Pendiente|Aprobado|En atención|Abierto|Entregando/.test(text)?'warn':null;
export const navigationGroups=[['Inicio',['overview']],['Ventas',['customers','orders','renewals','deliveries']],['Productos',['catalog','inventory']],['WhatsApp',['connections','commands','support']],['Control',['reports','events','history']],['Administración',['team','audit','settings']]];
export function setupModernUI(){
 const nav=document.querySelector('nav');nav.id='workspace-navigation';nav.setAttribute('aria-label','Navegación principal');
 for(const button of nav.querySelectorAll('button[data-view]')){const label=button.querySelector('span')?.textContent||button.textContent.trim();button.innerHTML=icon(button.dataset.view)+'<span></span>';button.lastElementChild.textContent=label;}
 for(const [label,views] of navigationGroups){const group=document.createElement('details');group.className='navigation-group';group.open=true;const title=document.createElement('summary');title.textContent=label;group.append(title);for(const view of views){const button=nav.querySelector(`[data-view="${view}"]`);if(button)group.append(button);}nav.append(group);}
 const syncGroups=()=>{for(const group of nav.querySelectorAll('.navigation-group')){const hidden=![...group.querySelectorAll('[data-view]')].some(button=>!button.hidden);if(group.hidden!==hidden)group.hidden=hidden;}};
 new MutationObserver(syncGroups).observe(nav,{subtree:true,attributes:true,attributeFilter:['hidden']});syncGroups();
 const toggle=document.createElement('button');toggle.className='mobile-menu';toggle.type='button';toggle.setAttribute('aria-controls',nav.id);toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-label','Abrir navegación');toggle.innerHTML=icon('overview');
 document.querySelector('main header').prepend(toggle);
 const close=()=>{document.body.classList.remove('navigation-open');toggle.setAttribute('aria-expanded','false');};
 toggle.onclick=()=>{const open=document.body.classList.toggle('navigation-open');toggle.setAttribute('aria-expanded',String(open));};
 nav.addEventListener('click',e=>{if(e.target.closest('button'))close();});document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
 const footer=document.querySelector('.main-footer');footer.lastElementChild.textContent='Espacio privado · Jheliz Control';
}
export function decorateView(view){
 const root=document.querySelector('#content');root.dataset.page=view;
 if(view==='orders')setupOrderFilters(root);
 if(root.dataset.previousPage!==view){window.scrollTo({top:0,behavior:'instant'});root.dataset.previousPage=view;}
 if(view==='customers')setupClientsReference(root);
 if(view==='deliveries')setupDeliveryFilters(root);
 const activeGroup=document.querySelector(`nav [data-view="${view}"]`)?.closest('details');if(activeGroup)activeGroup.open=true;
 for(const b of document.querySelectorAll('nav button')){if(b.dataset.view===view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
 for(const td of root.querySelectorAll('td')){
  const text=td.textContent.trim();if(td.childElementCount===0&&tone(text)){const tag=document.createElement('span');tag.className='pill '+tone(text);tag.textContent=text;td.replaceChildren(tag);}
  if(view==='catalog'&&td.cellIndex!==0)continue;
  const node=Array.from(td.childNodes).find(n=>n.nodeType===3&&brandKey(n.textContent));if(node){const name=brandKey(node.textContent),wrap=document.createElement('span');wrap.className='platform-label';const mark=document.createElement('img');mark.src='/brands/'+name+'.png';mark.dataset.brand=name;mark.alt='';mark.width=['prime','crunchyroll'].includes(name)?72:32;mark.height=['prime','crunchyroll'].includes(name)?40:32;mark.addEventListener('error',()=>mark.remove(),{once:true});const label=document.createElement('span');label.textContent=node.textContent;wrap.append(mark,label);node.replaceWith(wrap);}
 }
 const table=root.querySelector('.table-scroll table');
 if(table&&['inventory','catalog'].includes(view)){
  const rows=[...table.querySelectorAll('tbody tr')];
  const cells=rows.map(r=>[...r.cells].map(c=>c.textContent.trim()));
  const specs=view==='inventory'?[['Cuentas cargadas',rows.length],['Disponibles',cells.filter(c=>c[2]==='Disponible').length],['Vendidas',cells.filter(c=>c[2]==='Vendida').length]]:view==='orders'?[['Pedidos cargados',rows.length],['Entregados',cells.filter(c=>c[2]==='Entregado').length],['Pagos pendientes',cells.filter(c=>c[2]==='Pago pendiente').length]]:[['Productos cargados',rows.length],['Visibles',cells.filter(c=>c[5]==='Sí').length],['Con stock',cells.filter(c=>Number(c[4])>0).length]];
  const summary=document.createElement('section');summary.className='workspace-metrics';summary.setAttribute('aria-label','Resumen de los registros cargados');
  for(const [label,value] of specs){const card=document.createElement('div');card.className='workspace-metric';const name=document.createElement('span'),number=document.createElement('strong');name.textContent=label;number.textContent=String(value);card.append(name,number);summary.append(card);}
  table.parentElement.before(summary);
 }
 if(table&&!['customers','orders','deliveries'].includes(view)){const tools=document.createElement('div');tools.className='table-tools';const label=document.createElement('label');label.className='table-search';label.textContent='Buscar en esta tabla';const input=document.createElement('input');input.type='search';input.placeholder='Cliente, plataforma, estado…';label.append(input);const count=document.createElement('span');count.className='table-count';const rows=Array.from(table.querySelectorAll('tbody tr'));const update=()=>{const query=input.value.trim().toLocaleLowerCase('es');let shown=0;for(const row of rows){row.hidden=!row.textContent.toLocaleLowerCase('es').includes(query);if(!row.hidden)shown++;}count.textContent=shown+' de '+rows.length+' registros cargados';};input.addEventListener('input',update);update();tools.append(label,count);table.parentElement.before(tools);}
 const old=root.querySelector('.section-note');if(view==='overview'&&old)old.textContent='Tu operación en un solo lugar: WhatsApp, catálogo, inventario, pagos, soporte y reportes.';
 const mark=root.querySelector('.hero-mark');if(mark){mark.innerHTML=icon('connections');}
 root.querySelectorAll('dialog button').forEach(b=>{if(b.textContent.trim()==='✕')b.setAttribute('aria-label','Cerrar');});
}
import {setupOrderFilters} from './orders-workspace.js?v=1.1.0';
import {setupClientsReference} from './clients-reference.js?v=1.0.0';
import {setupDeliveryFilters} from './deliveries-reference.js?v=1.0.0';
