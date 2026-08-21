"""Telegram inline klaviaturalari (admin 1-click tugmalari)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Callback data prefikslari
CB_CONFIRM_PREFIX = "adm_confirm"
CB_REJECT_PREFIX = "adm_reject"
CB_REJECT_CONFIRM_PREFIX = "adm_rejyes"
CB_CANCEL = "adm_cancel"


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Yangi buyurtma / to'lov cheki xabari tagidagi 1-click tugmalar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash & PDF", callback_data=f"{CB_CONFIRM_PREFIX}:{order_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"{CB_REJECT_PREFIX}:{order_id}"),
        ]
    ])


def admin_reject_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Rad etishni tasdiqlash uchun ikkinchi bosqich tugmalari."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚫 Ha, rad etilsin", callback_data=f"{CB_REJECT_CONFIRM_PREFIX}:{order_id}"),
            InlineKeyboardButton(text="↩️ Bekor qilish", callback_data=f"{CB_CANCEL}:{order_id}"),
        ]
    ])
