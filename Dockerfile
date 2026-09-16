FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY app app
COPY alembic alembic
COPY alembic.ini ./
RUN uv sync --frozen

ENV PATH="/srv/.venv/bin:$PATH"

EXPOSE 8000
