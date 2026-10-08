FROM python:3.8-slim-bookworm

# tzdata so TZ gives local detection times; libusb is loaded by tflite_support at import
RUN apt-get update && apt-get install -y --no-install-recommends tzdata libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY model.tflite birdnames.db ./
COPY *.py ./
COPY static/ ./static/

CMD ["python", "./speciesid.py"]
