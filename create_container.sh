#!/bin/bash
CONTAINER_NAME="s21-logins"

git pull origin main
docker rm -f $CONTAINER_NAME
docker build -t $CONTAINER_NAME .
docker run -d \
  --name $CONTAINER_NAME \
  --restart always \
  -e BASE_KEY="$BASE_KEY" \
  -e DATABASE_HOST="$DATABASE_HOST" \
  -e DATABASE_PORT="$DATABASE_PORT" \
  -e DATABASE_USERNAME="$DATABASE_USERNAME" \
  -e DATABASE_PASSWORD="$DATABASE_PASSWORD" \
  -e DATABASE_NAME="$DATABASE_NAME" \
  -e TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  -e TELEGRAM_TOKEN="$TELEGRAM_TOKEN" \
  --network=yaroslavevg \
  $CONTAINER_NAME
docker ps
docker logs -f $CONTAINER_NAME
