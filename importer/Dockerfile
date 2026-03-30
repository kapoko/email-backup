FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      tzdata \
      python3 \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY run-sync.sh /usr/local/bin/run-sync.sh
COPY oauth-token.py /usr/local/bin/oauth-token.py
COPY gmail-import.py /usr/local/bin/gmail-import.py

RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/run-sync.sh /usr/local/bin/oauth-token.py /usr/local/bin/gmail-import.py

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
