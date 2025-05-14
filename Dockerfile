FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    iproute2 \
    smartmontools \
    git \
    curl \
    openssh-client

RUN curl -fsSL https://download.docker.com/linux/static/stable/$(uname -m)/docker-24.0.6.tgz | tar xz && \
    mv docker/* /usr/bin/

RUN mkdir -p /usr/libexec/docker/cli-plugins && \
    curl -SL https://github.com/docker/compose/releases/download/v2.20.2/docker-compose-linux-$(uname -m) \
    -o /usr/libexec/docker/cli-plugins/docker-compose && \
    chmod +x /usr/libexec/docker/cli-plugins/docker-compose

WORKDIR /app

COPY . .

RUN git config --global user.name "FinlerBot" \
 && git config --global user.email "bot@finler.local"

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
