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

# ==================== AVTO-POST SANA OYNASI (3–35 KUN) ====================
# Kanalga faqat yaqin kunlardagi reyslar chiqadi: bugundan 3 kundan 35 kungacha.
# Shu tufayli uzoq dekabr/yanvar sanalari postga tushmaydi.
MIN_DAYS_AHEAD: int = 3
MAX_DAYS_AHEAD: int = 35

# Sanalarni o'zbekcha ko'rsatish uchun hafta kunlari
WEEKDAYS_UZ: list[str] = [
    "Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba",
]

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


# ==================== SANA YORDAMCHILARI (3–35 KUN OYNASI) ====================
def parse_date(value) -> date | None:
    """'2026-09-05', '2026-09-05T10:20:00+03:00' yoki date/datetime -> date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def days_until(value, today: date | None = None) -> int | None:
    """Bugundan berilgan sanagacha necha kun qolganini qaytaradi."""
    parsed = parse_date(value)
    if parsed is None:
        return None
    return (parsed - (today or date.today())).days


def is_within_window(
    value,
    min_days: int = MIN_DAYS_AHEAD,
    max_days: int = MAX_DAYS_AHEAD,
    today: date | None = None,
) -> bool:
    """Sana yaqin 3–35 kun oynasiga tushadimi? (uzoq oylar chiqib ketmasligi uchun)"""
    left = days_until(value, today=today)
    if left is None:
        return False
    return min_days <= left <= max_days


def filter_offers_by_window(
    offers: list[dict],
    min_days: int = MIN_DAYS_AHEAD,
    max_days: int = MAX_DAYS_AHEAD,
    today: date | None = None,
) -> list[dict]:
    """Faqat 3–35 kun ichidagi sanalarga ega takliflarni qoldiradi.

    Sanasi yo'q yoki oynadan tashqaridagi (masalan uzoq dekabr/yanvar) takliflar
    o'chirib tashlanadi. Har bir taklifga `days_left` va `depart_date_label`
    maydonlari qo'shiladi.
    """
    base_day = today or date.today()
    filtered: list[dict] = []
    for offer in offers or []:
        left = days_until(offer.get("depart_date"), today=base_day)
        if left is None or left < min_days or left > max_days:
            continue
        enriched = dict(offer)
        enriched["days_left"] = left
        enriched["depart_date"] = parse_date(offer.get("depart_date")).isoformat()
        enriched["depart_date_label"] = format_date_uz(enriched["depart_date"])
        filtered.append(enriched)
    return filtered


def format_date_uz(value) -> str:
    """'2026-09-05' -> '05.09.2026 (Juma)'."""
    parsed = parse_date(value)
    if parsed is None:
        return str(value or "")
    return f"{parsed.strftime('%d.%m.%Y')} ({WEEKDAYS_UZ[parsed.weekday()]})"


def window_dates(
    min_days: int = MIN_DAYS_AHEAD,
    max_days: int = MAX_DAYS_AHEAD,
    today: date | None = None,
) -> list[str]:
    """Oynadagi barcha sanalar ro'yxati (ISO formatda)."""
    base_day = today or date.today()
    return [(base_day + timedelta(days=i)).isoformat() for i in range(min_days, max_days + 1)]


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


# Travelpayouts/Aviasales javobida tashuvchi ba'zan IATA kodi, ba'zan to'liq nom
# ko'rinishida keladi. Ushbu ikki tashuvchi uchun yagona, foydalanuvchiga tushunarli
# yorliq ishlatamiz. Bu alohida taxminiy reys yaratmaydi: faqat agregatordan kelgan
# haqiqiy takliflar boyitiladi.
PARTNER_AIRLINES = {
    "centrum air": ("C6", "⭐ Centrum Air (To'g'ridan-to'g'ri)", 0),
    "air arabia": ("G9", "💸 Air Arabia (Arzon Tranzit)", 1),
}


def enrich_partner_offer(offer: dict) -> dict:
    """Centrum Air va Air Arabia taklifiga mahsulot yorlig'ini qo'shadi.

    `airline` maydoni UI va Telegram postlarida ishlatilgani sababli unda tayyor
    yorliq saqlanadi; asl tashuvchi kodi `airline_code`da yo'qolmaydi.
    """
    enriched = dict(offer)
    raw_airline = str(enriched.get("airline") or "").strip()
    raw_code = str(enriched.get("airline_code") or raw_airline).strip().upper()
    normalized = raw_airline.casefold()

    for name, (code, label, expected_transfers) in PARTNER_AIRLINES.items():
        if normalized == name or raw_code == code or normalized == code.casefold():
            enriched["airline_code"] = code
            enriched["airline_name"] = name.title()
            enriched["airline"] = label
            enriched["airline_label"] = label
            enriched["partner_airline"] = name
            # Centrum charterlari to'g'ridan-to'g'ri; Air Arabia taklifi tranzit
            # ekanini faqat agregator transfer sonini bermaganda to'ldiramiz.
            if enriched.get("transfers") is None:
                enriched["transfers"] = expected_transfers
            return enriched
    return enriched


def partner_priority(offer: dict) -> int:
    """Kunlik postda yangi tashuvchilar umumiy variantlar orasida yo'qolmasin."""
    partner = str(offer.get("partner_airline") or "").casefold()
    return {"centrum air": 0, "air arabia": 1}.get(partner, 2)


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
        results.append(enrich_partner_offer({
            "origin": item.get("origin") or origin,
            "destination": item.get("destination") or destination,
            "price": marked_up_price,
            "airline": item.get("airline") or "Aviakompaniya",
            "flight_number": item.get("flight_number") or "",
            "departure_at": item.get("departure_at"),
            "return_at": item.get("return_at"),
            "transfers": item.get("transfers", 0),
            "link": _build_affiliate_link(item.get("link", "")),
        }))
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


async def _fetch_window_for_route(
    client: httpx.AsyncClient,
    origin: str,
    destination: str,
    min_days: int = MIN_DAYS_AHEAD,
    max_days: int = MAX_DAYS_AHEAD,
    today: date | None = None,
) -> list[dict]:
    """Yaqin 3–35 kun oynasidagi haqiqiy sanalar bo'yicha narxlarni oladi.

    Travelpayouts v3 `prices_for_dates` oyma-oy so'raladi (oyna 2 oyni qamrashi mumkin),
    so'ng natijalar qat'iy ravishda oyna ichida filtrlanadi.
    """
    base_day = today or date.today()
    allowed = set(window_dates(min_days, max_days, today=base_day))
    months = sorted({d[:7] for d in allowed})

    offers: list[dict] = []
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
                if raw_date not in allowed:
                    continue
                price = _apply_markup(item.get("price"))
                if price is None:
                    continue
                offers.append(enrich_partner_offer({
                    "origin": origin,
                    "destination": destination,
                    "origin_name": city_name(origin),
                    "destination_name": city_name(destination),
                    "value": price,
                    "depart_date": raw_date,
                    "airline": item.get("airline") or "",
                    "flight_number": item.get("flight_number") or "",
                    "transfers": item.get("transfers", 0),
                    "source": "api",
                }))
        except Exception as e:
            log.warning(f"{origin}->{destination} ({month}) oynadagi narxlarni olishda xatolik: {e}")
            continue
    return offers


async def _fetch_route_offers(
    client: httpx.AsyncClient,
    origin: str,
    destination: str,
    min_days: int,
    max_days: int,
    today: date | None = None,
) -> list[dict]:
    """Avval aniq sanali (v3) narxlar, ular bo'lmasa — so'nggi narxlar (v2), ikkalasi ham oyna ichida."""
    offers = await _fetch_window_for_route(client, origin, destination, min_days, max_days, today=today)
    if offers:
        return offers
    latest = await _fetch_latest_for_route(client, origin, destination)
    return filter_offers_by_window(latest, min_days, max_days, today=today)


async def get_daily_cheapest(
    origin_city: str | None = None,
    origins: list[str] | None = None,
    destinations: list[str] | None = None,
    min_days: int = MIN_DAYS_AHEAD,
    max_days: int = MAX_DAYS_AHEAD,
) -> list[dict]:
    """Kunlik avto-post uchun narxlarni oladi.

    Sukut bo'yicha O'zbekistonning barcha 11 ta xalqaro aeroportidan
    Jidda (JED) va Madinaga (MED) narxlarni parallel ravishda yig'adi.
    Natijada faqat yaqin `min_days`–`max_days` (3–35) kun ichidagi reyslar qoladi.
    """
    if origins:
        origin_codes = [to_iata(o) for o in origins if o]
    elif origin_city:
        origin_codes = [to_iata(origin_city)]
    else:
        origin_codes = list(UZ_AIRPORTS)

    dest_codes = [to_iata(d) for d in (destinations or SAUDI_DESTINATIONS) if d]
    today = date.today()

    results: list[dict] = []
    async with httpx.AsyncClient(timeout=20) as client:
        tasks = [
            _fetch_route_offers(client, origin, dest, min_days, max_days, today=today)
            for origin in origin_codes
            for dest in dest_codes
        ]
        for chunk in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(chunk, list):
                results.extend(chunk)

    # Yakuniy qat'iy filtr: uzoq sanalar (dekabr, yanvar...) hech qanday holatda o'tmasin
    return filter_offers_by_window(results, min_days, max_days, today=today)


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
    min_days: int = MIN_DAYS_AHEAD,
    max_days: int = MAX_DAYS_AHEAD,
    today: date | None = None,
) -> list[dict]:
    """Barcha 11 ta aeroportdan Jidda/Madinaga zaxira (taxminiy) narxlar ro'yxati.

    Sanalar faqat yaqin 3–35 kun oynasidan tanlanadi — uzoq oylar (dekabr, yanvar)
    hech qachon zaxira postga tushmaydi.
    """
    origin_codes = origins or UZ_AIRPORTS
    dest_codes = destinations or SAUDI_DESTINATIONS
    base_day = today or date.today()
    span = max(1, max_days - min_days + 1)

    offers: list[dict] = []
    for idx, origin in enumerate(origin_codes):
        for j, dest in enumerate(dest_codes):
            # Sanalar oyna bo'ylab bir tekis taqsimlanadi (deterministik)
            offset = min_days + ((idx * len(dest_codes) + j) * 3) % span
            day = (base_day + timedelta(days=offset)).isoformat()
            offers.append({
                "origin": origin,
                "destination": dest,
                "origin_name": city_name(origin),
                "destination_name": city_name(dest),
                "value": _pseudo_price(origin, dest, day),
                "depart_date": day,
                "days_left": offset,
                "depart_date_label": format_date_uz(day),
                "source": "fallback",
            })
    return offers


def top_up_missing_cities(
    offers: list[dict],
    origins: list[str] | None = None,
    destinations: list[str] | None = None,
    min_days: int = MIN_DAYS_AHEAD,
    max_days: int = MAX_DAYS_AHEAD,
    today: date | None = None,
) -> list[dict]:
    """API'dan tushmay qolgan shaharlarni zaxira (3–35 kunlik) takliflar bilan to'ldiradi.

    Shu tufayli postda har doim O'zbekistonning 11 ta aeroporti ham qatnashadi.
    """
    origin_codes = origins or UZ_AIRPORTS
    present = {str(o.get("origin") or "").upper() for o in (offers or [])}
    missing = [o for o in origin_codes if o not in present]
    if not missing:
        return list(offers or [])
    return list(offers or []) + build_fallback_offers(
        origins=missing,
        destinations=destinations,
        min_days=min_days,
        max_days=max_days,
        today=today,
    )


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
        # Centrum Air va Air Arabia agregatordan kelgan bo'lsa, ular kunlik
        # postda boshqa tashuvchilarning arzon narxi orasida yo'qolib ketmaydi.
        # Bir xil ustuvorlikda odatdagidek eng arzon variant tanlanadi.
        if current is None or (partner_priority(offer), value) < (
            partner_priority(current), float(current.get("value") or 10 ** 9)
        ):
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
