# Imagem única: API + painéis + ferramentas OSINT de linha de comando.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# exiftool = leitura de EXIF dos anexos; curl/ca-certificates = download do phoneinfoga
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ferramentas OSINT. Instaladas em camada separada porque são pesadas e
# mudam pouco — mantém o rebuild rápido no free tier.
RUN pip install --no-cache-dir "holehe==1.61" "maigret==0.5.0a1" || \
    pip install --no-cache-dir holehe maigret

# theHarvester puxa muita dependência; se o build falhar o conector apenas
# aparece como indisponível, sem derrubar a imagem.
RUN pip install --no-cache-dir theHarvester \
    || echo "AVISO: theHarvester nao instalado; o conector ficara indisponivel"

# phoneinfoga (binário Go, ~10 MB)
RUN curl -fsSL https://raw.githubusercontent.com/sundowndev/phoneinfoga/master/support/scripts/install \
      -o /tmp/install-phoneinfoga.sh \
    && sh /tmp/install-phoneinfoga.sh \
    && mv ./phoneinfoga /usr/local/bin/phoneinfoga \
    && chmod +x /usr/local/bin/phoneinfoga \
    && rm -f /tmp/install-phoneinfoga.sh \
    || echo "AVISO: phoneinfoga nao instalado; o conector ficara indisponivel"

COPY app ./app
COPY db  ./db
COPY web ./web

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
