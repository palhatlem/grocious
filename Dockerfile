# Trumf fetch client — browser-free (uses the saved NextAuth session cookie).
FROM python:3.12-slim
RUN pip install --no-cache-dir requests
COPY app/ /app/
WORKDIR /app
ENTRYPOINT ["python", "trumf_client.py"]
