# Imagen mínima para el servidor MCP de hipercampo.
FROM python:3.13-slim

WORKDIR /app

# Dependencias primero (mejor cache de capas)
COPY pyproject.toml README.md ./
COPY hipercampo ./hipercampo

RUN pip install --no-cache-dir .

# La memoria persiste en el volumen /data (ver docker-compose.yml)
ENV HIPERCAMPO_DB=/data/hipercampo.db
VOLUME ["/data"]

# MCP habla por stdio: mantener STDIN abierto con `docker run -i`.
ENTRYPOINT ["python", "-m", "hipercampo.server"]
