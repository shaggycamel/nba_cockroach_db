ARG PYTHON_VERSION=3.11.3
FROM python:${PYTHON_VERSION} as base
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Download dependencies as a separate step to take advantage of Docker's caching.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    apt-get update \
#    && apt-get upgrade \
    && apt-get -y install libpq-dev libpq5 python3-psycopg2 libopenblas-dev libhdf5-dev libhdf5-serial-dev libatlas-base-dev gcc \
    && pip install --upgrade pip \
#    && pip install psycopg2 \
    && python -m pip install -r requirements.txt \
    && curl --create-dirs -o $HOME/.postgresql/root.crt 'https://cockroachlabs.cloud/clusters/11af18b7-ef5e-41b2-b3b7-5db438b1d403/cert'

# Copy the source code into the container.
COPY . .

# Run the application.
ENTRYPOINT ["python3", "."]