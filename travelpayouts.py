import httpx
from config import settings

# Shahar nomlaridan IATA kodlariga moslashtirish
IATA = {
    "tashkent": "TAS",
    "toshkent": "TAS",
    "samarkand": "SKD",
    "samarqand": "SKD",
    "jeddah": "JED",
    "jidda": "JED",
    "madinah": "MED",
    "madina": "MED",
}

PRICES_FOR_DATES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
LATEST_PRICES_URL = "https://api.travelpayouts.com/v2/prices/latest"


def to_iata(city: str) -> str:
    return IATA.get(city.strip().lower(), city.strip().upper())


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
        results.append({
            "origin": item.get("origin"),
            "destination": item.get("destination"),
            "price": item.get("price"),
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
                        "value": item.get("value"),
                        "depart_date": item.get("depart_date"),
                    })
    return results
