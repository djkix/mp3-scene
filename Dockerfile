FROM python:3.12-slim

ARG UID=1000
ARG GID=1000

ENV MUSIC_ROOT=/music DATA_DIR=/data PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# dépendances d'abord : cette couche n'est reconstruite que si requirements.txt change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/

# utilisateur non-root ; /data est le seul répertoire inscriptible
RUN groupadd --gid ${GID} app \
 && useradd --uid ${UID} --gid ${GID} --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data /music \
 && chown ${UID}:${GID} /data

# en dernier : changer de version ne reconstruit aucune couche
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

USER app
EXPOSE 8000
VOLUME /data

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]

# --no-proxy-headers explicite : uvicorn ne réécrit pas l'adresse du client. L'appli lit elle-même le DERNIER
# élément de X-Forwarded-For (anti-force brute) et doit voir le pair TCP réel dans les autres cas.
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
