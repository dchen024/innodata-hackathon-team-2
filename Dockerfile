FROM python:3.12-slim

# tesseract: OCR for render checks. fonts-dejavu: fixed fonts so rebuilt images are byte-identical.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONHASHSEED=0 MPLBACKEND=Agg
ENTRYPOINT ["python", "-m", "factory"]
CMD ["--help"]
