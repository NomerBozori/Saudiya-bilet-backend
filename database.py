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


def delete_order(order_id: int) -> None:
    """Buyurtma va unga bog'liq pasportlarni to'liq o'chiradi (admin uchun)."""
    try:
        supabase.table("passports").delete().eq("order_id", order_id).execute()
    except Exception:
        pass
    supabase.table("orders").delete().eq("id", order_id).execute()


def delete_all_orders() -> int:
    """Barcha buyurtmalarni va ularga bog'liq pasportlarni o'chiradi.
    
    Qaytaradi: o'chirilgan buyurtmalar soni.
    """
    # Avval barcha order ID larni olish
    res = supabase.table("orders").select("id").execute()
    order_ids = [row["id"] for row in (res.data or []) if row.get("id") is not None]
    
    if not order_ids:
        return 0
    
    # Pasportlarni o'chirish
    try:
        supabase.table("passports").delete().in_("order_id", order_ids).execute()
    except Exception:
        pass
    
    # Buyurtmalarni o'chirish
    supabase.table("orders").delete().in_("id", order_ids).execute()
    return len(order_ids)


def delete_orders_by_status(status: str) -> int:
    """Berilgan holatdagi (masalan 'rejected') barcha buyurtmalarni o'chiradi.

    Qaytaradi: o'chirilgan buyurtmalar soni.
    """
    res = supabase.table("orders").select("id").eq("status", status).execute()
    order_ids = [row["id"] for row in (res.data or []) if row.get("id") is not None]
    if not order_ids:
        return 0

    try:
        supabase.table("passports").delete().in_("order_id", order_ids).execute()
    except Exception:
        pass
    supabase.table("orders").delete().in_("id", order_ids).execute()
    return len(order_ids)


# ==================== VIZA ARIZALARI ====================
def create_visa_application(data: dict) -> dict:
    """Yangi viza arizasini saqlaydi."""
    res = supabase.table("visa_applications").insert(data).execute()
    return res.data[0] if res.data else data


def get_visa_application(application_id: int) -> dict | None:
    res = (
        supabase.table("visa_applications")
        .select("*")
        .eq("id", application_id)
        .maybe_single()
        .execute()
    )
    return res.data if res else None


def get_visa_applications_by_user(telegram_user_id: int, limit: int = 20) -> list[dict]:
    res = (
        supabase.table("visa_applications")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def list_visa_applications(status: str | None = None, limit: int = 200) -> list[dict]:
    query = supabase.table("visa_applications").select("*")
    if status:
        query = query.eq("status", status)
    res = query.order("id", desc=True).limit(limit).execute()
    return res.data or []


def update_visa_application(application_id: int, data: dict) -> dict:
    res = (
        supabase.table("visa_applications")
        .update(data)
        .eq("id", application_id)
        .execute()
    )
    return res.data[0] if res.data else data


def delete_visa_application(application_id: int) -> None:
    supabase.table("visa_applications").delete().eq("id", application_id).execute()


# ==================== NARX TUSHISHI OBUNALARI ====================
def create_price_alert(data: dict) -> dict:
    """Bir xil faol obuna bo'lsa uni yangilaydi, aks holda yangisini yaratadi."""
    existing_res = (
        supabase.table("price_alerts")
        .select("*")
        .eq("telegram_user_id", data["telegram_user_id"])
        .eq("origin", data["origin"])
        .eq("destination", data["destination"])
        .eq("date_from", data["date_from"])
        .eq("date_to", data["date_to"])
        .eq("target_price", data["target_price"])
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    existing = existing_res.data if existing_res else None
    if existing:
        update_data = {
            "username": data.get("username"),
            "is_active": True,
            "last_price": None,
            "last_checked_at": None,
            "last_notified_at": None,
        }
        res = (
            supabase.table("price_alerts")
            .update(update_data)
            .eq("id", existing["id"])
            .execute()
        )
        return res.data[0] if res.data else {**existing, **update_data}

    res = supabase.table("price_alerts").insert(data).execute()
    return res.data[0] if res.data else data


def get_price_alert(alert_id: int) -> dict | None:
    res = (
        supabase.table("price_alerts")
        .select("*")
        .eq("id", alert_id)
        .maybe_single()
        .execute()
    )
    return res.data if res else None


def get_price_alerts_by_user(telegram_user_id: int, active_only: bool = False, limit: int = 50) -> list[dict]:
    query = supabase.table("price_alerts").select("*").eq("telegram_user_id", telegram_user_id)
    if active_only:
        query = query.eq("is_active", True)
    res = query.order("id", desc=True).limit(limit).execute()
    return res.data or []


def list_price_alerts(active_only: bool = False, limit: int = 500) -> list[dict]:
    query = supabase.table("price_alerts").select("*")
    if active_only:
        query = query.eq("is_active", True)
    res = query.order("id", desc=True).limit(limit).execute()
    return res.data or []


def update_price_alert(alert_id: int, data: dict) -> dict:
    res = supabase.table("price_alerts").update(data).eq("id", alert_id).execute()
    return res.data[0] if res.data else data


def delete_price_alert(alert_id: int) -> None:
    supabase.table("price_alerts").delete().eq("id", alert_id).execute()
