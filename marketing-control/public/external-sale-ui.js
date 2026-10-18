export function setupExternalSale({api,h,notify,render}){
 const dialog=document.createElement('dialog');document.body.append(dialog);
 document.addEventListener('click',async e=>{
  if(!e.target.closest('[data-external-sale]'))return;
  try{
   const [products,instances,stock]=await Promise.all([api('/products'),api('/instances'),api('/external-stock')]);
   const connected=instances.filter(i=>i.status==='CONNECTED'&&i.purpose==='SALES');
   if(!connected.length||!products.length){notify('Necesitas un producto y una conexión WhatsApp conectada.');return;}
   const request_id=crypto.randomUUID();
   dialog.innerHTML=`<form><div class="dialog-head"><h2>Registrar venta anterior</h2><button type="button" data-close>✕</button></div>
   <p>Envía los accesos conservando la vigencia original. No registres una venta que ya exista.</p>
   <label>Bot de ventas · remitente<select name="instance_id">${connected.map(i=>`<option value="${i.id}">${h(i.name)} · ${h(i.phone||'')}</option>`).join('')}</select></label>
   <label>Cliente<input name="customer" required minlength="2" maxlength="100"></label>
   <label>WhatsApp con código de país (ejemplo: 51987654321)<input name="phone" inputmode="numeric" pattern="[1-9][0-9]{7,14}" required></label>
   <label>Plataforma<select name="product_id">${products.map(p=>`<option value="${p.id}">${h(p.name)}</option>`).join('')}</select></label>
   <label>Cuenta<select name="stock_id"></select></label>
   <div data-new-account><label>Correo de la cuenta<input name="email" type="email" autocomplete="off"></label><label>Contraseña<input name="password" type="password" maxlength="256" autocomplete="new-password"></label></div>
   <label>Inicio original · hora de Perú<input name="started_at" type="datetime-local" required></label>
   <label>Vencimiento original · hora de Perú<input name="expires_at" type="datetime-local" required></label>
   <label>Importe ya cobrado (S/; 0 para cortesía)<input name="price" type="number" min="0" max="100000" step="0.01" required></label>
   <label>Referencia única del pago original (opcional)<input name="reference" maxlength="100" placeholder="Número de operación, no «pago aprobado»"></label><p class="muted">Si no tienes la referencia, déjala vacía. Un cliente puede tener varias cuentas distintas de la misma plataforma.</p>
   <p>El importe se registrará en la fecha de inicio original. No se realiza ningún cobro nuevo.</p>
   <label class="check"><input name="confirmed" type="checkbox" required> Verifiqué el número del destinatario, los accesos, el pago y las fechas; autorizo enviar este mensaje.</label>
   <p class="danger" role="alert"></p><button class="primary" type="submit">Registrar y enviar por WhatsApp</button></form>`;
   const form=dialog.querySelector('form'),f=form.elements;
   const account=()=>{const fresh=!f.stock_id.value;dialog.querySelector('[data-new-account]').hidden=!fresh;f.email.required=f.password.required=fresh;};
   const options=()=>{f.stock_id.innerHTML='<option value="">Cargar la cuenta vendida</option>'+stock.filter(s=>s.product_id===f.product_id.value).map(s=>`<option value="${s.id}">${h(s.email)} · ${s.id.slice(0,8)}</option>`).join('');account();};
   f.product_id.onchange=options;f.stock_id.onchange=account;options();
   dialog.querySelector('[data-close]').onclick=()=>dialog.close();
   form.onsubmit=async ev=>{ev.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    try{const d=Object.fromEntries(new FormData(form));await api('/orders/external','POST',{request_id,instance_id:d.instance_id,customer:d.customer,phone:d.phone,product_id:d.product_id,stock_id:d.stock_id||null,...(!d.stock_id?{email:d.email,password:d.password}:{}),started_at:new Date(d.started_at+':00-05:00').toISOString(),expires_at:new Date(d.expires_at+':00-05:00').toISOString(),price_cents:Math.round(Number(d.price)*100),reference:d.reference,confirmed:f.confirmed.checked});dialog.close();dialog.innerHTML='';notify('Venta registrada. Envío programado; revisa el estado en Pedidos y pagos.');await render();}
    catch(err){form.querySelector('[role=alert]').textContent=err.message;}finally{button.disabled=false;}};
   dialog.showModal();
  }catch(err){notify(err.message);}
 });
}
