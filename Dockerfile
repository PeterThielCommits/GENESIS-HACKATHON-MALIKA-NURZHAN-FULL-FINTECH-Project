# TwinLedger offline verification image (Master TZ §22.4).
#
# Reproducibility contract (TZ 22.4: "pin the base image digest, the Python
# patch version, the package versions and the commands"):
#   * BASE_IMAGE is pinned BY DIGEST, so the userland never changes under us.
#   * The image writes its own provenance record (base digest, the exact
#     CPython patch version, the Debian release and the versions of the two
#     Debian packages it installs) to /usr/local/share/twinledger/build_info.json.
#   * `configs/docker_build_info.json` records the same values for the
#     published image; `python3 tools/docker_build_info.py verify` checks that
#     the two agree, and `... resolve` reports whether the upstream tag moved.
#   * The Debian packages are resolved by apt at build time (vendoring is not
#     permitted by TZ 22.3); their versions are recorded and drift is reported
#     instead of breaking the build. See docs/LIMITATIONS.md (L11).
ARG BASE_IMAGE="python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b"

FROM ${BASE_IMAGE}

ARG BASE_IMAGE

LABEL org.opencontainers.image.title="TwinLedger offline verification image" \
      org.opencontainers.image.description="Deterministic offline verification image for the Genesis FinTech 2026-11-20 TwinLedger benchmark" \
      org.opencontainers.image.base.name="${BASE_IMAGE}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="TwinLedger"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INDEX=1

# `make` drives the single documented verification command; `util-linux`
# provides `unshare`/`setpriv`, which the kernel-level sandbox profile
# (harness/ns_launcher.py, TZ 16.2) needs inside the container.
RUN apt-get update && apt-get install -y --no-install-recommends make util-linux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Ensure non-root user, pre-compile bytecode before read-only runtime, pre-create report dirs (TZ 22.4)
RUN python3 -m compileall -q judge_adapter.py core contracts adapter gen invariants verifier nlp env harness scoring seal arena metamorphic judge tools tests independent_verifier \
    && useradd --create-home --uid 10001 twinledger \
    && mkdir -p /app/artifacts/reports/latest /app/artifacts/reports/doc_claims /app/artifacts/trajectories \
    && chown -R twinledger:twinledger /app \
    && chmod 1777 /app/artifacts/reports/latest /app/artifacts/reports/doc_claims /app/artifacts/trajectories \
    && mkdir -p /usr/local/share/twinledger \
    && python3 tools/docker_build_info.py emit --base-image "${BASE_IMAGE}" --out /usr/local/share/twinledger/build_info.json \
    && chmod 0444 /usr/local/share/twinledger/build_info.json

USER 10001:10001

# Single-command offline verification (stdlib only, no network, no downloads)
CMD ["make", "verify"]
