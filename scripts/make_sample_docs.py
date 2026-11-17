"""Generate the extra sample documents (DOCX and Markdown) for the demo.

Maple Street Dental is FICTIONAL: every name, price and phone number is made up.
The DOCX is written with zipfile + XML only, which also gives the tests a file
whose structure we control:  python scripts/make_sample_docs.py
"""

import pathlib
import zipfile
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_docs"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>
</w:styles>"""


def build_docx(path, paragraphs):
    """paragraphs: list of (style or None, text) or the string 'PAGE_BREAK'."""
    body = []
    for item in paragraphs:
        if item == "PAGE_BREAK":
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            continue
        style, text = item
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                + "".join(body) + "</w:body></w:document>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/document.xml", document)


AFTERCARE = [
    ("Title", "Maple Street Dental - Aftercare Sheet"),
    (None, "Fictional sample document created for a software demo. Not a real business and not medical advice."),
    ("Heading1", "After a Filling"),
    (None, "If you had a numbing injection, wait until the numbness wears off, usually 2 to 3 hours, before eating hot food or drinks."),
    (None, "Mild sensitivity to cold for a week after a new filling is common. If it lasts longer than two weeks, call the practice."),
    ("Heading1", "After a Tooth Extraction"),
    (None, "Bite gently on the gauze pad for 30 minutes. Avoid rinsing, smoking and straws for 24 hours so the blood clot can form."),
    (None, "From the second day, rinse gently with warm salt water after meals for one week."),
    "PAGE_BREAK",
    ("Heading1", "After Teeth Whitening"),
    (None, "For 48 hours after each whitening session, avoid coffee, tea, red wine and other strongly coloured food and drinks."),
    (None, "Temporary sensitivity is normal. A sensitive toothpaste helps; stop whitening for a day if it becomes uncomfortable."),
    ("Heading1", "When to Call Us"),
    (None, "Call the practice on 555-0142 if you have swelling that gets worse after two days, a fever, or bleeding that does not stop after one hour of pressure."),
]

NEW_PATIENT_FAQ = """# New Patient FAQ

*Fictional sample document created for a software demo. Not a real business.*

## What to Bring to Your First Visit

- Photo ID and your dental insurance card, if you have one.
- A list of any medicines you take.
- Your previous dentist's details, so we can request your X-rays.

## Languages Spoken

Our front-desk team speaks English and Spanish. One of our dentists also speaks Polish.
Tell us when you book if you would like an interpreter for another language.

## Accessibility

The practice is on the ground floor with step-free access and an accessible toilet.
Treatment room 1 has extra space for a wheelchair.

## Gift Vouchers

Gift vouchers for hygiene appointments and whitening are available at the front desk
in values of $50 and $100. Vouchers are valid for 12 months.
"""

TEAM_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Our Team - Maple Street Dental (demo)</title></head>
<body>
<header><nav>Home | Services | Our team</nav></header>
<main>
<h1>Our Team</h1>
<p>Fictional demo page used to show adding a website page as a chatbot source. Not a real business.</p>
<h2>Dentists</h2>
<p>Dr. Anna Kowalski is our principal dentist and leads implant and root canal treatment. She speaks Polish and English.</p>
<p>Dr. Sam Patel focuses on family dentistry and nervous patients.</p>
<p>Dr. Lucia Moreno works on Tuesdays, Thursdays and Saturdays and specialises in children's dentistry.</p>
<h2>Hygienists</h2>
<p>Our two hygienists, Tom and Grace, run the scale and polish appointments, including on Saturday mornings.</p>
</main>
<footer>Maple Street Dental (fictional)</footer>
</body></html>
"""


def main():
    OUT.mkdir(exist_ok=True)
    build_docx(OUT / "aftercare-sheet.docx", AFTERCARE)
    (OUT / "new-patient-faq.md").write_text(NEW_PATIENT_FAQ, encoding="utf-8")
    (ROOT / "static" / "site" / "team.html").write_text(TEAM_PAGE, encoding="utf-8")
    print("Wrote sample_docs/aftercare-sheet.docx, sample_docs/new-patient-faq.md, static/site/team.html")


if __name__ == "__main__":
    main()
