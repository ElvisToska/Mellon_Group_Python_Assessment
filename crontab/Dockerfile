
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir SQLAlchemy PyMySQL

COPY db ./db
COPY crontab ./crontab

RUN crontab ./crontab/clear_decommission.cron

CMD ["sh", "-c", "printenv > /etc/environment && cron -f"]
