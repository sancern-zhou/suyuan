#!/bin/bash
# 重启后端服务器脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_PATH="${CONDA_ENV_PATH:-/root/miniconda3/envs/backend_py311}"
PYTHON_BIN="${CONDA_ENV_PATH}/bin/python"
PID_FILE="${BACKEND_PID_FILE:-/tmp/suyuan_backend.pid}"

echo "=== 重启后端服务器 ==="

if [ ! -x "${PYTHON_BIN}" ]; then
    echo "[ERROR] Python not found at ${PYTHON_BIN}"
    exit 1
fi

# 1. 先验证并准备数据库；失败时保留当前服务，避免迁移故障扩大为停机。
cd "${SCRIPT_DIR}"
echo "准备数据库..."
"${PYTHON_BIN}" -m app.db.prepare_database

# 2. 停止现有进程
echo "停止现有uvicorn进程..."
is_backend_master() {
    local candidate_pid="$1"
    local command_line
    command_line="$(ps -o args= -p "${candidate_pid}" 2>/dev/null || true)"
    [[ "${command_line}" == *"${PYTHON_BIN} -m uvicorn app.main:app"* ]]
}

stop_backend_tree() {
    local master_pid="$1"
    local process_group
    process_group="$(ps -o pgid= -p "${master_pid}" 2>/dev/null | tr -d '[:space:]')"
    if [ "${process_group}" = "${master_pid}" ]; then
        # The service is started with setsid. Signalling the whole group also
        # stops multiprocessing workers that may outlive a terminated master.
        kill -TERM -- "-${process_group}" 2>/dev/null || true
    else
        kill -TERM "${master_pid}" 2>/dev/null || true
        pkill -TERM -P "${master_pid}" 2>/dev/null || true
    fi
    for _ in $(seq 1 20); do
        if [ "${process_group}" = "${master_pid}" ]; then
            pgrep -g "${process_group}" >/dev/null 2>&1 || return 0
        elif ! kill -0 "${master_pid}" 2>/dev/null && ! pgrep -P "${master_pid}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    if [ "${process_group}" = "${master_pid}" ]; then
        kill -KILL -- "-${process_group}" 2>/dev/null || true
    else
        pkill -KILL -P "${master_pid}" 2>/dev/null || true
        kill -KILL "${master_pid}" 2>/dev/null || true
    fi
    return 0
}

if [ -f "${PID_FILE}" ]; then
    OLD_PID="$(tr -d '[:space:]' < "${PID_FILE}")"
    if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null && is_backend_master "${OLD_PID}"; then
        stop_backend_tree "${OLD_PID}"
    fi
    rm -f "${PID_FILE}"
else
    # Compatibility path for servers launched before process-group PID tracking.
    mapfile -t LEGACY_PIDS < <(pgrep -f "${PYTHON_BIN} -m uvicorn app.main:app" || true)
    for OLD_PID in "${LEGACY_PIDS[@]}"; do
        is_backend_master "${OLD_PID}" && stop_backend_tree "${OLD_PID}"
    done
fi

# 3. 启动服务器
echo "启动服务器..."
export DATABASE_SCHEMA_INIT_ON_STARTUP=false
WORKERS="${WORKERS:-4}"
# Authentication must see the raw TCP peer; Nginx owns public-client-IP logging.
nohup setsid "${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}" --env-file .env --no-proxy-headers > /tmp/backend.log 2>&1 &
NEW_PID=$!
echo "${NEW_PID}" > "${PID_FILE}"

# 4. 等待启动
for _ in $(seq 1 60); do
    if ! kill -0 "${NEW_PID}" 2>/dev/null; then
        echo "[ERROR] 后端进程启动失败，日志如下："
        tail -80 /tmp/backend.log
        exit 1
    fi
    if curl -fsS --max-time 2 http://localhost:8000/health >/dev/null; then
        break
    fi
    sleep 1
done

# 5. 检查状态
echo "=== 服务器状态 ==="
ps aux | grep "uvicorn.*app.main" | grep -v grep
echo ""
echo "测试健康检查..."
curl -fsS --max-time 3 http://localhost:8000/health

echo ""
echo "新进程PID: $NEW_PID"
echo "日志文件: /tmp/backend.log"
