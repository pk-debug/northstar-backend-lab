FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NORTHSTAR_DB=/data/northstar.sqlite3
WORKDIR /service
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
COPY app ./app
USER 10001
EXPOSE 8000
# A single SQLite instance owns this volume. Use TLS termination and request
# size/rate limits at the ingress; never start multiple replicas on this file.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
