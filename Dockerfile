FROM python:3.11-slim

WORKDIR /app

# pyproject.toml uses setuptools, which needs the package source present
# to resolve `app*`, so copy code before installing.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
