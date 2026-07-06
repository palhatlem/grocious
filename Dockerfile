# Fetch clients (Trumf, Rema) — browser-free (requests + saved tokens/session).
FROM python:3.12-slim
RUN pip install --no-cache-dir requests
COPY app/ /app/
WORKDIR /app
ENTRYPOINT ["python"]
