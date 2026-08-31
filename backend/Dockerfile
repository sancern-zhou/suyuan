# Backend Dockerfile - FastAPI Application
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Keep this list aligned with system-dependencies.yml. LibreOffice on Debian
# provides headless mode through the regular component packages (there is no
# separate libreoffice-headless package in Debian bookworm).
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    fonts-liberation \
    fonts-noto-cjk \
    gnupg \
    jq \
    libreoffice-calc \
    libreoffice-impress \
    libreoffice-writer \
    libmagic1 \
    librsvg2-bin \
    nodejs \
    npm \
    poppler-utils \
    unixodbc \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install the Chromium binary and native libraries used by the Python browser
# tools. The editable-PPT Node runtime reuses this Playwright browser cache.
RUN python -m playwright install --with-deps chromium

# Copy application code
COPY . .

# Install the isolated editable-PPT compiler runtime without downloading a
# second Chromium copy.
ENV PUPPETEER_SKIP_DOWNLOAD=true
RUN npm ci --omit=dev --prefix /app/app/tools/office/editable_ppt_runtime

# Quarto is required by the report renderer; pin the version documented and
# validated by this repository.
ARG QUARTO_VERSION=1.8.25
RUN curl -fsSL \
      "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.deb" \
      -o /tmp/quarto.deb \
    && apt-get update \
    && apt-get install -y /tmp/quarto.deb \
    && rm -f /tmp/quarto.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /app/static /app/database /app/config

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application with production settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
