from supabase import Client, create_client

from config import settings

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def create_order(data: dict) -> dict:
    res = supabase.table("orders").insert(data).execute()
    return res.data[0] if res.data else {}


def get_order(order_id: int) -> dict | None:
    res = supabase.table("orders").select("*").eq("id", order_id).maybe_single().execute()
    return res.data if res else None


def update_order(order_id: int, data: dict) -> dict:
    res = supabase.table("orders").update(data).eq("id", order_id).execute()
    return res.data[0] if res.data else {}


def save_passport(order_id: int, passport: dict) -> dict:
    payload = {**passport, "order_id": order_id}
    res = supabase.table("passports").insert(payload).execute()
    return res.data[0] if res.data else payload


def get_passport_by_order(order_id: int) -> dict | None:
    res = supabase.table("passports").select("*").eq("order_id", order_id).maybe_single().execute()
    return res.data if res else None


def get_orders_by_user(telegram_user_id: int, limit: int = 20) -> list[dict]:
    """Mijozning buyurtmalar tarixini pasportlari bilan birga qaytaradi."""
    res = (
        supabase.table("orders")
        .select("*, passports(*)")
        .eq("telegram_user_id", telegram_user_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def upload_file(bucket: str, path: str, file_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Supabase Storage'ga fayl yuklaydi va public URL qaytaradi."""
    supabase.storage.from_(bucket).upload(
        path,
        file_bytes,
        {"content-type": content_type, "upsert": "true"},
    )
    return supabase.storage.from_(bucket).get_public_url(path)


# ==================== ADMIN: BUYURTMALAR RO'YXATI ====================
def get_orders_with_passport(status: str | None = None, limit: int = 100) -> list[dict]:
    """Buyurtmalarni pasport ma'lumotlari bilan birga qaytaradi (admin panel uchun)."""
    query = supabase.table("orders").select("*, passports(*)")
    if status:
        query = query.eq("status", status)
    res = query.order("id", desc=True).limit(limit).execute()
    return res.data or []


# ==================== ADMIN: QO'LDA CHIPTA QO'SHISH ====================
def create_manual_flight(data: dict) -> dict:
    res = supabase.table("manual_flights").insert(data).execute()
    return res.data[0] if res.data else {}


def list_manual_flights(origin: str | None = None, destination: str | None = None, depart_date: str | None = None) -> list[dict]:
    query = supabase.table("manual_flights").select("*").eq("is_active", True)
    if origin:
        query = query.ilike("origin", origin.strip())
    if destination:
        query = query.ilike("destination", destination.strip())
    if depart_date:
        query = query.eq("depart_date", depart_date.strip())
    res = query.order("price").execute()
    return res.data or []


def list_all_manual_flights() -> list[dict]:
    res = supabase.table("manual_flights").select("*").order("id", desc=True).execute()
    return res.data or []


def delete_manual_flight(flight_id: int) -> None:
    supabase.table("manual_flights").delete().eq("id", flight_id).execute()


def deactivate_manual_flight(flight_id: int) -> None:
    supabase.table("manual_flights").update({"is_active": False}).eq("id", flight_id).execute()
