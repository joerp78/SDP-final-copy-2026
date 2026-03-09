#!/bin/bash
cd /opt/sdp
git pull origin main
docker compose up -d --build app