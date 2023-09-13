
ARG PYTHON_VERSION=3.11.3
FROM python:${PYTHON_VERSION}-slim as base
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Download dependencies as a separate step to take advantage of Docker's caching.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    apt-get update \
    && apt-get -y install libpq-dev gcc \
    && pip install --upgrade pip \
    && pip install psycopg2 \
    && python -m pip install -r requirements.txt

# Copy the source code into the container.
COPY . .

# Run the application.
CMD python3 update_process.py
