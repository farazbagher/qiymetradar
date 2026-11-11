FROM python:3.12-slim

# Tesseract OCR (Azərbaycan + ingilis) və Azərbaycan hərflərini (ə, ı, ş...) göstərən şrift
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-aze tesseract-ocr-eng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY app ./app
COPY demoshop ./demoshop

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
