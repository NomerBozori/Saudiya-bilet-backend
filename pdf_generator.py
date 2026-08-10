import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


def generate_ticket_pdf(order: dict, passport: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Sarlavha paneli
    c.setFillColorRGB(0.06, 0.48, 0.42)
    c.rect(0, height - 3.2 * cm, width, 3.2 * cm, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(2 * cm, height - 1.6 * cm, "E-TICKET / AVIACHIPTA")
    c.setFont("Helvetica", 11)
    c.drawString(2 * cm, height - 2.4 * cm, "Umra Chipta — rasmiy elektron tasdiqnoma")

    c.setFillColorRGB(0, 0, 0)
    y = height - 4.4 * cm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(2 * cm, y, f"Buyurtma raqami: #{order['id']}")
    y -= 1.0 * cm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, y, "YO'LOVCHI MA'LUMOTLARI")
    y -= 0.7 * cm
    c.setFont("Helvetica", 11)
    passenger_lines = [
        f"F.I.Sh: {passport['first_name']} {passport['last_name']}",
        f"Passport raqami: {passport['passport_number']}",
        f"Tug'ilgan yil: {passport['birth_year']}",
        f"Passport amal qilish muddati: {passport['expiry_date']}",
    ]
    for line in passenger_lines:
        c.drawString(2 * cm, y, line)
        y -= 0.65 * cm

    y -= 0.4 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, y, "REYS MA'LUMOTLARI")
    y -= 0.7 * cm
    c.setFont("Helvetica", 11)

    flight = order.get("flight_data") or {}
    flight_lines = [
        f"Qayerdan: {order.get('origin', '-')}",
        f"Qayerga: {order.get('destination', '-')}",
        f"Jo'nash sanasi: {order.get('depart_date', '-')}",
        f"Yo'lovchilar soni: {order.get('passengers', 1)}",
        f"Aviakompaniya: {flight.get('airline', '-')}",
        f"Reys raqami: {flight.get('flight_number', '-')}",
        f"Narxi: {order.get('price', '-')} USD",
    ]
    for line in flight_lines:
        c.drawString(2 * cm, y, line)
        y -= 0.65 * cm

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(2 * cm, 2 * cm, "Ushbu hujjat elektron chipta tasdiqnomasi hisoblanadi.")
    c.drawString(2 * cm, 1.5 * cm, "Savollar uchun: Telegram bot orqali murojaat qiling.")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
