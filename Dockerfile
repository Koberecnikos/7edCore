# 7edCore - web panel + 7 Days to Die dedicated servers (SteamCMD)
FROM ubuntu:24.04
ARG VERSION=dev
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl tzdata lib32gcc-s1 lib32stdc++6 libc6:i386 \
        python3 python3-aiohttp python3-psutil tar zstd procps util-linux \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/steamcmd \
    && curl -fsSL https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz | tar -xz -C /opt/steamcmd \
    && chown -R 1000:1000 /opt/steamcmd
COPY --chown=1000:1000 app /app
USER 1000:1000
ENV HOME=/data/home DATA_DIR=/data STEAMCMD=/opt/steamcmd/steamcmd.sh PANEL_PORT=8120 \
    SEVENEDCORE_VERSION=${VERSION} SEVENEDCORE_REPO=Koberecnikos/7edCore PYTHONUNBUFFERED=1
WORKDIR /app
VOLUME /data
EXPOSE 8120 26900-26939/tcp 26900-26939/udp 8080-8083
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s CMD curl -fs http://127.0.0.1:8120/api/session >/dev/null || exit 1
LABEL org.opencontainers.image.title="7edCore" \
      org.opencontainers.image.description="Web panel for 7 Days to Die dedicated servers" \
      org.opencontainers.image.source="https://github.com/Koberecnikos/7edCore"
CMD ["python3", "/app/main.py"]
