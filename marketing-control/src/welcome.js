export const welcomeText=`👋 *JHELIZ · Bienvenido*

🎬 Tus plataformas favoritas, en un solo lugar.

🛍️ *1. Explora el catálogo*
Escribe /catalogo para ver servicios y precios.

📦 *2. Consulta tus compras*
Escribe /pedidos para revisar su estado.

🛠️ *3. ¿Necesitas ayuda?*
Escribe /soporte para reportar un problema.

🔒 Pago por Ligo · Verificación manual antes de la entrega.

Escribe el comando de la opción que necesitas.
🏠 Para volver al inicio: /menu`;

export function isWelcomeGreeting(text){
 if(typeof text!=='string'||text.length>80)return false;
 const normalized=text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim().replace(/^[¡!¿?.,\s]+|[¡!¿?.,\s]+$/g,'').replace(/\s+/g,' ');
 return ['hola','buenas','inicio','menu','buenos dias','buenas tardes','buenas noches'].includes(normalized);
}
