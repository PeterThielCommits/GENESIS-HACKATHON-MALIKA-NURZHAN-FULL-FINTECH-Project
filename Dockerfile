# TwinLedger offline verification image (Master TZ §22.4).
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INDEX=1

RUN apt-get update && apt-get install -y --no-install-recommends make util-linux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Ensure non-root user, pre-compile bytecode before read-only runtime, and pre-create report dirs (TZ §22.4)
RUN python3 -m compileall -q judge_adapter.py core contracts adapter gen invariants verifier nlp env harness scoring seal arena metamorphic judge tools tests \
    && useradd --create-home --uid 10001 twinledger \
    && mkdir -p /app/artifacts/reports/latest /app/artifacts/trajectories \
    && chown -R twinledger:twinledger /app \
    && chmod 1777 /app/artifacts/reports/latest /app/artifacts/trajectories

USER 10001:10001

# Single-command offline verification (stdlib only, no network, no downloads)
CMD ["make", "verify"]
