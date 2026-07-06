# Trumf (re)login — Playwright drives phone+password+SMS OTP, saves session state.
# Run interactively when the session cookie finally expires. Writes /data/trumf_state.json.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install --no-cache-dir "playwright==1.47.0"
COPY login.py /login.py
ENTRYPOINT ["python", "/login.py"]
