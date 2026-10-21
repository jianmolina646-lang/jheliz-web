export function enhanceMobileTables(root){
 for(const table of root.querySelectorAll('table')){
  const headers=[...(table.tHead?.rows[0]?.cells||[])];
  if(!headers.length||headers.some(h=>h.colSpan!==1))continue;
  table.dataset.mobileCards='';table.setAttribute('role','table');
  for(const group of [table.tHead,...table.tBodies])if(group)group.setAttribute('role','rowgroup');
  for(const header of headers){header.setAttribute('scope','col');header.setAttribute('role','columnheader');}
  for(const row of table.rows){row.setAttribute('role','row');}
  for(const body of table.tBodies)for(const row of body.rows){
   [...row.cells].forEach((cell,n)=>{
    cell.setAttribute('role','cell');
    if(cell.colSpan===1)cell.dataset.label=headers[n]?.textContent.trim()||'Detalle';
   });
  }
 }
}
export function setupMobileUI(){
 const root=document.querySelector('#content');if(!root)return;
 enhanceMobileTables(root);
 new MutationObserver(()=>enhanceMobileTables(root)).observe(root,{childList:true,subtree:true});
 const backdrop=document.createElement('button');backdrop.type='button';backdrop.className='mobile-nav-backdrop';
 backdrop.setAttribute('aria-label','Cerrar navegación');backdrop.tabIndex=-1;document.body.append(backdrop);
 const close=()=>{
  document.body.classList.remove('navigation-open');
  const toggle=document.querySelector('.mobile-menu');toggle?.setAttribute('aria-expanded','false');
  toggle?.focus();
 };
 backdrop.addEventListener('click',close);
 const syncNavigation=()=>{
  const mobile=matchMedia('(max-width:750px)').matches;
  const open=document.body.classList.contains('navigation-open');
  const sidebar=document.querySelector('#shell aside');if(sidebar)sidebar.inert=mobile&&!open;
  const toggle=document.querySelector('.mobile-menu');
  toggle?.setAttribute('aria-label',open?'Cerrar navegación':'Abrir navegación');
 };
 new MutationObserver(syncNavigation).observe(document.body,{attributes:true,attributeFilter:['class']});
 syncNavigation();
 matchMedia('(max-width:750px)').addEventListener('change',syncNavigation);
 matchMedia('(max-width:750px)').addEventListener('change',()=>{if(document.body.classList.contains('navigation-open'))close();});
 document.addEventListener('focusin',e=>{
  if(!matchMedia('(max-width:750px)').matches||!document.body.classList.contains('navigation-open'))return;
  if(!e.target.closest('aside,.mobile-menu'))close();
 });
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('navigation-open'))close();});
}
if(typeof document!=='undefined')setupMobileUI();
