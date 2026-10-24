FROM python:3.12.14-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    APP_ENV=production DEBUG=false EXPOSE_VERIFICATION_TOKEN_IN_RESPONSE=false \
    PORT=8000 FORWARDED_ALLOW_IPS=127.0.0.1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && python -m app.db.seed && exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
