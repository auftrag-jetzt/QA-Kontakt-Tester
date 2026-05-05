FROM python:3.11-slim

# System dependencies required by Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Flush QA pipeline logs immediately so Coolify shows the real failing stage.
ENV PYTHONUNBUFFERED=1

# Copy everything (webhook-server/app.py imports from parent dir)
COPY . .

# Install all Python dependencies (root pipeline + webhook server)
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r webhook-server/requirements.txt

# Install Playwright's Chromium browser (required for screenshot + form testing)
RUN playwright install chromium

EXPOSE 5000

# gunicorn with threads so webhook requests return while QA keeps running.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "600", "--workers", "2", "--worker-class", "gthread", "--threads", "4", "webhook-server.app:app"]
