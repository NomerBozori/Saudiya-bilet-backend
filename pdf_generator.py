import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors


def generate_ticket_pdf(order: dict, passport: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Ranglar palitrasi
    PRIMARY = colors.HexColor("#0F5132")      # Saudi Green
    PRIMARY_DARK = colors.HexColor("#082F1D")
    ACCENT = colors.HexColor("#D4AF37")       # Gold
    BG_LIGHT = colors.HexColor("#F8FAFC")
    TEXT_DARK = colors.HexColor("#0F172A")
    TEXT_MUTED = colors.HexColor("#64748B")
    BORDER_COLOR = colors.HexColor("#E2E8F0")

    # 1. Asosiy fon va sarlavha paneli
    c.setFillColor(PRIMARY)
    c.rect(0, height - 3.8 * cm, width, 3.8 * cm, fill=True, stroke=False)

    # Oltin rangli chiziq
    c.setFillColor(ACCENT)
    c.rect(0, height - 3.9 * cm, width, 0.1 * cm, fill=True, stroke=False)

    # Sarlavha matnlari
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(1.8 * cm, height - 1.6 * cm, "ELECTRONIC FLIGHT TICKET / AVIACHIPTA")
    
    c.setFont("Helvetica", 11)
    c.drawString(1.8 * cm, height - 2.4 * cm, "Saudiya Aviabiletlari & Umra Xizmatlari Rasmiy Tasdiqnomasi")

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 1.8 * cm, height - 1.6 * cm, f"E-TICKET: #{order['id']:06d}")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 1.8 * cm, height - 2.4 * cm, "STATUS: CONFIRMED / TASDIQLANGAN")

    y = height - 4.8 * cm

    # 2. Reys yo'nalishi banneri (TAS ➔ JED)
    origin = str(order.get('origin', '-')).upper()
    destination = str(order.get('destination', '-')).upper()
    depart_date = str(order.get('depart_date', '-'))
    flight = order.get("flight_data") or {}
    airline = str(flight.get("airline", "Umra Chipta"))
    flight_num = str(flight.get("flight_number", "SAU-777"))

    # Kartochka foni
    c.setFillColor(BG_LIGHT)
    c.setStrokeColor(BORDER_COLOR)
    c.roundRect(1.5 * cm, y - 2.4 * cm, width - 3.0 * cm, 2.6 * cm, 8, fill=True, stroke=True)

    c.setFillColor(PRIMARY_DARK)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(2.2 * cm, y - 1.2 * cm, origin)
    
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(6.0 * cm, y - 1.2 * cm, "✈ ➔")

    c.setFillColor(PRIMARY_DARK)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(8.2 * cm, y - 1.2 * cm, destination)

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(2.2 * cm, y - 1.9 * cm, f"SANA: {depart_date}")
    c.drawString(6.0 * cm, y - 1.9 * cm, f"AVIAKOMPANIYA: {airline}")
    c.drawString(12.0 * cm, y - 1.9 * cm, f"REYS: {flight_num}")

    y -= 3.4 * cm

    # 3. YO'LOVCHI MA'LUMOTLARI (PASSENGER DETAILS)
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1.5 * cm, y, "1. YO'LOVCHI MA'LUMOTLARI (PASSENGER DETAILS)")
    y -= 0.6 * cm

    # Jadval ramkasi
    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER_COLOR)
    c.roundRect(1.5 * cm, y - 2.8 * cm, width - 3.0 * cm, 2.8 * cm, 6, fill=True, stroke=True)

    c.setFillColor(TEXT_DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2.0 * cm, y - 0.7 * cm, "F.I.Sh (Yo'lovchi ismi):")
    c.drawString(2.0 * cm, y - 1.3 * cm, "Xorijiy Pasport (Zagran):")
    c.drawString(2.0 * cm, y - 1.9 * cm, "Tug'ilgan yili:")
    c.drawString(2.0 * cm, y - 2.5 * cm, "Amal qilish muddati:")

    c.setFont("Helvetica", 10)
    c.drawString(8.0 * cm, y - 0.7 * cm, f"{passport.get('first_name', '')} {passport.get('last_name', '')}".upper())
    c.drawString(8.0 * cm, y - 1.3 * cm, str(passport.get('passport_number', '-')).upper())
    c.drawString(8.0 * cm, y - 1.9 * cm, str(passport.get('birth_year', '-')))
    c.drawString(8.0 * cm, y - 2.5 * cm, str(passport.get('expiry_date', '-')))

    y -= 3.8 * cm

    # 4. REYS VA TO'LOV TAFSILOTLARI (FLIGHT & PAYMENT)
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1.5 * cm, y, "2. REYS VA TO'LOV TAFSILOTLARI (FLIGHT & FARE)")
    y -= 0.6 * cm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER_COLOR)
    c.roundRect(1.5 * cm, y - 3.4 * cm, width - 3.0 * cm, 3.4 * cm, 6, fill=True, stroke=True)

    c.setFillColor(TEXT_DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2.0 * cm, y - 0.7 * cm, "Buyurtma ID:")
    c.drawString(2.0 * cm, y - 1.3 * cm, "Yo'lovchilar soni:")
    c.drawString(2.0 * cm, y - 1.9 * cm, "Bagaj ruxsati (Yuk):")
    c.drawString(2.0 * cm, y - 2.5 * cm, "Klass / Xizmat turi:")
    c.drawString(2.0 * cm, y - 3.1 * cm, "Jami to'langan summa:")

    c.setFont("Helvetica", 10)
    c.drawString(8.0 * cm, y - 0.7 * cm, f"#{order['id']}")
    c.drawString(8.0 * cm, y - 1.3 * cm, f"{order.get('passengers', 1)} kishi")
    c.drawString(8.0 * cm, y - 1.9 * cm, "30 kg (Bagaj) + 7 kg (Qo'l yuki)")
    c.drawString(8.0 * cm, y - 2.5 * cm, "Ekonom / Umra Charter")
    
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(PRIMARY)
    c.drawString(8.0 * cm, y - 3.1 * cm, f"{order.get('price', '-')} USD (TO'LANGAN / PAID)")

    y -= 4.4 * cm

    # 5. MUHIM ESLATMALAR VA QOIDALAR
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1.5 * cm, y, "MUHIM ESLATMALAR / IMPORTANT NOTICE:")
    y -= 0.5 * cm

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 8)
    notices = [
        "1. Aeroportga parvozdan kamida 3 soat oldin yetib kelishingiz shart.",
        "2. Pasportingizning amal qilish muddati Saudiya Arabistoniga kirish sanasidan kamida 6 oy bo'lishi lozim.",
        "3. Har bir yo'lovchi o'zi bilan elektron viza nusxasi va ushbu aviachiptani olib yurishi tavsiya etiladi.",
        "4. Savollar yoki transfer xizmatlari uchun Telegram: @Saudiya_Admin orqali bog'lanishingiz mumkin."
    ]
    for n in notices:
        c.drawString(1.5 * cm, y, n)
        y -= 0.4 * cm

    # Pastki qism / Footer
    c.setStrokeColor(BORDER_COLOR)
    c.line(1.5 * cm, 1.8 * cm, width - 1.5 * cm, 1.8 * cm)
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(TEXT_MUTED)
    c.drawString(1.5 * cm, 1.3 * cm, "Saudiya Biletlari & Umra Xizmatlari — Rasmiy Elektron Tizim")
    c.drawRightString(width - 1.5 * cm, 1.3 * cm, "www.saudiyabiletlari.uz")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
