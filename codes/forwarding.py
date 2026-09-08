"""Identifica reenvíos automáticos Outlook sin autorizar menciones del cuerpo.

El receptor IMAP debe garantizar que los Authentication-Results con el
authserv-id configurado fueron añadidos por él, eliminando copias externas.
La autenticación de dominio se combina con el remitente exacto de Outlook,
las marcas de su regla automática y el destinatario del bloque original.
"""

from __future__ import annotations

import re
from email.message import Message
from email.utils import getaddresses
from html.parser import HTMLParser


_OUTLOOK_DOMAIN = "outlook.com"
_ORIGINAL_DOMAIN = "account.netflix.com"
_METHOD_RE = re.compile(r"([a-z][a-z0-9_-]*)(?:/1)?\s*=\s*([a-z][a-z0-9_-]*)", re.I)
_PROPERTY_RE = re.compile(
    r'([a-z][a-z0-9_.-]*)\s*=\s*("(?:\\.|[^"\\])*"|[^\s"]+)', re.I
)
_BLOCK_TAGS = frozenset({"br", "div", "p", "tr", "li", "hr"})


def _one_address(values: list[str]) -> str:
    if len(values) != 1:
        return ""
    addresses = getaddresses(values)
    if len(addresses) != 1:
        return ""
    address = addresses[0][1].strip().lower()
    return address if address.count("@") == 1 and not re.search(r"\s", address) else ""


def _auth_fields(value: str) -> list[str] | None:
    """Separa campos sin convertir comentarios o cadenas en resultados."""
    fields: list[str] = []
    current: list[str] = []
    comments = 0
    quoted = escaped = False
    for char in value:
        if escaped:
            if not comments:
                current.append(char)
            escaped = False
        elif char == "\\" and (comments or quoted):
            if quoted and not comments:
                current.append(char)
            escaped = True
        elif comments:
            if char == "(":
                comments += 1
            elif char == ")":
                comments -= 1
        elif char == '"':
            quoted = not quoted
            current.append(char)
        elif not quoted and char == "(":
            comments = 1
            current.append(" ")
        elif not quoted and char == ")":
            return None
        elif not quoted and char == ";":
            fields.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if comments or quoted or escaped:
        return None
    fields.append("".join(current).strip())
    return fields


def _auth_result(field: str) -> tuple[str, str, dict[str, str]] | None:
    match = _METHOD_RE.match(field)
    if not match:
        return None
    method, result = (value.lower() for value in match.groups())
    properties: dict[str, str] = {}
    remainder = field[match.end():]
    while remainder:
        # Los atributos necesitan separación; no aceptar passheader.from=...
        if not remainder[0].isspace():
            return None
        remainder = remainder.lstrip()
        if not remainder:
            break
        prop = _PROPERTY_RE.match(remainder)
        if not prop:
            return None
        name, value = prop.groups()
        name = name.lower()
        if name in properties:
            return None
        if value.startswith('"'):
            value = re.sub(r"\\(.)", r"\1", value[1:-1])
        properties[name] = value.lower()
        remainder = remainder[prop.end():]
    return method, result, properties


def _authenticated_outlook(msg: Message, trusted_authserv_id: str) -> bool:
    trusted = (trusted_authserv_id or "").strip().lower()
    if not trusted or not re.fullmatch(r"[a-z0-9.-]+", trusted):
        return False
    seen: set[str] = set()
    for header in msg.get_all("Authentication-Results", []):
        fields = _auth_fields(str(header))
        if fields is None:
            # Una cabecera malformada nunca debe permitir elegir otro pass.
            return False
        identity = re.fullmatch(r"([a-z0-9.-]+)(?:\s+1)?", fields[0], re.I)
        if not identity or identity.group(1).lower() != trusted:
            continue
        if len(fields) < 2:
            return False
        for field in fields[1:]:
            parsed = _auth_result(field)
            if parsed is None:
                return False
            method, result, properties = parsed
            if method not in {"dkim", "dmarc"}:
                continue
            domain_property = "header.d" if method == "dkim" else "header.from"
            # El primer resultado debe ser pass alineado. Ninguno posterior
            # puede ocultar un fallo ni introducir una identidad conflictiva.
            if result != "pass" or properties.get(domain_property) != _OUTLOOK_DOMAIN:
                return False
            seen.add(method)
    return seen == {"dkim", "dmarc"}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.ignored: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "script", "style"}:
            self.ignored.append(tag)
        if not self.ignored and tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
        elif tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self.ignored:
            self.chunks.append(data)


def _body_texts(msg: Message) -> list[str] | None:
    """Solo cuerpos exteriores; no tomar encabezados de mensajes adjuntos."""
    if msg.get_content_maintype() == "message":
        # El lector histórico recorre msg.walk(): podría interpretar un
        # cuerpo interno después de validar el destinatario exterior.
        return None
    attached = bool(msg.get_filename() or msg.get_content_disposition() == "attachment")
    if attached:
        if msg.is_multipart() or (
            not msg.get_filename() and msg.get_content_type() in {"text/html", "text/plain"}
        ):
            return None
        return []
    if msg.is_multipart():
        bodies: list[str] = []
        for part in msg.get_payload():
            texts = _body_texts(part)
            if texts is None:
                return None
            bodies.extend(texts)
        return bodies
    if msg.get_content_type() not in {"text/html", "text/plain"}:
        return []
    try:
        raw = msg.get_payload(decode=True)
        value = raw.decode(msg.get_content_charset() or "utf-8") if raw else ""
        if not value.strip():
            return []
        if msg.get_content_type() == "text/html":
            parser = _VisibleText()
            parser.feed(value)
            parser.close()
            value = "".join(parser.chunks)
    except (LookupError, UnicodeError, ValueError):
        return None
    return [value]


def _original_recipient_matches(text: str, target: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    values: list[str] = []
    for line, label in zip(lines[:4], ("de", "enviados", "para", "asunto")):
        match = re.fullmatch(rf"{label}\s*:\s*(.+)", line, flags=re.I)
        if not match:
            return False
        values.append(match.group(1).strip())
    sender = _one_address([values[0]])
    if not sender or sender.rpartition("@")[2] != _ORIGINAL_DOMAIN:
        return False
    # Outlook muestra a veces la dirección como nombre sin entrecomillarla:
    # ``ana@outlook.com <ana@outlook.com>`` no es una cabecera RFC válida.
    # Solo aceptamos esta forma visible cuando ambas direcciones son iguales
    # a la solicitada, sin flexibilizar el parser de los encabezados reales.
    repeated = re.fullmatch(r'([^\s<>"@]+@[^\s<>"]+)\s*<([^\s<>"]+)>', values[2])
    if repeated:
        return all(address.lower() == target for address in repeated.groups())
    return _one_address([values[2]]) == target


def matches_outlook_forward(
    msg: Message, account_email: str, *, trusted_authserv_id: str
) -> bool:
    """Autoriza únicamente una regla Outlook autenticada de la misma cuenta."""
    target = (account_email or "").strip().lower()
    if not target or target.rpartition("@")[2] != _OUTLOOK_DOMAIN:
        return False
    if _one_address(msg.get_all("From", [])) != target:
        return False
    if _one_address(msg.get_all("X-Ms-Exchange-Inbox-Rules-Loop", [])) != target:
        return False
    submitted = msg.get_all("Auto-Submitted", [])
    if len(submitted) != 1 or str(submitted[0]).strip().lower() != "auto-generated":
        return False
    if not _authenticated_outlook(msg, trusted_authserv_id):
        return False
    bodies = _body_texts(msg)
    return bool(bodies) and all(_original_recipient_matches(body, target) for body in bodies)
