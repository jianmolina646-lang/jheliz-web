"""Tipo de cambio USDT/PEN automatico desde el P2P de Binance.

Usamos el endpoint publico de busqueda de anuncios P2P y promediamos los
primeros 5 anuncios del lado BUY (es decir, gente que vende USDT a cambio
de PEN — el precio que ve un peruano cuando quiere comprar USDT en
Binance). Asi reflejamos el precio real que tiene el cliente cuando paga
con Binance Pay desde Peru.

No requiere autenticacion. Cachea 30 minutos para no abusar de la API.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

BINANCE_P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
CACHE_KEY = "jh_binance_usdt_pen_rate"
CACHE_TTL = 1800  # 30 min


def fetch_binance_usdt_pen_rate(timeout: float = 8.0) -> Optional[Decimal]:
    """Devuelve el promedio P2P de USDT/PEN en Binance, o None si falla."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    try:
        resp = requests.post(
            BINANCE_P2P_URL,
            json={
                "asset": "USDT",
                "fiat": "PEN",
                "tradeType": "BUY",
                "page": 1,
                "rows": 10,
                "transAmount": "",
                "publisherType": None,
                "payTypes": [],
                "countries": [],
            },
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; JhelizStore/1.0)",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        ads = data.get("data") or []
        prices = []
        for ad in ads[:5]:
            price_str = ((ad.get("adv") or {}).get("price")) or ""
            try:
                prices.append(Decimal(str(price_str)))
            except (InvalidOperation, ValueError, TypeError):
                continue
        if not prices:
            logger.warning("Binance P2P respondio sin precios validos")
            return None
        avg = (sum(prices) / Decimal(len(prices))).quantize(Decimal("0.0001"))
        cache.set(CACHE_KEY, avg, CACHE_TTL)
        return avg
    except Exception as exc:
        logger.warning("Fallo al jalar TC de Binance P2P: %s", exc)
        return None
