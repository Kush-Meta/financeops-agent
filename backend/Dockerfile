FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY eval ./eval
COPY tests ./tests
COPY data ./data

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV DATABASE_URL=sqlite:////data/financeops.db

RUN mkdir -p /data /app/data/documents

EXPOSE 8765
CMD ["sh", "-c", "python -m app.scripts.seed && uvicorn app.main:app --host 0.0.0.0 --port 8765"]
