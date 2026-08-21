import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta

import httpx

from config import settings

log = logging.getLogger("travelpayouts")

# Shahar nomlaridan IATA kodlariga moslashtirish
IATA = {
    # O'zbekiston
    "tashkent": "TAS", "toshkent": "TAS", "tas": "TAS",
    "samarkand": "SKD", "samarqand": "SKD", "skd": "SKD",
    "bukhara": "BHK", "buxoro": "BHK", "bhk": "BHK",
    "fergana": "FEG", "fargona": "FEG", "farg'ona": "FEG", "fargʻona": "FEG", "fargʼona": "FEG", "feg": "FEG",
    "namangan": "NMA", "nma": "NMA",
    "andijan": "AZN", "andijon": "AZN", "azn": "AZN",
    "nukus": "NCU", "ncu": "NCU",
    "urgench": "UGC", "urganch": "UGC", "ugc": "UGC",
    "navoi": "NVI", "navoiy": "NVI", "nvi": "NVI",
    "termez": "TMJ", "termiz": "TMJ", "tmj": "TMJ",
    "qarshi": "KSQ", "karshi": "KSQ", "ksq": "KSQ",

    # Saudiya Arabistoni
    "jeddah": "JED", "jidda": "JED", "jed": "JED",
    "madinah": "MED", "madina": "MED", "medina": "MED", "med": "MED",
    "riyadh": "RUH", "riyod": "RUH", "ar-riyod": "RUH", "ar-riyadh": "RUH", "ruh": "RUH",
    "dammam": "DMM", "dmm": "DMM",
    "taif": "TIF", "toif": "TIF", "tif": "TIF",

    # Boshqa mashhur tranzit yo'nalishlar
    "dubai": "DXB", "dubay": "DXB", "dxb": "DXB",
    "sharjah": "SHJ", "sharja": "SHJ", "shj": "SHJ",
    "abu dhabi": "AUH", "abu-dhabi": "AUH", "abu dabi": "AUH", "auh": "AUH",
    "istanbul": "IST", "ist": "IST", "saw": "SAW",
    "kuwait": "KWI", "quvayt": "KWI", "kwi": "KWI",
    "doha": "DOH", "doh": "DOH",
}

PRICES_FOR_DATES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
LATEST_PRICES_URL = "https://api.travelpayouts.com/v2/prices/latest"

# ==================== O'ZBEKISTONNING 11 TA XALQARO AEROPORTI ====================
# Kunlik avto-post shu ro'yxat bo'yicha aralash reyslar chiqaradi.
UZ_AIRPORTS: list[str] = [
    "TAS",  # Toshkent
    "NMA",  # Namangan
    "SKD",  # Samarqand
    "FEG",  # Farg'ona
    "BHK",  # Buxoro
    "AZN",  # Andijon
    "UGC",  # Urganch
    "TMJ",  # Termiz
    "NVI",  # Navoiy
    "KSQ",  # Qarshi
    "NCU",  # Nukus
]

# Saudiya yo'nalishlari (Jidda va Madina)
SAUDI_DESTINATIONS: list[str] = ["JED", "MED"]

# IATA kodlarining o'zbekcha nomlari (post va Mini App uchun)
CITY_NAMES_UZ: dict[str, str] = {
    "TAS": "Toshkent",
    "NMA": "Namangan",
    "SKD": "Samarqand",
    "FEG": "Farg'ona",
    "BHK": "Buxoro",
    "AZN": "Andijon",
    "UGC": "Urganch",
    "TMJ": "Termiz",
    "NVI": "Navoiy",
    "KSQ": "Qarshi",
    "NCU": "Nukus",
    "JED": "Jidda",
    "MED": "Madina",
    "RUH": "Ar-Riyod",
    "DMM": "Dammam",
    "DXB": "Dubay",
    "IST": "Istanbul",
}

# Har bir aeroport uchun taxminiy (bazaviy) narx — API javob bermaganda ishlatiladi
_BASE_PRICES: dict[str, int] = {
    "TAS": 349,
    "NMA": 369,
    "SKD": 359,
    "FEG": 375,
    "BHK": 379,
    "AZN": 385,
    "UGC": 395,
    "TMJ": 389,
    "NVI": 372,
    "KSQ": 392,
    "NCU": 399,
}


def city_name(code: str) -> str:
    """IATA kodini o'zbekcha shahar nomiga aylantiradi."""
    if not code:
        return ""
    code = code.strip().upper()
    return CITY_NAMES_UZ.get(code, code)



def to_iata(city: str) -> str:
    if not city:
        return ""
    clean = city.strip().lower()
    return IATA.get(clean, city.strip().upper())


def _apply_markup(price):
    """API'dan kelgan narxga foyda ustamasini (MARKUP_PERCENT) qo'shadi."""
    if price is None:
        return None
    try:
        marked_up = float(price) * (1 + settings.MARKUP_PERCENT / 100)
        return round(marked_up, 2)
    except (TypeError, ValueError):
        return price


def _build_affiliate_link(raw_link: str) -> str:
    """Aviasales havolasiga marker qo'shadi, shunda buyurtmadan komissiya sizga hisoblanadi."""
    if not raw_link:
        return ""
    base = f"https://www.aviasales.com{raw_link}" if not raw_link.startswith("http") else raw_link
    marker = settings.TRAVELPAYOUTS_MARKER or ""
    if not marker:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}marker={marker}"


async def search_flights(origin_city: str, destination_city: str, depart_date: str, limit: int = 15) -> list[dict]:
    """Belgilangan sana uchun mavjud chiptalarni qidiradi (narx bo'yicha saralangan)."""
    origin = to_iata(origin_city)
    destination = to_iata(destination_city)
    if not origin or not destination:
        return []

    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": depart_date.strip(),
        "sorting": "price",
        "direct": "false",
        "currency": "usd",
        "limit": limit,
        "one_way": "true",
        "token": settings.TRAVELPAYOUTS_TOKEN,
        "marker": settings.TRAVELPAYOUTS_MARKER,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(PRICES_FOR_DATES_URL, params=params)
        if r.status_code != 200:
            return []
        payload = r.json()

    results = []
    for item in payload.get("data", []):
        original_price = item.get("price")
        marked_up_price = _apply_markup(original_price)
        results.append({
            "origin": item.get("origin") or origin,
            "destination": item.get("destination") or destination,
            "price": marked_up_price,
            "airline": item.get("airline") or "Aviakompaniya",
            "flight_number": item.get("flight_number") or "",
            "departure_at": item.get("departure_at"),
            "return_at": item.get("return_at"),
            "transfers": item.get("transfers", 0),
            "link": _build_affiliate_link(item.get("link", "")),
        })
    return results


async def _fetch_latest_for_route(client: httpx.AsyncClient, origin: str, destination: str) -> list[dict]:
    """Bitta yo'nalish (origin -> destination) bo'yicha eng so'nggi narxlarni oladi."""
    params = {
        "origin": origin,
        "destination": destination,
        "currency": "usd",
        "token": settings.TRAVELPAYOUTS_TOKEN,
        "marker": settings.TRAVELPAYOUTS_MARKER,
    }
    offers: list[dict] = []
    try:
        r = await client.get(LATEST_PRICES_URL, params=params)
        if r.status_code != 200:
            return offers
        data = r.json().get("data", [])
        if not isinstance(data, list):
            return offers
        for item in data:
            val = item.get("value")
            if val is None:
                continue
            offers.append({
                "origin": origin,
                "destination": destination,
                "origin_name": city_name(origin),
                "destination_name": city_name(destination),
                "value": _apply_markup(val),
                "depart_date": item.get("depart_date"),
                "source": "api",
            })
    except Exception as e:
        log.warning(f"{origin}->{destination} narxlarini olishda xatolik: {e}")
    return offers


async def get_daily_cheapest(
    origin_city: str | None = None,
    origins: list[str] | None = None,
    destinations: list[str] | None = None,
) -> list[dict]:
    """Kunlik avto-post uchun narxlarni oladi.

    Sukut bo'yicha O'zbekistonning barcha 11 ta xalqaro aeroportidan
    Jidda (JED) va Madinaga (MED) narxlarni parallel ravishda yig'adi.
    """
    if origins:
        origin_codes = [to_iata(o) for o in origins if o]
    elif origin_city:
        origin_codes = [to_iata(origin_city)]
    else:
        origin_codes = list(UZ_AIRPORTS)

    dest_codes = [to_iata(d) for d in (destinations or SAUDI_DESTINATIONS) if d]

    results: list[dict] = []
    async with httpx.AsyncClient(timeout=20) as client:
        tasks = [
            _fetch_latest_for_route(client, origin, dest)
            for origin in origin_codes
            for dest in dest_codes
        ]
        for chunk in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(chunk, list):
                results.extend(chunk)
    return results


def _pseudo_price(origin: str, destination: str, day: str) -> int:
    """API javob bermaganda ishlatiladigan barqaror (deterministik) taxminiy narx."""
    base = _BASE_PRICES.get((origin or "").upper(), 380)
    if (destination or "").upper() == "MED":
        base += 18
    seed = hashlib.md5(f"{origin}{destination}{day}".encode()).hexdigest()
    delta = int(seed[:4], 16) % 71 - 35  # -35 ... +35
    return max(199, base + delta)


def build_fallback_offers(
    origins: list[str] | None = None,
    destinations: list[str] | None = None,
    days_ahead: int = 9,
) -> list[dict]:
    """Barcha 11 ta aeroportdan Jidda/Madinaga zaxira (taxminiy) narxlar ro'yxati."""
    origin_codes = origins or UZ_AIRPORTS
    dest_codes = destinations or SAUDI_DESTINATIONS
    today = date.today()
    offers: list[dict] = []
    for idx, origin in enumerate(origin_codes):
        for j, dest in enumerate(dest_codes):
            day = (today + timedelta(days=((idx * 2 + j) % max(days_ahead, 1)) + 3)).isoformat()
            offers.append({
                "origin": origin,
                "destination": dest,
                "origin_name": city_name(origin),
                "destination_name": city_name(dest),
                "value": _pseudo_price(origin, dest, day),
                "depart_date": day,
                "source": "fallback",
            })
    return offers


def pick_mixed_offers(
    offers: list[dict],
    limit: int = 11,
    origins_order: list[str] | None = None,
) -> list[dict]:
    """Turfa xil aralash reyslar tanlaydi: bitta shahar (origin) ikki marta takrorlanmaydi.

    Har bir shahar uchun eng arzon variant olinadi, Jidda va Madina yo'nalishlari
    esa navbatma-navbat aralashtiriladi.
    """
    if not offers:
        return []

    # 1) Shahar + yo'nalish bo'yicha eng arzonini yig'ib olamiz
    per_origin: dict[str, dict[str, dict]] = {}
    for offer in offers:
        origin = str(offer.get("origin") or "").upper()
        dest = str(offer.get("destination") or "").upper()
        if not origin:
            continue
        try:
            value = float(offer.get("value"))
        except (TypeError, ValueError):
            continue
        bucket = per_origin.setdefault(origin, {})
        current = bucket.get(dest)
        if current is None or value < float(current.get("value") or 10 ** 9):
            enriched = dict(offer)
            enriched["origin"] = origin
            enriched["destination"] = dest
            enriched["value"] = value
            enriched.setdefault("origin_name", city_name(origin))
            enriched.setdefault("destination_name", city_name(dest))
            bucket[dest] = enriched

    if not per_origin:
        return []

    order = [o for o in (origins_order or UZ_AIRPORTS) if o in per_origin]
    order += [o for o in per_origin if o not in order]

    # 2) Yo'nalishlarni navbatma-navbat aralashtiramiz (JED, MED, JED, MED ...)
    selected: list[dict] = []
    used_dest_count: dict[str, int] = {}
    for i, origin in enumerate(order):
        bucket = per_origin[origin]
        preferred = SAUDI_DESTINATIONS[i % len(SAUDI_DESTINATIONS)]
        chosen = bucket.get(preferred)
        if chosen is None:
            # Afzal yo'nalish yo'q bo'lsa — mavjudlaridan eng arzoni
            chosen = sorted(bucket.values(), key=lambda x: float(x.get("value") or 10 ** 9))[0]
        selected.append(chosen)
        dest = chosen.get("destination")
        used_dest_count[dest] = used_dest_count.get(dest, 0) + 1
        if len(selected) >= limit:
            break

    return selected


async def get_calendar_prices(
    origin_city: str,
    destination_city: str,
    start_date: str | None = None,
    days: int = 30,
) -> list[dict]:
    """Arzon narxlar taqvimi: har bir kun uchun eng arzon narxni qaytaradi."""
    origin = to_iata(origin_city)
    destination = to_iata(destination_city)
    days = max(1, min(int(days or 30), 60))

    try:
        start = datetime.strptime((start_date or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        start = date.today()
    if start < date.today():
        start = date.today()

    day_list = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    cheapest: dict[str, dict] = {}

    if origin and destination:
        months = sorted({d[:7] for d in day_list})
        async with httpx.AsyncClient(timeout=20) as client:
            for month in months:
                params = {
                    "origin": origin,
                    "destination": destination,
                    "departure_at": month,
                    "sorting": "price",
                    "direct": "false",
                    "currency": "usd",
                    "limit": 100,
                    "one_way": "true",
                    "token": settings.TRAVELPAYOUTS_TOKEN,
                    "marker": settings.TRAVELPAYOUTS_MARKER,
                }
                try:
                    r = await client.get(PRICES_FOR_DATES_URL, params=params)
                    if r.status_code != 200:
                        continue
                    for item in r.json().get("data", []) or []:
                        raw_date = str(item.get("departure_at") or "")[:10]
                        if raw_date not in day_list:
                            continue
                        price = _apply_markup(item.get("price"))
                        if price is None:
                            continue
                        current = cheapest.get(raw_date)
                        if current is None or float(price) < float(current["price"]):
                            cheapest[raw_date] = {
                                "date": raw_date,
                                "price": float(price),
                                "airline": item.get("airline") or "",
                                "flight_number": item.get("flight_number") or "",
                                "transfers": item.get("transfers", 0),
                                "source": "api",
                            }
                except Exception as e:
                    log.warning(f"Taqvim narxlarini olishda xatolik ({month}): {e}")
                    continue

    calendar: list[dict] = []
    for day in day_list:
        found = cheapest.get(day)
        if found:
            calendar.append(found)
        else:
            calendar.append({
                "date": day,
                "price": float(_pseudo_price(origin, destination, day)),
                "airline": "",
                "flight_number": "",
                "transfers": 0,
                "source": "estimate",
            })
    return calendar
