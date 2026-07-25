"""Carga segura de configuración desde Docker Secrets o variables de entorno."""

from pathlib import Path

from decouple import config


def secret_config(name: str, default: str = "") -> str:
    """
    Lee ``NAME_FILE`` antes que ``NAME``.

    Docker monta los secretos como archivos en ``/run/secrets``. Mantener el
    fallback a variables de entorno permite desarrollo local y una migración
    gradual sin interrumpir el servicio.
    """

    file_path = config(f"{name}_FILE", default="").strip()
    if not file_path:
        return config(name, default=default)

    try:
        value = Path(file_path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"No se pudo leer el secreto {name} desde {file_path}"
        ) from exc

    if not value:
        raise RuntimeError(f"El archivo secreto {file_path} está vacío")

    return value
