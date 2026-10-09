# syntax=docker/dockerfile:1
# E3-D0 uses a pinned Python 3.12 base and a separate build stage so the
# runtime contains no build tools, virtual environments, or local secrets.
FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build

COPY requirements.lock pyproject.toml README.md ./
RUN python -m pip install --prefix=/install -r requirements.lock

COPY src ./src
RUN python -m pip install --prefix=/install --no-deps .

FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN groupadd --gid 10001 incubia \
    && useradd --uid 10001 --gid incubia --create-home --home-dir /home/incubia --shell /usr/sbin/nologin incubia

COPY --from=build /install /usr/local
WORKDIR /app
COPY --chown=incubia:incubia src ./src
COPY --chown=incubia:incubia config ./config
COPY --chown=incubia:incubia migrations ./migrations

USER 10001:10001
EXPOSE 8080

CMD ["python", "-m", "incubia_orchestrator.interfaces.http.main", "--host", "0.0.0.0", "--port", "8080"]
