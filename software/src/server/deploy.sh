#!/bin/bash
cd /opt/sdp/software/src/server
git pull origin main
docker compose up -d --build app
