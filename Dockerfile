# Document chatbot: python -m app.server on port 8000
FROM python:3.12-slim

# pdftotext (poppler-utils) reads PDF files
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY sample_docs ./sample_docs

RUN useradd --create-home bot && mkdir -p /app/data && chown bot /app/data
USER bot

ENV HOST=0.0.0.0 PORT=8000 DATA_DIR=/app/data PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=4)"
CMD ["python", "-m", "app.server"]
