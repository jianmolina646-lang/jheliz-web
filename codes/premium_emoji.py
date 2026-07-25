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
    "✅": "CODES_PREMIUM_EMOJI_SUCCESS_ID",
    "⚠️": "CODES_PREMIUM_EMOJI_WARNING_ID",
    "✨": "CODES_PREMIUM_EMOJI_SPARKLES_ID",
    "❓": "CODES_PREMIUM_EMOJI_HELP_ID",
}

_CUSTOM_EMOJI_RE = re.compile(
    r'<tg-emoji emoji-id="[^"]+">(?P<fallback>.*?)</tg-emoji>'
)


def render(text: str) -> str:
    """Reemplaza emojis Unicode por custom emojis HTML cuando tienen un ID."""
    for fallback, setting_name in EMOJI_SETTINGS.items():
        custom_id = str(getattr(settings, setting_name, "") or "").strip()
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
