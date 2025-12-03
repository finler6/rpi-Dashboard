FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    curl \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
COPY *.py ./
COPY known_hosts .

RUN mkdir -p downloads && chmod 777 downloads

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONHTTPSVERIFY=0
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

ENV INSTAGRAM_USERNAME=""
ENV INSTAGRAM_PASSWORD=""

RUN update-ca-certificates

CMD ["python", "main.py"]
