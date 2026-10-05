FROM python:3.12-slim
WORKDIR /app
COPY . .
CMD ["sh", "-c", "pip install -q -e '.[dev]' && python -m pyflakes src tests && python -m pytest -q"]
