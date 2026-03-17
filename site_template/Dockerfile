FROM alpine:3.19 AS litestream
ARG LITESTREAM_VERSION=v0.3.13
RUN wget -q "https://github.com/benbjohnson/litestream/releases/download/${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-amd64.tar.gz" -O /tmp/litestream.tar.gz && tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin/ && rm /tmp/litestream.tar.gz

FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git sqlite3 && rm -rf /var/lib/apt/lists/*
COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN SECRET_KEY=build-only-dummy-key ENVIRONMENT=production python manage.py collectstatic --noinput
RUN chmod +x scripts/entrypoint.sh
CMD ["scripts/entrypoint.sh"]
