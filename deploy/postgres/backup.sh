#!/bin/bash
# 本机应用数据 PostgreSQL 逻辑备份（仅备份 SESSION_DATABASE_URL 承载的表）。
# crontab 示例（每天 03:10 备份，保留 14 天）：
#   10 3 * * * /home/xckj/suyuan-main/deploy/postgres/backup.sh >> /tmp/local_pg_backup.log 2>&1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
[ -f "${SCRIPT_DIR}/.env" ] && set -a && . "${SCRIPT_DIR}/.env" && set +a

BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/suyuan_app_${STAMP}.dump"

mkdir -p "${BACKUP_DIR}"

docker exec suyuan-main-local-postgres-1 \
    pg_dump -U "${LOCAL_PG_USER:-suyuan}" -d "${LOCAL_PG_DB:-suyuan_app}" -Fc \
    > "${OUT}"

if [ ! -s "${OUT}" ]; then
    echo "[ERROR] backup produced empty file: ${OUT}" >&2
    rm -f "${OUT}"
    exit 1
fi

echo "${OUT} ($(du -h "${OUT}" | cut -f1))"

# 保留最近 N 份
ls -1t "${BACKUP_DIR}"/suyuan_app_*.dump 2>/dev/null | tail -n +$((RETAIN_DAYS + 1)) | xargs -r rm -f
