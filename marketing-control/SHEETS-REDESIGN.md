# Jheliz Ventas — rediseño empresarial, 13/10/2026

## Inspección previa real

Google Sheets `Jheliz ventas`: 14 pestañas; configuración es_MX, Etc/GMT.
No se encontraron fórmulas, validaciones de celdas, rangos con nombre,
protecciones ni vistas de filtro en la inspección API completa.
Dos gráficos, filtros básicos y nueve reglas de estado por tabla con estados.
El archivo no contiene una pestaña `Ventas list`: se conserva `Ventas Bot`.
No se cambia la configuración regional ni los nombres o IDs de las pestañas.
No se inspeccionaron proyectos Apps Script externos ni sus triggers; no se crean ni modifican.

## Relaciones y fuente de verdad

PostgreSQL → worker (aprox. cada minuto) → proyecciones Google Sheets.
Catálogo.ID producto = stock.product_id = orders.product_id.
Inventario.Referencia cuenta = Ventas Bot.Referencia cuenta.
Ventas Bot.Pedido = Pagos.Pedido = Vencimientos.Pedido = Soporte.Pedido.
Disponibles y Vendidas son vistas de Inventario por estado, no stock adicional.
Clientes se agrupa por conexión + identificador WhatsApp, no solo nombre.
Historial soporte conserva reemplazos y vencimientos de la compra original.
Resumen agrega datos del mismo snapshot de base de datos.
Panel ejecutivo usa fórmulas nativas sobre Pagos, Inventario, Clientes,
Ventas Bot y el reloj de actualización Resumen!B2 (hora Lima).
Hoja 1 permanece intacta. No se exportan contraseñas.

## Diagnóstico / diseño

Antes: predominio verde, indicadores sin período, ausencia de controles de
duplicados/incompletos, reinicio de filtros y recreación de gráficos al reiniciar.
Ahora: encabezados azul marino, azul discreto, fondos claros, verde completado,
ámbar advertencias y rojo incidencias; filas alternas, encabezado congelado,
columnas de correo anchas, fechas claras y moneda S/.
Se mantienen las columnas actuales y el flujo de aprobación/entrega.

KPIs: cobros aprobados históricos, ingresos del mes calendario Lima,
cuentas disponibles, vendidas/asignadas, clientes con pedidos, operaciones
en todos los estados, vencimientos en siete días y ventas entregadas.
No hay costos fiables: no se presenta utilidad neta.
Ingresos son aprobaciones registradas, no un extracto bancario ni beneficio.
Gráficos existentes conservan sus IDs: inventario y cobros diarios (14 días).

Alertas de formato condicional (no bloquean ni cambian registros):
ID duplicado o ausente, correo ausente, mismo correo/plataforma duplicado,
vencimiento próximo/vencido, fechas faltantes en ventas entregadas.
Los duplicados de correo entre plataformas distintas no se consideran error.
Filtros conservan criterios y orden. Reglas ajenas no se eliminan.

## Respaldo previo

Servidor: /opt/backups/marketing-control/sheets-redesign-20261013/
- workbook.json: respuesta completa Sheets API con datos y formatos (privada, 0600).
- source.tgz: código previo.
Respaldo sistema: /opt/backups/marketing-control/20261013T220515Z.
SHA256 workbook: cbbcff500dc79bb3ea6ea61c0b75c57c59c3a9918bf9833eb48f88892d2cd1a6.
No es una copia Drive compartida: es un snapshot recuperable en el servidor.
Restaurar requiere detener sincronización de reportes y reponer los campos
editables del snapshot por API; no enviar campos de respuesta de solo lectura.

## Operación

Las hojas administradas son reportes, no formularios de carga. Editar cuentas,
precios y pagos en el panel web. Para cálculos manuales usar otra pestaña.
No se agrega Apps Script: duplicaría el sincronizador existente.
Las fórmulas del dashboard se escriben como fórmulas, nunca como valores fijos.
El contenido de clientes sigue escribiéndose RAW para prevenir inyección.

## Pruebas

Ejecutar: node --test tests/reports.test.js tests/sheet-design.test.js.
Verificación remota posterior: errores de fórmula, resultados KPI contra DB,
IDs de pestañas/gráficos, encabezados, filtros, datos operativos contra respaldo,
sincronización sucesiva y conexión del bot. No implica prueba visual en navegador.

### Resultados ejecutados

- `npm test` en la imagen Node 22 de producción: 15 aprobadas, 0 fallidas,
  3 pruebas de integración omitidas (no se activaron sus flags).
- Comparación API real con respaldo: 12 pestañas operativas idénticas en
  contenido, incluidos correos, fechas e identificadores. Resumen cambia su
  reloj; Panel ejecutivo cambia intencionalmente sus indicadores y fórmulas.
- Se conservaron los 14 nombres/IDs de pestaña y los 2 IDs de gráfico.
- 39 fórmulas nativas sin errores; 10 filtros y 79 reglas de diagnóstico.
- KPI contrastados contra SQL: S/35 acumulado y mes en curso, 2 clientes con
  pedidos, 2 operaciones, 1 cuenta asignada/entregada, 0 disponibles/próximas
  a vencer. Son resultados al verificar, no valores fijos del código.
- Se detectó y corrigió COUNTA contando textos vacíos del exportador:
  se usan identificadores de texto no vacíos (`COUNTIF` con `?*`).
- Última sincronización comprobada: 13/10/2026 17:11:54 Lima, sin error.
  Instancia `jheliz` conectada. No se envió una compra o mensaje real de prueba.
- No hubo validaciones de entrada preexistentes que probar. No se añaden
  formularios ni listas editables a proyecciones de solo reporte.

Archivos: src/sheet-design.js (identidad, KPI y gráficos),
src/sheet-quality.js (alertas, filtros y protección de fórmulas),
src/reports.js (integración), tests/sheet-design.test.js,
scripts/inspect-workbook.mjs, scripts/backup-workbook.mjs,
scripts/verify-workbook.mjs y este documento.

Referencia técnica consultada: documentación oficial de solicitudes Sheets API,
https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request

## Actualización v3 — franjas de marca en todas las pestañas

Se aplicó la referencia visual del usuario: título e icono de sección en franja
blanca, subtítulo azul claro, encabezados azul marino, filas alternas azul pálido.
El panel ejecutivo comparte ahora la misma identidad.
La inspección previa a esta actualización encontró 13 pestañas (Hoja 1 ya no
estaba presente); no se borró ni renombró ninguna.

Migración atómica por Sheets API: una fila nueva al inicio de cada una de las
12 tablas, marcada con metadata `brand-header-v3` para no repetirla. Encabezados
en fila 2, datos desde fila 3, dos filas congeladas. Se desactiva la congelación
de la primera columna para permitir combinar las celdas del título.
Las fórmulas del panel y reglas INDIRECT usan ahora Resumen!B3 y datos desde
fila 3. El exportador empieza en A2 y no toca las franjas.

Respaldo: /opt/backups/marketing-control/banner-v3-20261013/ (workbook.json,
source.tgz), más respaldo completo 20261013T222056Z.
SHA256 hoja: 6124a844936c725fd31c5b6538a6559139be578e7b5036e2a2edf4174291e160.

Pruebas ejecutadas: 20 aprobadas, 3 de integración omitidas. Verificador real
con BANNER_VERIFY=1: datos operativos preservados tras normalizar el cambio de
fila; 39 fórmulas sin errores, 10 filtros, 79 reglas, nombres/IDs y gráficos
conservados, KPIs coinciden con SQL. Sincronización inicial v3 22:23:40 UTC,
bot jheliz CONNECTED. Validación por API; no captura visual de navegador.
Archivos adicionales: src/sheet-banner.js, tests/sheet-banner.test.js; ajustes
en reports.js, sheet-quality.js, sheet-design.js y verify-workbook.mjs.
