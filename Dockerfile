FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip ffmpeg webp && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://github.com/aldinokemal/go-whatsapp-web-multidevice/releases/download/v9.7.0/whatsapp_9.7.0_linux_amd64.zip -o /tmp/gowa.zip \
 && echo '8ec1fa8636db9b0f988dff09f61dead07cacc58cde1dfed820b8b5826f6e3933  /tmp/gowa.zip' | sha256sum -c - \
 && unzip -j /tmp/gowa.zip linux-amd64 -d /usr/local/bin \
 && mv /usr/local/bin/linux-amd64 /usr/local/bin/whatsapp \
 && chmod +x /usr/local/bin/whatsapp && rm /tmp/gowa.zip
# The gateway cuts every request at 45 s. A group send encrypts for each member's phone; after a restart (keys
# not rebuilt yet) a big group takes longer, fails with "cipher encryption failed", keeps nothing, and fails
# again every time. Raise that one limit to 300 s: the 8-byte value at this offset of the pinned binary above.
RUN python3 -c "import struct,pathlib; p=pathlib.Path('/usr/local/bin/whatsapp'); b=bytearray(p.read_bytes()); o=0xC7E423; assert b[o:o+8]==struct.pack('<q',45*10**9), 'gateway changed: update this offset'; b[o:o+8]=struct.pack('<q',300*10**9); p.write_bytes(b)"
WORKDIR /app/studio
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data/studio TZ=Asia/Karachi
EXPOSE 10000
CMD ["python", "launcher.py"]
