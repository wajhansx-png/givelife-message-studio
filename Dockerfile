FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip ffmpeg webp && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://github.com/aldinokemal/go-whatsapp-web-multidevice/releases/download/v9.7.0/whatsapp_9.7.0_linux_amd64.zip -o /tmp/gowa.zip \
 && echo '8ec1fa8636db9b0f988dff09f61dead07cacc58cde1dfed820b8b5826f6e3933  /tmp/gowa.zip' | sha256sum -c - \
 && unzip -j /tmp/gowa.zip -d /usr/local/bin \
 && chmod +x /usr/local/bin/whatsapp && rm /tmp/gowa.zip
WORKDIR /app/studio
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data/studio TZ=Asia/Karachi
EXPOSE 10000
CMD ["python", "launcher.py"]
