FROM python:3.13-slim

WORKDIR /app

# Instala dependências avançadas de rede
RUN apt-get update && apt-get install -y \
    iputils-ping \
    net-tools \
    iproute2 \
    tcpdump \
    traceroute \
    && rm -rf /var/lib/apt/lists/*

# Copia os arquivos do router
COPY ./router/router.py .
COPY ./setup.py .

# Instala dependências Python
RUN pip install --no-cache-dir -e .

CMD ["python", "router.py"]