FROM python:3.11-alpine
RUN apk add --no-cache docker-cli git curl && \
    mkdir -p /root/.docker/cli-plugins && \
    curl -SL https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64 \
    -o /root/.docker/cli-plugins/docker-compose && \
    chmod +x /root/.docker/cli-plugins/docker-compose
RUN pip install flask
WORKDIR /app
COPY webhook.py .
EXPOSE 9000
CMD ["python", "webhook.py"]