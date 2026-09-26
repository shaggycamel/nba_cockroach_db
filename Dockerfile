# ---- build stage: compilers + git are only needed to install deps
# (psycopg2 builds from source; sports-hub is installed from GitHub)
FROM python:3.12-slim AS build

# Pinned to the uv that generated uv.lock, so the image can't be tripped up by a
# lock-format change in a newer release. Bump together with the lock.
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /usr/local/bin/uv

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# No glob on uv.lock: a missing lock must fail the build, not silently re-resolve.
COPY pyproject.toml uv.lock ./
# --locked fails if the lock is out of date with pyproject, rather than updating it.
RUN uv sync --no-dev --no-install-project --locked

# ---- runtime stage
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/shaggycamel/nba_cockroach_db"
LABEL org.opencontainers.image.description="Scheduled NBA/fantasy table updates from util.update_schedule"

# libpq5: psycopg2 runtime (sports-hub pins psycopg2, which has no Linux wheels).
# tzdata: ZoneInfo('Pacific/Auckland').
# default-jre-headless: nbainjuries starts a JVM via jpype at import time, and
#   sports_hub.nba imports it at module top, so Java is needed on every run.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 tzdata default-jre-headless \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY __main__.py .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Runs as root on purpose: credentials.ini is bind-mounted read-only from a chmod 600
# host file, which a non-root uid in the container could not read.
#
# credentials.ini is NOT in the image: mount it at /app/credentials.ini
# (sports-hub and __main__.py both read it from the working directory).
# Exec form so `docker run <image> tbl_a,tbl_b` reaches __main__.py as argv[1].
ENTRYPOINT ["python", "__main__.py"]
