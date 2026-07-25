"""Custom emojis configurables para el bot de códigos de Telegram."""

from __future__ import annotations

from html import escape
import re

from django.conf import settings


EMOJI_SETTINGS = {
    "🔑": "CODES_PREMIUM_EMOJI_KEY_ID",
    "✈️": "CODES_PREMIUM_EMOJI_TRAVEL_ID",
    "🏠": "CODES_PREMIUM_EMOJI_HOME_ID",
    "🔒": "CODES_PREMIUM_EMOJI_LOCK_ID",
    "📺": "CODES_PREMIUM_EMOJI_TV_ID",
    "📧": "CODES_PREMIUM_EMOJI_MAIL_ID",
    "📋": "CODES_PREMIUM_EMOJI_MAIL_ID",
    "✅": "CODES_PREMIUM_EMOJI_SUCCESS_ID",
    "⚠️": "CODES_PREMIUM_EMOJI_WARNING_ID",
    "✨": "CODES_PREMIUM_EMOJI_SPARKLES_ID",
    "❓": "CODES_PREMIUM_EMOJI_HELP_ID",
    "👥": "CODES_PREMIUM_EMOJI_CLIENTS_ID",
    "🔓": "CODES_PREMIUM_EMOJI_ACTIVATE_ID",
    "⏸": "CODES_PREMIUM_EMOJI_DEACTIVATE_ID",
    "➕": "CODES_PREMIUM_EMOJI_ASSIGN_ID",
    "➖": "CODES_PREMIUM_EMOJI_REMOVE_ID",
    "📢": "CODES_PREMIUM_EMOJI_ANNOUNCEMENT_ID",
}

# Set Premium elegido para TEAM JHELIZ. Las variables del entorno permiten
# sustituir cualquiera de estos IDs sin modificar el código.
DEFAULT_EMOJI_IDS = {
    "🔑": "5231250323779116601",
    "✈️": "5206558088642981395",
    "🏠": "6019562296462806837",
    "🔒": "5422546307422118237",
    "📺": "5418026554422750284",
    "📧": "5008025248314950702",
    "📋": "5008025248314950702",
    "❓": "6102840561281014143",
    "👥": "5343902827712367295",
    "🔓": "6105118564690172709",
    "⏸": "5244807637157029775",
    "➕": "6102432045466656180",
    "➖": "5357300578760285016",
    "📢": "5312210989884655886",
}

_CUSTOM_EMOJI_RE = re.compile(
    r'<tg-emoji emoji-id="[^"]+">(?P<fallback>.*?)</tg-emoji>'
)


def emoji_id(fallback: str) -> str:
    """Devuelve el ID configurado o el ID predeterminado de TEAM JHELIZ."""
    setting_name = EMOJI_SETTINGS.get(fallback, "")
    configured_id = (
        str(getattr(settings, setting_name, "") or "").strip()
        if setting_name
        else ""
    )
    return configured_id or DEFAULT_EMOJI_IDS.get(fallback, "")


def render(text: str) -> str:
    """Reemplaza emojis Unicode por custom emojis HTML cuando tienen un ID."""
    for fallback in EMOJI_SETTINGS:
        custom_id = emoji_id(fallback)
        if custom_id:
            tag = (
                f'<tg-emoji emoji-id="{escape(custom_id, quote=True)}">'
                f"{fallback}</tg-emoji>"
            )
            text = text.replace(fallback, tag)
    return text


def without_custom_emoji(text: str) -> str:
    """Elimina las etiquetas conservando sus emojis Unicode de respaldo."""
    return _CUSTOM_EMOJI_RE.sub(r"\g<fallback>", text)


def custom_emoji_ids(message: dict) -> list[str]:
    """Extrae IDs Premium de un mensaje o del mensaje al que responde."""
    source = message.get("reply_to_message") or message
    entities = list(source.get("entities") or []) + list(
        source.get("caption_entities") or []
    )
    ids: list[str] = []
    for entity in entities:
        custom_id = str(entity.get("custom_emoji_id") or "")
        if custom_id and custom_id not in ids:
            ids.append(custom_id)
    return ids
