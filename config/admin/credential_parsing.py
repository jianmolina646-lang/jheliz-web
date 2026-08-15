"""Análisis de credenciales ingresadas desde el panel administrativo."""

def _parse_bulk_replace_line(raw: str) -> tuple[str, str, str] | None:
    """Parsea una línea del modal de reemplazo masivo de credenciales.

    Devuelve ``(email_actual, email_nuevo, contraseña_nueva)`` o ``None`` si
    no se pudo parsear. ``email_nuevo`` puede ser ``""`` si solo cambia la
    contraseña.

    Formatos soportados (auto-detectados):
      A. ``email_actual:contraseña_nueva`` (solo cambia contraseña)
      B. ``email_actual|email_nuevo|contraseña_nueva`` (separador pipe)
      C. ``email_actual,email_nuevo,contraseña_nueva`` (separador coma)
      D. ``email_actual -> email_nuevo:contraseña_nueva``
    """
    line = (raw or "").strip()
    if not line or line.startswith("#"):
        return None

    # Formato D: flecha
    if "->" in line or "→" in line:
        sep = "->" if "->" in line else "→"
        left, _, right = line.partition(sep)
        left = left.strip()
        right = right.strip()
        if "@" in left and ":" in right:
            new_email, _, new_pass = right.partition(":")
            new_email = new_email.strip()
            new_pass = new_pass.strip()
            if "@" in new_email and new_pass:
                return (left.lower(), new_email, new_pass)

    # Formato B/C: 3 campos con | o ,
    for sep in ("|", ","):
        if line.count(sep) >= 2:
            parts = [p.strip() for p in line.split(sep, 2)]
            if (
                len(parts) == 3
                and "@" in parts[0]
                and "@" in parts[1]
                and parts[2]
            ):
                return (parts[0].lower(), parts[1], parts[2])

    # Formato A: email:contraseña (solo cambia password)
    if ":" in line:
        email, _, password = line.partition(":")
        email = email.strip()
        password = password.strip()
        if "@" in email and password:
            return (email.lower(), "", password)

    return None
