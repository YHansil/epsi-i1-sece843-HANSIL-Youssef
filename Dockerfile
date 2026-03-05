FROM python:3.11-slim

# Installer les polices pour le CAPTCHA
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installer les dépendances Python
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code applicatif
COPY app/ .

EXPOSE 5000

CMD ["python", "app.py"]
