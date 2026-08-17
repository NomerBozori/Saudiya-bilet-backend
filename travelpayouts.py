import httpx
from config import settings

# Shahar nomlaridan IATA kodlariga moslashtirish
IATA = {
    # O'zbekiston
    "tashkent": "TAS", "toshkent": "TAS", "tas": "TAS",
    "samarkand": "SKD", "samarqand": "SKD", "skd": "SKD",
    "bukhara": "BHK", "buxoro": "BHK", "bhk": "BHK",
    "fergana": "FEG", "fargona": "FEG", "farg'ona": "FEG", "feg": "FEG",
    "namangan": "NMA", "nma": "NMA",
    "andijan": "AZN", "andijon": "AZN", "azn": "AZN",
    "nukus": "NCU", "ncu": "NCU",
    "urgench": "UGC", "urganch": "UGC", "ugc": "UGC",
    "navoi": "NVI", "navoiy": "NVI", "nvi": "NVI",
    "termez": "TMJ", "termiz": "TMJ", "tmj": "TMJ",
    "qarshi": "KSQ", "karshi": "KSQ", "ksq": "KSQ",

    # Saudiya Arabistoni
    "jeddah": "JED", "jidda": "JED", "jed": "JED",
    "madinah": "MED", "madina": "MED", "med": "MED",
    "riyadh": "RUH", "riyod": "RUH", "ar-riyod": "RUH", "ruh": "RUH",
    "dammam": "DMM", "dmm": "DMM",
    "taif": "TIF", "toif": "TIF", "tif": "TIF",
}

PRICES_FOR_DATES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
LATEST_PRICES_URL = "https://api.travelpayouts.com/v2/prices/latest"


def to_iata(city: str) -> str:
    if not city:
        return ""
    clean = city.strip().lower()
    return IATA.get(clean, city.strip().upper())


def _apply_markup(price):
    """API'dan kelgan narxga foyda ustamasini (MARKUP_PERCENT) qo'shadi."""
    if price is None:
        return price
    try:
        marked_up = float(price) * (1 + settings.MARKUP_PERCENT / 100)
        return round(marked_up, 2)
    except (TypeError, ValueError):
        return price


def _build_affiliate_link(raw_link: str) -> str:
    """Aviasales havolasiga marker qo'shadi, shunda buyurtmadan komissiya sizga hisoblanadi."""
    if not raw_link:
        return ""
    base = f"https://www.aviasales.com{raw_link}"
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}marker={settings.TRAVELPAYOUTS_MARKER}"


async def search_flights(origin_city: str, destination_city: str, depart_date: str, limit: int = 15) -> list[dict]:
    """Belgilangan sana uchun mavjud chiptalarni qidiradi (narx bo'yicha saralangan)."""
    origin = to_iata(origin_city)
    destination = to_iata(destination_city)

    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": depart_date,
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
        r.raise_for_status()
        payload = r.json()

    results = []
    for item in payload.get("data", []):
        original_price = item.get("price")
        marked_up_price = _apply_markup(original_price)
        results.append({
            "origin": item.get("origin"),
            "destination": item.get("destination"),
            "price": marked_up_price,
            "airline": item.get("airline"),
            "flight_number": item.get("flight_number"),
            "departure_at": item.get("departure_at"),
            "return_at": item.get("return_at"),
            "transfers": item.get("transfers", 0),
            "link": _build_affiliate_link(item.get("link", "")),
        })
    return results


async def get_daily_cheapest(origin_city: str = "tashkent") -> list[dict]:
    """Kunlik avto-post uchun Jidda va Madinaga eng arzon narxlarni oladi."""
    origin = to_iata(origin_city)
    results = []

    async with httpx.AsyncClient(timeout=20) as client:
        for dest in ("JED", "MED"):
            params = {
                "origin": origin,
                "destination": dest,
                "currency": "usd",
                "token": settings.TRAVELPAYOUTS_TOKEN,
                "marker": settings.TRAVELPAYOUTS_MARKER,
            }
            r = await client.get(LATEST_PRICES_URL, params=params)
            if r.status_code == 200:
                for item in r.json().get("data", []):
                    results.append({
                        "origin": origin,
                        "destination": dest,
                        "value": _apply_markup(item.get("value")),
                        "depart_date": item.get("depart_date"),
                    })
    return results
