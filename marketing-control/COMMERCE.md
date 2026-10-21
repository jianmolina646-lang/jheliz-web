# Ventas con aprobación manual

El administrador crea productos en **Catálogo y precios**, carga cuentas en **Inventario** y aprueba pagos en **Pedidos y pagos**. Desactivar un producto lo oculta sin borrar el historial. Solo se deben cargar cuentas cuya venta esté autorizada.

Bot: `/catalogo`, `/comprar codigo`, `/pedidos`, `/cancelar`. Un pedido pendiente por cliente e instancia. Una imagen JPG/PNG de hasta 5 MB enviada al chat se asocia al pedido pendiente; no valida un pago. El administrador debe comprobar el ingreso real en Lemon Cash e ingresar una referencia de operación única. El QR configurado es el proporcionado por el propietario; beneficiario declarado: Jhedy Javier Villa Lima.

Precios y días se copian al pedido, por lo que editar el producto no cambia compras existentes. Al aprobar se asigna stock en una transacción con bloqueo de filas; referencias de pago y cuentas asignadas son únicas. El stock se asigna al aprobar, no al mostrar el QR: un pedido pendiente no garantiza disponibilidad. Si no hay stock, se bloquea la aprobación y el administrador debe reponer o coordinar devolución.

La duración comienza al iniciar el envío por WhatsApp. Una fecha fija de inventario se interpreta como válida hasta fin del día, hora Lima. Un envío ambiguo se marca `REVIEW`, sin reenvío automático: revisar el chat antes de intervenir. Un resultado de envío aceptado no prueba que el cliente haya leído el mensaje.

Credenciales y comprobantes: AES-256-GCM, clave en `/opt/jheliz-marketing-secrets/commerce-key`, fuera del código y montada de solo lectura. La clave se incluye en los nuevos respaldos privados junto con la base de datos: no perderla. El listado de inventario nunca expone los accesos.

Google Sheets utiliza `/opt/jheliz-marketing-secrets/sheets.json`. Se generan diez pestañas: Resumen, Catálogo, Inventario, Disponibles, Vendidas, Clientes, Ventas Bot, Pagos, Vencimientos y Guía. Cada minuto se proyecta una lectura consistente de la base y se reemplazan únicamente las pestañas administradas, sin insertar duplicados. No modificar/reordenar/borrar estas filas; usar vistas de filtro o pestañas propias. Las pestañas ajenas se conservan. `RAW` evita interpretar los datos del cliente como fórmulas. Fechas numéricas con formato local Lima, importes en soles, encabezados congelados, filtros y estados con colores. No exporta contraseñas ni comprobantes. El panel muestra la última sincronización y los pedidos pendientes. La base de datos es la fuente principal.

Pruebas de comercio: solo con `RUN_COMMERCE_TEST=1` y base terminada en `/marketing_commerce_test`; no ejecutar contra producción. Las pruebas cubren cifrado, congelación de precio, duplicados y aprobaciones concurrentes. No requieren ni envían pagos reales.
