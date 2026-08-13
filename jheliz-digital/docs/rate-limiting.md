# Rate limiting

Nginx limita solicitudes por dirección IP antes de que alcancen Django.

- `/ingresar/` y `/admin/login/`: 6 solicitudes por minuto, con una ráfaga inicial
  de 4 solicitudes adicionales.
- Aplicación general: 15 solicitudes por segundo, con ráfaga de 30.
- Conexiones simultáneas: máximo 30 por IP.
- `/health/` y archivos estáticos: excluidos del límite de solicitudes.
- Respuesta al superar el límite: HTTP `429 Too Many Requests`.

La configuración activa está versionada en
`deploy/nginx/jheliz-digital-tls.conf`. Antes de reemplazarla se debe respaldar el
sitio actual, ejecutar `nginx -t` y recargar Nginx únicamente si la prueba es válida.

Si el dominio vuelve a utilizar proxy de Cloudflare, debe configurarse primero la
restauración segura de la IP real del visitante; de lo contrario, Nginx verá las IP
de Cloudflare en lugar de la IP del usuario.
