const normalized=value=>String(value||'').normalize('NFD').replace(/\p{Diacritic}/gu,'').trim().toLowerCase();
export function isCodesInstance(instance){
 return instance?.purpose==='CODES'||normalized(instance?.name)===normalized(process.env.CODES_WHATSAPP_INSTANCE_NAME||'codigos jheliz');
}
export async function requireSalesInstance(c,id){
 const instance=(await c.query('SELECT * FROM instances WHERE id=$1',[id])).rows[0];
 if(!instance||isCodesInstance(instance))throw Object.assign(new Error('Sales instance required'),{statusCode:409,publicMessage:'Esta operación solo puede salir por el bot de ventas. Selecciona su conexión de WhatsApp.'});
 return instance;
}
export function duplicateMessage(constraint){
 return ({stock_fingerprint_key:'Ese correo ya está en el inventario de esta plataforma. Selecciona la cuenta existente; si está vendida, revisa su cliente.',orders_payment_ref_key:'Esta referencia de pago ya fue registrada. Usa el número real de la operación; en ventas anteriores puedes dejarla vacía si no la tienes.',orders_stock_id_key:'Esta cuenta ya está asignada a otra venta.',products_code_key:'Este código de producto ya existe. Usa otro código o edita el producto.',one_pending_order:'El cliente ya tiene un pedido pendiente en este bot.',one_open_renewal:'Esta cuenta ya tiene una renovación en proceso.',orders_external_key_key:'Esta venta anterior ya fue registrada.',commands_name_key:'Ya existe un comando con ese nombre.',users_email_key:'Ya existe un usuario con ese correo.'})[constraint]||'Ya existe un registro con ese identificador. Revisa los datos antes de repetir la operación.';
}
