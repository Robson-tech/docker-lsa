FROM python:3.13-slim

WORKDIR /app

# Instala dependências de rede e Python
RUN apt-get update && apt-get install -y \
    iputils-ping \
    net-tools \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Copia os arquivos do host
COPY ./host/host.py .
COPY ./setup.py .

# Instala dependências Python
RUN pip install --no-cache-dir -e .

CMD ["python", "host.py"]