# ---- build stage: compilers + git are only needed to install deps
# (psycopg2 builds from source; sports-hub is installed from GitHub)
FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

# ---- runtime stage
FROM python:3.12-slim

# libpq5: psycopg2 runtime. tzdata: ZoneInfo (NZ / US Eastern).
# default-jre-headless: tabula-py (used by the injuries scrape) shells out to Java.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 tzdata default-jre-headless \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY __main__.py .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# credentials.ini is NOT in the image: mount it at /app/credentials.ini
# (sports-hub reads it from the working directory).
# Exec form so `docker run <image> tbl_a,tbl_b` reaches __main__.py as argv[1].
ENTRYPOINT ["python", "__main__.py"]