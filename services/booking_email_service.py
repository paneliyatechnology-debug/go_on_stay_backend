import os
import logging
from io import BytesIO
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)


def generate_booking_pdf(booking) -> bytes:
    """
    Generates a professional PDF Booking Confirmation & Tax Invoice receipt
    using ReportLab and actual saved booking data.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=32,
        bottomMargin=32
    )

    styles = getSampleStyleSheet()

    # Custom Color Palette
    c_primary = colors.HexColor('#DC2626')     # Book My Room Crimson Red
    c_dark = colors.HexColor('#0F172A')        # Slate 900
    c_slate = colors.HexColor('#475569')       # Slate 600
    c_light = colors.HexColor('#F8FAFC')       # Slate 50
    c_border = colors.HexColor('#E2E8F0')      # Slate 200
    c_green = colors.HexColor('#16A34A')       # Emerald Green

    # Typography Styles
    style_brand = ParagraphStyle(
        'BMRBrand',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=c_primary
    )
    style_subtitle = ParagraphStyle(
        'BMRSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=c_slate
    )
    style_doc_title = ParagraphStyle(
        'BMRDocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        alignment=2,  # Right align
        textColor=c_dark
    )
    style_doc_sub = ParagraphStyle(
        'BMRDocSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=c_green
    )
    style_section_h = ParagraphStyle(
        'BMRSectionH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=c_dark
    )
    style_cell_label = ParagraphStyle(
        'BMRCellLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=c_slate
    )
    style_cell_value = ParagraphStyle(
        'BMRCellValue',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=c_dark
    )
    style_table_head = ParagraphStyle(
        'BMRTableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )
    style_table_cell = ParagraphStyle(
        'BMRTableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=c_dark
    )
    style_table_cell_bold = ParagraphStyle(
        'BMRTableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=c_dark
    )
    style_notes = ParagraphStyle(
        'BMRNotes',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=c_slate
    )

    elements = []

    # 1. Header Banner: Brand Logo on Left, Tax Invoice Title on Right
    header_data = [
        [
            Paragraph("<b>BOOK MY ROOM</b>", style_brand),
            Paragraph("<b>OFFICIAL BOOKING CONFIRMATION</b>", style_doc_title)
        ],
        [
            Paragraph("Premium Stays & Escrow Hospitality", style_subtitle),
            Paragraph(f"TAX INVOICE &bull; {booking.booking_status}", style_doc_sub)
        ]
    ]
    header_table = Table(header_data, colWidths=[260, 263])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceAfter=10))

    # 2. Key Metadata Block: Booking ID, Confirmation Time, Payment Status
    confirmed_date_str = (
        booking.confirmed_at.strftime('%d %b %Y, %I:%M %p')
        if booking.confirmed_at else
        booking.created_at.strftime('%d %b %Y, %I:%M %p')
    )
    captured_payment = booking.payments.filter(status='CAPTURED').first()
    payment_method = captured_payment.payment_method.upper() if (captured_payment and captured_payment.payment_method) else 'ONLINE (RAZORPAY)'
    razorpay_pid = captured_payment.razorpay_payment_id if captured_payment else (booking.razorpay_order_id or 'PAID-ESCROW')

    meta_data = [
        [
            Paragraph(f"<b>Booking Reference:</b> <font color='#DC2626'>{booking.booking_id}</font>", style_cell_value),
            Paragraph(f"<b>Confirmation Date:</b> {confirmed_date_str}", style_cell_value),
            Paragraph(f"<b>Payment:</b> <font color='#16A34A'>PAID &bull; {payment_method}</font>", style_cell_value)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[174, 174, 175])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_light),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    # 3. Two-Column Details: Guest Info (Left) vs Hotel & Stay Info (Right)
    hotel = booking.hotel
    room = booking.room
    hotel_addr = f"{hotel.address or ''}, {hotel.city or ''}, {hotel.state or ''} {hotel.zip_code or ''}".strip(', ')
    assigned_rooms = booking.room_number or 'Standard Assignment at Front Desk'

    guest_hotel_data = [
        [
            Paragraph("<b>PRIMARY GUEST DETAILS</b>", style_section_h),
            Paragraph("<b>HOTEL & PROPERTY DETAILS</b>", style_section_h)
        ],
        [
            Paragraph(f"<b>Guest Name:</b> {booking.guest_name}<br/>"
                      f"<b>Email:</b> {booking.guest_email}<br/>"
                      f"<b>Phone:</b> {booking.guest_phone}<br/>"
                      f"<b>Total Guests:</b> {booking.number_of_guests} Guest(s)<br/>"
                      f"<b>Meal Plan:</b> {booking.meal_plan.replace('_', ' ').title()}", style_cell_value),
            Paragraph(f"<b>Hotel:</b> <b>{hotel.name}</b> ({hotel.star_rating}&#9733;)<br/>"
                      f"<b>Address:</b> {hotel_addr}<br/>"
                      f"<b>Room Category:</b> {room.title if room else 'Hotel Room'}<br/>"
                      f"<b>Room(s) Booked:</b> {booking.number_of_rooms} Room(s) &bull; [{assigned_rooms}]<br/>"
                      f"<b>Check-in Time:</b> After {getattr(hotel, 'check_in_time', '12:00 PM')}<br/>"
                      f"<b>Check-out Time:</b> Before {getattr(hotel, 'check_out_time', '11:00 AM')}", style_cell_value)
        ]
    ]
    guest_hotel_table = Table(guest_hotel_data, colWidths=[260, 263])
    guest_hotel_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_light),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(guest_hotel_table)
    elements.append(Spacer(1, 10))

    # 4. Schedule Strip: Check-in / Check-out / Duration
    sched_data = [
        [
            Paragraph("<b>CHECK-IN DATE</b>", style_cell_label),
            Paragraph("<b>CHECK-OUT DATE</b>", style_cell_label),
            Paragraph("<b>TOTAL STAY DURATION</b>", style_cell_label)
        ],
        [
            Paragraph(f"<font size=10><b>{booking.check_in.strftime('%a, %d %b %Y')}</b></font>", style_cell_value),
            Paragraph(f"<font size=10><b>{booking.check_out.strftime('%a, %d %b %Y')}</b></font>", style_cell_value),
            Paragraph(f"<font size=10 color='#DC2626'><b>{booking.number_of_nights} Night(s)</b></font>", style_cell_value)
        ]
    ]
    sched_table = Table(sched_data, colWidths=[174, 174, 175])
    sched_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_light),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(sched_table)
    elements.append(Spacer(1, 12))

    # 5. Itemized Price Breakdown Table
    price_rows = [
        [
            Paragraph("<b>ITEM DESCRIPTION</b>", style_table_head),
            Paragraph("<b>QTY / NIGHTS</b>", style_table_head),
            Paragraph("<b>RATE (INR)</b>", style_table_head),
            Paragraph("<b>AMOUNT (INR)</b>", style_table_head)
        ],
        [
            Paragraph(f"Room Accommodation &bull; {room.title if room else 'Room'}", style_table_cell_bold),
            Paragraph(f"{booking.number_of_rooms} Rm x {booking.number_of_nights} Nts", style_table_cell),
            Paragraph(f"&#8377;{booking.price_per_night}", style_table_cell),
            Paragraph(f"&#8377;{booking.subtotal}", style_table_cell_bold)
        ]
    ]

    if booking.cleaning_fee and Decimal(str(booking.cleaning_fee)) > 0:
        price_rows.append([
            Paragraph("Property Cleaning & Sanitization Fee", style_table_cell),
            Paragraph("1 Stay", style_table_cell),
            Paragraph(f"&#8377;{booking.cleaning_fee}", style_table_cell),
            Paragraph(f"&#8377;{booking.cleaning_fee}", style_table_cell)
        ])

    if booking.service_fee and Decimal(str(booking.service_fee)) > 0:
        price_rows.append([
            Paragraph("Platform Concierge & Facilitation Fee", style_table_cell),
            Paragraph("1 Booking", style_table_cell),
            Paragraph(f"&#8377;{booking.service_fee}", style_table_cell),
            Paragraph(f"&#8377;{booking.service_fee}", style_table_cell)
        ])

    if booking.taxes and Decimal(str(booking.taxes)) > 0:
        price_rows.append([
            Paragraph("Hospitality GST & State Taxes (Combined)", style_table_cell),
            Paragraph("Standard", style_table_cell),
            Paragraph(f"&#8377;{booking.taxes}", style_table_cell),
            Paragraph(f"&#8377;{booking.taxes}", style_table_cell)
        ])

    if booking.discount and Decimal(str(booking.discount)) > 0:
        price_rows.append([
            Paragraph("Promotional Coupon Discount Applied", style_table_cell),
            Paragraph("Promo", style_table_cell),
            Paragraph(f"-&#8377;{booking.discount}", style_table_cell),
            Paragraph(f"<font color='#16A34A'>-&#8377;{booking.discount}</font>", style_table_cell_bold)
        ])

    # Grand Total Row
    price_rows.append([
        Paragraph("<b>GRAND TOTAL PAID (ALL INCLUSIVE)</b>", style_table_cell_bold),
        Paragraph("", style_table_cell),
        Paragraph("", style_table_cell),
        Paragraph(f"<font size=10 color='#DC2626'><b>&#8377;{booking.total_amount} {booking.currency}</b></font>", style_table_cell_bold)
    ])

    price_table = Table(price_rows, colWidths=[230, 90, 95, 108])
    price_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_dark),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, -1), (-1, -1), c_light),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ]))
    elements.append(price_table)
    elements.append(Spacer(1, 10))

    # 6. Payment Transaction Reference & Security
    pay_ref_data = [
        [
            Paragraph(f"<b>Transaction Reference:</b> Razorpay Payment ID: <b>{razorpay_pid}</b> &bull; "
                      f"Razorpay Order ID: <b>{booking.razorpay_order_id or 'N/A'}</b> &bull; "
                      f"Status: <font color='#16A34A'><b>{booking.payment_status}</b></font>", style_notes)
        ]
    ]
    pay_ref_table = Table(pay_ref_data, colWidths=[523])
    pay_ref_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_light),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(pay_ref_table)
    elements.append(Spacer(1, 10))

    # 7. Important Stay Policies & Check-in Requirements
    cancellation_text = booking.hotel.cancellation_policy or "Free cancellation up to 24 hours prior to check-in."
    policy_html = (
        f"<b>IMPORTANT CHECK-IN POLICIES & NOTICES:</b><br/>"
        f"&bull; <b>Mandatory Identification:</b> All adult guests must present valid government photo ID (Aadhaar, Passport, Driving License) at check-in.<br/>"
        f"&bull; <b>Cancellation Policy:</b> {cancellation_text}<br/>"
        f"&bull; <b>House Rules:</b> {booking.hotel.rules or 'Couples welcome. Standard house rules apply.'}<br/>"
        f"&bull; <b>Assistance & Concierge:</b> Reach Book My Room 24/7 Support at support@bookmyroom.com or in your Dashboard under Support Tickets."
    )
    elements.append(Paragraph(policy_html, style_notes))
    elements.append(Spacer(1, 8))

    # 8. Footer
    footer_text = f"This is an electronically generated official confirmation receipt. Generated on {timezone.now().strftime('%d %b %Y, %I:%M %p')}. Book My Room Hospitality Network."
    elements.append(HRFlowable(width="100%", thickness=0.5, color=c_border, spaceAfter=4))
    elements.append(Paragraph(footer_text, ParagraphStyle('BMRFoot', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9, alignment=1, textColor=c_slate)))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def render_booking_email_html(booking) -> str:
    """
    Renders a responsive, modern HTML email template with Book My Room branding
    and complete reservation details.
    """
    hotel = booking.hotel
    room = booking.room
    hotel_addr = f"{hotel.address or ''}, {hotel.city or ''}, {hotel.state or ''} {hotel.zip_code or ''}".strip(', ')
    assigned_rooms = booking.room_number or 'Auto-assigned at front desk'
    captured_payment = booking.payments.filter(status='CAPTURED').first()
    razorpay_pid = captured_payment.razorpay_payment_id if captured_payment else (booking.razorpay_order_id or 'PAID-ONLINE')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Booking Confirmed - Book My Room</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px 12px; color: #0f172a; }}
  .container {{ max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
  .header {{ background: #dc2626; color: #ffffff; padding: 28px 24px; text-align: center; }}
  .header h1 {{ margin: 0 0 6px 0; font-size: 24px; font-weight: 900; letter-spacing: -0.5px; text-transform: uppercase; }}
  .header p {{ margin: 0; font-size: 13px; opacity: 0.9; font-weight: 500; }}
  .badge {{ display: inline-block; background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 800; letter-spacing: 0.5px; margin-top: 10px; }}
  .body {{ padding: 28px 24px; }}
  .greeting {{ font-size: 16px; font-weight: 700; color: #0f172a; margin-bottom: 12px; }}
  .intro {{ font-size: 13px; line-height: 1.6; color: #475569; margin-bottom: 24px; }}
  .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px; margin-bottom: 20px; }}
  .card-title {{ font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: #dc2626; margin-bottom: 12px; }}
  .detail-row {{ display: flex; justify-content: space-between; font-size: 13px; padding: 6px 0; border-bottom: 1px solid #edf2f7; }}
  .detail-row:last-child {{ border-bottom: none; }}
  .detail-label {{ color: #64748b; font-weight: 600; }}
  .detail-val {{ color: #0f172a; font-weight: 700; text-align: right; }}
  .date-grid {{ display: table; width: 100%; margin: 16px 0; text-align: center; }}
  .date-col {{ display: table-cell; width: 50%; background: #ffffff; padding: 14px; border: 1px solid #e2e8f0; border-radius: 10px; }}
  .date-col.right {{ border-left: none; }}
  .date-title {{ font-size: 11px; font-weight: 800; color: #64748b; text-transform: uppercase; }}
  .date-val {{ font-size: 15px; font-weight: 800; color: #0f172a; margin-top: 4px; }}
  .date-time {{ font-size: 11px; color: #94a3b8; margin-top: 2px; }}
  .total-row {{ background: #0f172a; color: #ffffff; border-radius: 8px; padding: 12px 16px; margin-top: 12px; }}
  .pdf-notice {{ background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 10px; padding: 14px; margin-top: 20px; font-size: 12px; color: #065f46; display: flex; align-items: center; }}
  .footer {{ background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px; text-align: center; font-size: 11px; color: #64748b; line-height: 1.5; }}
</style>
</head>
<body>
<div class="container">
  <!-- Header -->
  <div class="header">
    <h1>Book My Room</h1>
    <p>Official Reservation Confirmation</p>
    <div class="badge">BOOKING CONFIRMED &bull; PAYMENT SUCCESSFUL</div>
  </div>

  <!-- Body -->
  <div class="body">
    <div class="greeting">Hello {booking.guest_name},</div>
    <div class="intro">
      Thank you for booking with <b>Book My Room</b>! Your reservation at <b>{hotel.name}</b> is confirmed.
      We have attached your official <b>PDF Tax Invoice & Stay Voucher</b> to this email for your records.
    </div>

    <!-- Booking Reference Card -->
    <div class="card">
      <div class="card-title">Reservation Summary</div>
      <table style="width: 100%; border-collapse: collapse;">
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px; font-weight: 600;">Booking ID</td>
          <td style="padding: 6px 0; color: #dc2626; font-size: 13px; font-weight: 800; text-align: right;">{booking.booking_id}</td>
        </tr>
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px; font-weight: 600;">Hotel Property</td>
          <td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 700; text-align: right;">{hotel.name}</td>
        </tr>
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px; font-weight: 600;">Location</td>
          <td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 500; text-align: right;">{hotel_addr}</td>
        </tr>
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px; font-weight: 600;">Room Category</td>
          <td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 700; text-align: right;">{room.title if room else 'Room'} ({booking.number_of_rooms} Room)</td>
        </tr>
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px; font-weight: 600;">Room Number(s)</td>
          <td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 700; text-align: right;">{assigned_rooms}</td>
        </tr>
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px; font-weight: 600;">Guests & Meal Plan</td>
          <td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 600; text-align: right;">{booking.number_of_guests} Guests &bull; {booking.meal_plan.replace('_', ' ').title()}</td>
        </tr>
      </table>
    </div>

    <!-- Check-in / Check-out Box -->
    <div style="margin: 20px 0; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;">
      <table style="width: 100%; text-align: center;">
        <tr>
          <td style="width: 50%; border-right: 1px solid #e2e8f0; padding: 0 10px;">
            <div style="font-size: 11px; font-weight: 800; color: #64748b; text-transform: uppercase;">Check-in</div>
            <div style="font-size: 16px; font-weight: 800; color: #0f172a; margin-top: 4px;">{booking.check_in.strftime('%a, %d %b %Y')}</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">After {getattr(hotel, 'check_in_time', '12:00 PM')}</div>
          </td>
          <td style="width: 50%; padding: 0 10px;">
            <div style="font-size: 11px; font-weight: 800; color: #64748b; text-transform: uppercase;">Check-out</div>
            <div style="font-size: 16px; font-weight: 800; color: #0f172a; margin-top: 4px;">{booking.check_out.strftime('%a, %d %b %Y')}</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">Before {getattr(hotel, 'check_out_time', '11:00 AM')}</div>
          </td>
        </tr>
      </table>
      <div style="text-align: center; margin-top: 10px; font-size: 12px; font-weight: 800; color: #dc2626;">
        Stay Duration: {booking.number_of_nights} Night(s)
      </div>
    </div>

    <!-- Payment Breakdown Card -->
    <div class="card">
      <div class="card-title">Payment Summary</div>
      <table style="width: 100%; border-collapse: collapse;">
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px;">Room Charges ({booking.number_of_nights} Nights)</td>
          <td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 600; text-align: right;">₹{booking.subtotal}</td>
        </tr>
        {f'<tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 6px 0; color: #64748b; font-size: 13px;">Cleaning & Sanitization</td><td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 600; text-align: right;">₹{booking.cleaning_fee}</td></tr>' if booking.cleaning_fee and Decimal(str(booking.cleaning_fee)) > 0 else ''}
        {f'<tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 6px 0; color: #64748b; font-size: 13px;">Platform Service Fee</td><td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 600; text-align: right;">₹{booking.service_fee}</td></tr>' if booking.service_fee and Decimal(str(booking.service_fee)) > 0 else ''}
        <tr style="border-bottom: 1px solid #e2e8f0;">
          <td style="padding: 6px 0; color: #64748b; font-size: 13px;">Taxes & GST</td>
          <td style="padding: 6px 0; color: #0f172a; font-size: 13px; font-weight: 600; text-align: right;">₹{booking.taxes}</td>
        </tr>
        {f'<tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 6px 0; color: #16a34a; font-size: 13px; font-weight: 600;">Promo Coupon Discount</td><td style="padding: 6px 0; color: #16a34a; font-size: 13px; font-weight: 700; text-align: right;">-₹{booking.discount}</td></tr>' if booking.discount and Decimal(str(booking.discount)) > 0 else ''}
        <tr>
          <td style="padding: 10px 0 0 0; color: #0f172a; font-size: 15px; font-weight: 800;">Total Amount Paid</td>
          <td style="padding: 10px 0 0 0; color: #dc2626; font-size: 16px; font-weight: 900; text-align: right;">₹{booking.total_amount} {booking.currency}</td>
        </tr>
      </table>
      <div style="margin-top: 10px; font-size: 11px; color: #64748b;">
        Paid via Razorpay Online &bull; Payment ID: <code style="font-family: monospace; background: #e2e8f0; padding: 1px 4px; border-radius: 4px;">{razorpay_pid}</code>
      </div>
    </div>

    <!-- PDF Attachment Notice -->
    <div class="pdf-notice">
      <span>📄 <b>Attached Document:</b> An official PDF Invoice (<code>Booking_Confirmation_{booking.booking_id}.pdf</code>) with full property information, directions, and tax receipt is attached to this email.</span>
    </div>

    <div style="margin-top: 20px; font-size: 12px; line-height: 1.5; color: #64748b;">
      <b>Important Check-in Policy:</b> Please carry valid Government Photo ID (Aadhaar Card, Passport, Voter ID) for all guests upon arrival.<br/>
      <b>Cancellation Terms:</b> {booking.hotel.cancellation_policy or 'Free cancellation up to 24 hours prior to check-in.'}
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    Book My Room Hospitality Network &bull; Need help? Contact us at <a href="mailto:support@bookmyroom.com" style="color: #dc2626; text-decoration: none; font-weight: 700;">support@bookmyroom.com</a><br/>
    You received this email because you made a reservation on Book My Room.
  </div>
</div>
</body>
</html>"""
    return html


def send_booking_confirmation_email(booking, force_retry=False) -> dict:
    """
    Main dispatch service:
    1. Validates that the booking is in CONFIRMED status and payment is completed.
    2. Enforces idempotency (does not send duplicate confirmation emails).
    3. Generates the branded PDF voucher/tax invoice.
    4. Sends the email via configured Gmail SMTP with PDF attached.
    5. Records the delivery status, timestamp, and error tracking in the database.
    6. Ensures that if email dispatch fails, the confirmed booking remains fully confirmed.
    """
    from bookings.models import Booking, BookingEmailLog

    # Rule 1: Send only for confirmed bookings
    if booking.booking_status != Booking.STATUS_CONFIRMED:
        logger.info(
            f"[BookingEmail] Skipped email for booking {booking.booking_id} because status is {booking.booking_status} (must be CONFIRMED)."
        )
        return {
            "success": False,
            "status": "skipped",
            "message": f"Booking status is {booking.booking_status}, not CONFIRMED."
        }

    # Rule 2: Prevent duplicate confirmation emails
    if booking.confirmation_email_sent and not force_retry:
        logger.info(
            f"[BookingEmail] Booking {booking.booking_id} already has confirmation email sent on {booking.confirmation_email_sent_at}. Skipping duplicate."
        )
        return {
            "success": True,
            "status": "already_sent",
            "sent_at": booking.confirmation_email_sent_at,
            "message": "Confirmation email was already delivered previously."
        }

    # Collect valid recipient email addresses (guest and customer account)
    recipients = []
    if booking.guest_email and '@' in booking.guest_email:
        clean_guest = booking.guest_email.strip()
        if clean_guest not in recipients:
            recipients.append(clean_guest)

    if booking.customer and booking.customer.email and '@' in booking.customer.email:
        clean_cust = booking.customer.email.strip()
        if clean_cust.lower() not in [r.lower() for r in recipients]:
            recipients.append(clean_cust)

    if not recipients:
        err_msg = f"No valid recipient email found for booking {booking.booking_id}."
        logger.error(f"[BookingEmail] {err_msg}")
        booking.confirmation_email_error = err_msg
        booking.save(update_fields=['confirmation_email_error'])
        BookingEmailLog.objects.create(
            booking=booking,
            recipient_email='unknown',
            subject=f"Booking Confirmation: {booking.booking_id}",
            pdf_attached=False,
            status=BookingEmailLog.STATUS_FAILED,
            error_message=err_msg
        )
        return {"success": False, "status": "failed", "error": err_msg}

    recipient_email_str = ', '.join(recipients)
    subject = f"Booking Confirmed: {booking.hotel.name} (Booking ID: {booking.booking_id})"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or f"Book My Room <{getattr(settings, 'EMAIL_HOST_USER', 'noreply@bookmyroom.com')}>"

    try:
        # Step A: Generate PDF Voucher & Invoice
        pdf_bytes = generate_booking_pdf(booking)
        pdf_filename = f"Booking_Confirmation_{booking.booking_id}.pdf"

        # Step B: Render HTML & Text
        html_content = render_booking_email_html(booking)
        text_content = (
            f"Book My Room - Booking Confirmation\n\n"
            f"Hello {booking.guest_name},\n\n"
            f"Your reservation at {booking.hotel.name} is CONFIRMED!\n"
            f"Booking ID: {booking.booking_id}\n"
            f"Check-in: {booking.check_in}\n"
            f"Check-out: {booking.check_out} ({booking.number_of_nights} Nights)\n"
            f"Total Amount Paid: INR {booking.total_amount}\n\n"
            f"Please find your official PDF Tax Invoice and Stay Voucher attached.\n\n"
            f"Regards,\nBook My Room Team"
        )

        # Step C: Compose Email with PDF attachment
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients
        )
        email.attach_alternative(html_content, "text/html")
        email.attach(pdf_filename, pdf_bytes, "application/pdf")

        # Step D: Dispatch via Django Gmail SMTP
        email.send(fail_silently=False)

        # Step E: Record Success in Database
        booking.confirmation_email_sent = True
        booking.confirmation_email_sent_at = timezone.now()
        booking.confirmation_email_error = None
        booking.save(update_fields=[
            'confirmation_email_sent',
            'confirmation_email_sent_at',
            'confirmation_email_error'
        ])

        BookingEmailLog.objects.create(
            booking=booking,
            recipient_email=recipient_email_str,
            subject=subject,
            pdf_attached=True,
            status=BookingEmailLog.STATUS_SENT
        )

        logger.info(f"[BookingEmail] SUCCESS: Confirmation email with PDF sent to {recipient_email_str} for booking {booking.booking_id}")
        return {
            "success": True,
            "status": "sent",
            "recipient": recipient_email_str,
            "booking_id": booking.booking_id
        }

    except Exception as exc:
        err_str = str(exc)
        logger.error(f"[BookingEmail] FAILED: Could not send email for booking {booking.booking_id}: {err_str}", exc_info=True)

        # Critical: Confirmed booking remains confirmed! Only record error on email tracking.
        booking.confirmation_email_error = err_str
        booking.confirmation_email_retry_count = (booking.confirmation_email_retry_count or 0) + 1
        booking.save(update_fields=[
            'confirmation_email_error',
            'confirmation_email_retry_count'
        ])

        BookingEmailLog.objects.create(
            booking=booking,
            recipient_email=recipient_email_str,
            subject=subject,
            pdf_attached=True,
            status=BookingEmailLog.STATUS_FAILED,
            error_message=err_str
        )

        return {
            "success": False,
            "status": "failed",
            "error": err_str,
            "booking_id": booking.booking_id
        }

