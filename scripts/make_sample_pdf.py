"""Generate the sample PDF used by the demo.

The business described here (Maple Street Dental) is FICTIONAL. All names,
prices, phone numbers and addresses are made up for demonstration purposes.

The document is written as HTML and converted to PDF with LibreOffice in
headless mode:  python scripts/make_sample_pdf.py
"""

import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "sample_docs" / "maple-street-dental-guide.pdf"

PAGE_BREAK = '<p style="page-break-before: always"></p>'

PAGES = [
    """
    <h1>Maple Street Dental - Patient Guide</h1>
    <p><i>Fictional sample document created for a software demo. Not a real business.</i></p>
    <h2>1. About Us</h2>
    <p>Maple Street Dental is a family dental practice offering general, cosmetic and
    emergency dentistry for adults and children aged 3 and over. Our team includes
    three dentists, two dental hygienists and a friendly front-desk team.</p>
    <h2>2. Opening Hours</h2>
    <p>Monday to Thursday: 8:00 am - 6:00 pm.</p>
    <p>Friday: 8:00 am - 4:00 pm.</p>
    <p>Saturday: 9:00 am - 1:00 pm (hygiene and check-ups only).</p>
    <p>Sunday and public holidays: closed.</p>
    <p>Our phone line opens at 7:45 am on weekdays.</p>
    <h2>3. Location and Parking</h2>
    <p>We are located at 120 Maple Street, Springfield, on the ground floor with
    step-free access. Free parking for patients is available behind the building,
    including two accessible spaces. The number 14 bus stops directly outside.</p>
    """,
    """
    <h2>4. Services and Prices</h2>
    <p>All prices are for self-paying patients and include a consultation with the dentist.</p>
    <p>New patient exam with two X-rays: $95.</p>
    <p>Routine check-up (existing patients): $65.</p>
    <p>Scale and polish with a hygienist (30 minutes): $80.</p>
    <p>Tooth-coloured filling: from $140 per tooth.</p>
    <p>Root canal treatment: from $650, depending on the tooth.</p>
    <p>Professional teeth whitening (home kit with custom trays): $350.</p>
    <p>Children's check-up (under 16): $40.</p>
    <p>Emergency appointment: $85, plus the cost of any treatment.</p>
    <h2>5. Insurance and Payment</h2>
    <p>We accept most major dental insurance plans and can submit claims on your behalf.
    Please bring your insurance card to your first visit. We accept cash, debit and
    credit cards, and Apple Pay. For treatment over $500 we offer an interest-free
    payment plan spread over 6 months, subject to approval.</p>
    """,
    """
    <h2>6. Booking and Cancellations</h2>
    <p>You can book an appointment by phone, through the online booking form on our
    website, or at the front desk. Please arrive 10 minutes early for your first visit
    to complete a medical history form.</p>
    <p>We ask for at least 24 hours notice to cancel or reschedule. Appointments cancelled
    with less than 24 hours notice, or missed without notice, may be charged a $30 fee.</p>
    <h2>7. Dental Emergencies</h2>
    <p>If you have severe tooth pain, swelling, a knocked-out tooth or bleeding that will
    not stop, call us as early as possible. We keep same-day emergency slots every
    weekday morning. Outside opening hours, please call the out-of-hours dental line
    at 555-0199 or go to your nearest emergency department if you have facial swelling
    affecting your breathing or swallowing.</p>
    <h2>8. Frequently Asked Questions</h2>
    <p><b>Do you treat nervous patients?</b> Yes. Tell us when you book and we will allow
    extra time. We also offer numbing gel before every injection.</p>
    <p><b>Can I bring my child to my appointment?</b> Yes, children are welcome in the
    waiting area if accompanied by another adult.</p>
    <p><b>How often should I have a check-up?</b> Most adults need a check-up every 6 to
    12 months. Your dentist will recommend the right interval for you.</p>
    <h2>9. Contact</h2>
    <p>Phone: 555-0142. Email: hello@maplestreetdental.example. Address: 120 Maple Street,
    Springfield.</p>
    """,
]

STYLE = """
<style>
  body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 11pt; line-height: 1.4; }
  h1 { color: #1f5f8b; font-size: 20pt; }
  h2 { color: #1f5f8b; font-size: 14pt; margin-top: 18pt; }
</style>
"""


def build_html():
    body = PAGE_BREAK.join(PAGES)
    return f"<html><head><meta charset='utf-8'>{STYLE}</head><body>{body}</body></html>"


def main():
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise SystemExit("LibreOffice (soffice) is required to build the sample PDF.")
    with tempfile.TemporaryDirectory() as tmp:
        html_path = pathlib.Path(tmp) / "maple-street-dental-guide.html"
        html_path.write_text(build_html(), encoding="utf-8")
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf:writer_web_pdf_Export",
             "--outdir", tmp, str(html_path)],
            check=True, capture_output=True, timeout=120,
        )
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(pathlib.Path(tmp) / "maple-street-dental-guide.pdf", OUTPUT)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
