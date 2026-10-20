#!/bin/bash
cd /root/suyuan/backend || exit 1
WEATHER_BACKFILL_WORKERS=3 nohup setsid /opt/miniconda3/envs/backend_py311/bin/python scripts/fetch_surrounding_weather_2026.py > /tmp/weather_backfill_2026.log 2>&1 < /dev/null &
echo "launched pid=$!"
