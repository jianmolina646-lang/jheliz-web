from decimal import Decimal, InvalidOperation


CURRENCIES = {
    "PEN": {"name": "Sol peruano", "symbol": "S/", "decimals": 2},
    "CLP": {"name": "Peso chileno", "symbol": "$", "decimals": 0},
    "MXN": {"name": "Peso mexicano", "symbol": "$", "decimals": 2},
    "USD": {"name": "Dólar estadounidense", "symbol": "US$", "decimals": 2},
    "USDT": {"name": "Tether", "symbol": "USDT", "decimals": 2},
    "COP": {"name": "Peso colombiano", "symbol": "$", "decimals": 0},
    "ARS": {"name": "Peso argentino", "symbol": "$", "decimals": 2},
    "BRL": {"name": "Real brasileño", "symbol": "R$", "decimals": 2},
    "BOB": {"name": "Boliviano", "symbol": "Bs.", "decimals": 2},
    "EUR": {"name": "Euro", "symbol": "€", "decimals": 2},
}

CURRENCY_CHOICES = tuple(
    (code, f"{code} · {data['name']} ({data['symbol']})")
    for code, data in CURRENCIES.items()
)

COUNTRIES = {
    "PE": ("Perú", "PEN"),
    "CL": ("Chile", "CLP"),
    "MX": ("México", "MXN"),
    "US": ("Estados Unidos", "USD"),
    "CO": ("Colombia", "COP"),
    "AR": ("Argentina", "ARS"),
    "BR": ("Brasil", "BRL"),
    "BO": ("Bolivia", "BOB"),
    "EC": ("Ecuador", "USD"),
    "OT": ("Otro país", "USD"),
}
try:
    import phonenumbers
    _all_regions = sorted(phonenumbers.SUPPORTED_REGIONS)
    COUNTRY_CHOICES = tuple(
        (
            code,
            (
                COUNTRIES[code][0]
                if code in COUNTRIES
                else f"{code} (+{phonenumbers.country_code_for_region(code)})"
            ),
        )
        for code in _all_regions
    ) + (("OT", "Otro país"),)
except ImportError:  # Permite ejecutar herramientas antes de instalar dependencias.
    COUNTRY_CHOICES = tuple((code, value[0]) for code, value in COUNTRIES.items())

ALIASES = {"S/": "PEN", "SOL": "PEN", "$": "USD"}


def normalize_currency(value, default="PEN"):
    code = (value or "").strip().upper()
    code = ALIASES.get(code, code)
    return code if code in CURRENCIES else default


def currency_symbol(value):
    code = normalize_currency(value)
    return CURRENCIES[code]["symbol"]


def suggested_currency(country):
    return COUNTRIES.get((country or "").upper(), COUNTRIES["OT"])[1]


def decimal_rate(value, default=Decimal("1")):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default
    return result if result > 0 else default
