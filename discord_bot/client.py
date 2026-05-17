"""Cliente HTTP fino para la API de Discord.

Encapsula las llamadas a la API REST de Discord
(https://discord.com/api/v10) que usamos para el back-office:

- ``send_message`` / ``send_embed`` para postear avisos en canales.
- ``create_channel`` para auto-crear la estructura inicial (#pedidos,
  #yape, #codigos, etc.).
- ``edit_message`` para actualizar un mensaje (ej. tachar un pedido cuando
  se marca entregado).

Diseñado para ser **best-effort**: nunca debe romper la petición HTTP del
cliente final si Discord está caído — todos los helpers devuelven ``None``
si no hay token o si la API rechaza la llamada.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://discord.com/api/v10"
TIMEOUT = 15  # segundos


def _token() -> str:
    return getattr(settings, "DISCORD_BOT_TOKEN", "") or ""


def is_configured() -> bool:
    return bool(_token())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bot {_token()}",
        "Content-Type": "application/json",
        "User-Agent": "JhelizWeb (https://ecormecejhelizstore.com, 1.0)",
    }


def _call(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict | list | None:
    """Llama a la API de Discord. Devuelve dict/list o None si falla."""
    if not is_configured():
        return None
    url = f"{API_BASE}{path}"
    try:
        resp = requests.request(
            method, url,
            headers=_headers(), json=json, params=params, timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Discord API %s %s: error de red %s", method, path, exc)
        return None
    if resp.status_code >= 400:
        body = ""
        try:
            body = resp.text[:500]
        except Exception:
            pass
        logger.warning(
            "Discord API %s %s -> %s %s", method, path, resp.status_code, body,
        )
        return None
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return None


# ---------- Identidad del bot ----------

def get_me() -> dict | None:
    """Devuelve los datos del propio bot (username, id, etc.). Útil para
    el comando ``discord_test``."""
    result = _call("GET", "/users/@me")
    return result if isinstance(result, dict) else None


def list_guilds() -> list[dict]:
    """Lista los servidores donde está el bot."""
    result = _call("GET", "/users/@me/guilds")
    return result if isinstance(result, list) else []


# ---------- Canales ----------

def list_channels(guild_id: str | int) -> list[dict]:
    result = _call("GET", f"/guilds/{guild_id}/channels")
    return result if isinstance(result, list) else []


def create_channel(
    guild_id: str | int,
    name: str,
    *,
    channel_type: int = 0,  # 0 = text, 4 = category
    parent_id: str | None = None,
    topic: str = "",
) -> dict | None:
    """Crea un canal de texto o categoría dentro del guild."""
    payload: dict[str, Any] = {"name": name, "type": channel_type}
    if parent_id is not None:
        payload["parent_id"] = str(parent_id)
    if topic:
        payload["topic"] = topic[:1024]
    result = _call("POST", f"/guilds/{guild_id}/channels", json=payload)
    return result if isinstance(result, dict) else None


# ---------- Mensajes ----------

def send_message(
    channel_id: str | int,
    content: str = "",
    *,
    embeds: Iterable[dict] | None = None,
    components: Iterable[dict] | None = None,
) -> dict | None:
    """Envía un mensaje (texto + embeds + botones) a un canal."""
    payload: dict[str, Any] = {}
    if content:
        payload["content"] = content[:2000]
    if embeds:
        payload["embeds"] = list(embeds)[:10]
    if components:
        payload["components"] = list(components)
    if not payload:
        return None
    result = _call("POST", f"/channels/{channel_id}/messages", json=payload)
    return result if isinstance(result, dict) else None


def send_embed(
    channel_id: str | int,
    *,
    title: str,
    description: str = "",
    fields: list[dict] | None = None,
    color: int = 0xE91E63,  # rosa por defecto (marca Jheliz)
    url: str | None = None,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
    footer: str = "",
    components: Iterable[dict] | None = None,
) -> dict | None:
    """Helper para mandar un embed con título, descripción y fields."""
    embed: dict[str, Any] = {
        "title": title[:256],
        "color": color,
    }
    if description:
        embed["description"] = description[:4096]
    if url:
        embed["url"] = url
    if image_url:
        embed["image"] = {"url": image_url}
    if thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}
    if fields:
        embed["fields"] = [
            {
                "name": str(f.get("name", ""))[:256],
                "value": str(f.get("value", ""))[:1024],
                "inline": bool(f.get("inline", False)),
            }
            for f in fields[:25]
        ]
    if footer:
        embed["footer"] = {"text": footer[:2048]}
    return send_message(channel_id, embeds=[embed], components=components)


def start_thread_from_message(
    channel_id: str | int,
    message_id: str | int,
    name: str,
    *,
    auto_archive_minutes: int = 10080,  # 7 días
) -> dict | None:
    """Convierte un mensaje en el primer mensaje de un thread.

    Devuelve el thread, cuyo ``id`` se usa como channel_id para posts
    posteriores dentro del thread.
    """
    payload = {
        "name": name[:100],
        "auto_archive_duration": auto_archive_minutes,
    }
    result = _call(
        "POST",
        f"/channels/{channel_id}/messages/{message_id}/threads",
        json=payload,
    )
    return result if isinstance(result, dict) else None


def archive_thread(thread_id: str | int) -> dict | None:
    """Marca el thread como archivado (se colapsa en la UI)."""
    result = _call(
        "PATCH",
        f"/channels/{thread_id}",
        json={"archived": True, "locked": False},
    )
    return result if isinstance(result, dict) else None


def edit_message(
    channel_id: str | int,
    message_id: str | int,
    *,
    content: str | None = None,
    embeds: Iterable[dict] | None = None,
    components: Iterable[dict] | None = None,
) -> dict | None:
    payload: dict[str, Any] = {}
    if content is not None:
        payload["content"] = content[:2000]
    if embeds is not None:
        payload["embeds"] = list(embeds)[:10]
    if components is not None:
        payload["components"] = list(components)
    result = _call(
        "PATCH", f"/channels/{channel_id}/messages/{message_id}", json=payload,
    )
    return result if isinstance(result, dict) else None


# ---------- Helpers UI: botones link ----------

def link_button(label: str, url: str, emoji: str | None = None) -> dict:
    """Devuelve un button-link listo para meter dentro de ``components``."""
    btn: dict[str, Any] = {
        "type": 2,
        "style": 5,  # link
        "label": label[:80],
        "url": url,
    }
    if emoji:
        btn["emoji"] = {"name": emoji}
    return btn


def action_row(*buttons: dict) -> dict:
    """Agrupa hasta 5 botones en una fila para enviar como ``components``."""
    return {"type": 1, "components": list(buttons)[:5]}
