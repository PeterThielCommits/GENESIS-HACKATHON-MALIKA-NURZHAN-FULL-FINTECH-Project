# TwinLedger offline verification image (TZ 22.4).
# Reproducible as far as the base image allows; pin digest in release.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY . /app

# Non-root user (TZ 22.4)
RUN useradd --create-home --uid 10001 twinledger && chown -R twinledger:twinledger /app
USER twinledger

# Offline smoke: core verification only (stdlib, no network, no installs)
CMD ["make", "verify-core"]
