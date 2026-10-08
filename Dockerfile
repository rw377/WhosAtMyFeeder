FROM python:3.8-slim-bookworm

# tzdata so the TZ environment variable gives local detection times
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY model.tflite birdnames.db ./
COPY *.py ./
COPY static/ ./static/

CMD ["python", "./speciesid.py"]
