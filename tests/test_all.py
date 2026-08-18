import os
from unittest.mock import AsyncMock, patch

import pytest

# Set dummy env vars for testing before importing settings
os.environ["BOT_TOKEN"] = "123456:fake_bot_token_for_testing"
os.environ["ADMIN_CHAT_ID"] = "-100123456789"
os.environ["CHANNEL_ID"] = "-100987654321"
os.environ["SUPABASE_URL"] = "https://fake.supabase.co"
os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy"
os.environ["TRAVELPAYOUTS_TOKEN"] = "dummy_travelpayouts_token"
os.environ["WEBHOOK_BASE_URL"] = "https://example.com"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["CRON_SECRET"] = "testcron"

import database as db
import order_actions
import travelpayouts as tp
from pdf_generator import generate_ticket_pdf


def test_to_iata():
    assert tp.to_iata("Tashkent") == "TAS"
    assert tp.to_iata("toshkent") == "TAS"
    assert tp.to_iata("TAS") == "TAS"
    assert tp.to_iata("Samarkand") == "SKD"
    assert tp.to_iata("samarqand") == "SKD"
    assert tp.to_iata("Jeddah") == "JED"
    assert tp.to_iata("jidda") == "JED"
    assert tp.to_iata("Madinah") == "MED"
    assert tp.to_iata("madina") == "MED"
    assert tp.to_iata("Dubai") == "DXB"
    assert tp.to_iata("Istanbul") == "IST"
    assert tp.to_iata("xyz") == "XYZ"
    assert tp.to_iata("") == ""


def test_apply_markup():
    tp.settings.MARKUP_PERCENT = 10.0
    assert tp._apply_markup(100) == 110.0
    assert tp._apply_markup("100") == 110.0
    assert tp._apply_markup(None) is None
    assert tp._apply_markup("invalid") == "invalid"


def test_build_affiliate_link():
    tp.settings.TRAVELPAYOUTS_MARKER = "12345"
    link = tp._build_affiliate_link("/search/TAS0101JED1")
    assert "marker=12345" in link
    assert "https://www.aviasales.com/search/TAS0101JED1" in link


def test_pdf_generation_complete():
    order = {
        "id": 42,
        "origin": "TAS",
        "destination": "JED",
        "depart_date": "2026-09-15",
        "passengers": 2,
        "price": 450,
        "flight_data": {
            "airline": "Centrum Air",
            "flight_number": "C6-331"
        }
    }
    passport = {
        "first_name": "Ali",
        "last_name": "Valiyev",
        "passport_number": "FA1234567",
        "birth_year": "1992",
        "expiry_date": "2032-05-10"
    }
    pdf = generate_ticket_pdf(order, passport)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000


def test_pdf_generation_missing_fields():
    order = {"id": 1}
    passport = {}
    pdf = generate_ticket_pdf(order, passport)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000


def test_pdf_generation_string_flight_data():
    order = {
        "id": 99,
        "origin": "TAS",
        "destination": "MED",
        "flight_data": '{"airline": "Flynas", "flight_number": "XY-612"}'
    }
    passport = {"first_name": "Karim", "last_name": "Nazarov"}
    pdf = generate_ticket_pdf(order, passport)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000


@pytest.mark.asyncio
async def test_confirm_order_flow():
    bot_mock = AsyncMock()
    
    with patch.object(db, "get_order", return_value={"id": 10, "telegram_user_id": 12345678, "origin": "TAS", "destination": "JED"}), \
         patch.object(db, "get_passport_by_order", return_value={"first_name": "Ali", "last_name": "Valiyev"}), \
         patch.object(db, "update_order") as mock_update:
        
        result = await order_actions.confirm_order(bot_mock, 10)
        assert result["ok"] is True
        bot_mock.send_document.assert_awaited_once()
        mock_update.assert_called_once_with(10, {"status": "confirmed"})


@pytest.mark.asyncio
async def test_reject_order_flow():
    bot_mock = AsyncMock()
    
    with patch.object(db, "get_order", return_value={"id": 10, "telegram_user_id": 12345678}), \
         patch.object(db, "update_order") as mock_update:
        
        result = await order_actions.reject_order(bot_mock, 10, "Chek noaniq")
        assert result["ok"] is True
        bot_mock.send_message.assert_awaited_once()
        mock_update.assert_called_once_with(10, {"status": "rejected"})
