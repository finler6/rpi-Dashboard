FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    iproute2 \
    smartmontools \
    git \
    openssh-client \
    docker.io

WORKDIR /app

COPY . .

RUN git config --global user.name "FinlerBot" \
 && git config --global user.email "bot@finler.local"

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
