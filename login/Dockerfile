# (Re)login images — Playwright drives the SMS-OTP OAuth flows, saves tokens/session.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install --no-cache-dir "playwright==1.47.0"
COPY *.py /login/
WORKDIR /login
ENTRYPOINT ["python"]
