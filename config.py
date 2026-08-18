from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int          # Admin guruh/kanal chat ID (masalan -1001234567890)
    CHANNEL_ID: int             # Kunlik post yuboriladigan kanal ID
    ADMIN_USERNAME: str = "nuriddinovdfg"

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str           # service_role kalit (server tomonida ishlatiladi)

    # Travelpayouts
    TRAVELPAYOUTS_TOKEN: str
    TRAVELPAYOUTS_MARKER: str = ""

    # Server
    WEBHOOK_BASE_URL: str        # Render.com'dagi https manzilingiz, masalan: https://umra-chipta.onrender.com
    CRON_SECRET: str = "change-me"
    ADMIN_PASSWORD: str = "change-me"   # /admin panelga kirish uchun parol

    # To'lov karta ma'lumotlari
    PAYMENT_CARD_NUMBER: str = "8600 0000 0000 0000"
    PAYMENT_CARD_OWNER: str = "F.I.Sh."

    # API'dan kelgan chiptalar narxiga qo'shiladigan avtomatik foyda ustamasi (%)
    MARKUP_PERCENT: float = 10.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
