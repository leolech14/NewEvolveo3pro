import re

# -------------------------
# Section headers / anchors
# -------------------------
ANCHORS = {
    "domestic": re.compile(r"lançamentos: compras e saques", re.I),
    "international": re.compile(r"lançamentos internacionais", re.I),
    "instalments_next": re.compile(r"compras parceladas – próximas faturas", re.I),
}

# ---------------
# Row patterns
# ---------------
# Domestic (2-line) – we only parse the 1st line here; 2nd line handled later
RE_DOMESTIC_L1 = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<merchant>.+?)\s+(?P<amount_brl>-?[\d.\,]+)$"
)
RE_DOMESTIC_L2 = re.compile(
    r"^(?P<category>[A-ZÇÉÂÊÕ ]+)\.\s+(?P<city>[A-ZÂÁÉÍÓÚÊÔÛ .-]+)$"
)

# International (3-line bundle)
RE_INTL_L1 = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<merchant>.+?)\s+(?P<amount_usd>-?[\d.\,]+)\s+USD$",
    re.I,
)
RE_INTL_L2 = re.compile(
    r"^(?P<city>[A-ZÂÁÉÍÓÚÊÔÛ .-]+)\s+(?P<amount_brl>-?[\d.\,]+)\s+BRL$", re.I
)
RE_INTL_L3 = re.compile(r"^Dólar de Conversão R\$ (?P<fx_rate>[\d.\,]+)", re.I)

# Summary / totals keywords (noise)
SUMMARY_KEYWORDS = {
    "total",
    "saldo",
    "encargos",
    "iof",
    "juros",
    "lançamentos atuais",
}
