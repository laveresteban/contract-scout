FROM alpine:3.20

# curl + jq for the scrape script; tzdata so cron honors America/New_York.
RUN apk add --no-cache curl jq tzdata

WORKDIR /app
COPY scrape.sh entrypoint.sh ./
COPY crontab /etc/crontabs/root

RUN chmod +x scrape.sh entrypoint.sh \
    && chmod 0600 /etc/crontabs/root

ENV TZ=America/New_York \
    SCRAPE_API_BASE=http://backend:8000/api/v1

ENTRYPOINT ["/app/entrypoint.sh"]
