#!/bin/bash
# 重启后端服务器脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_PATH="${CONDA_ENV_PATH:-/root/.codex/miniconda3/envs/backend_py311}"
PYTHON_BIN="${CONDA_ENV_PATH}/bin/python"
PID_FILE="${BACKEND_PID_FILE:-/tmp/suyuan_backend.pid}"

echo "=== 重启后端服务器 ==="

if [ ! -x "${PYTHON_BIN}" ]; then
    echo "[ERROR] Python not found at ${PYTHON_BIN}"
    exit 1
fi

# 1. 先验证持久化目录，再准备数据库；失败时保留当前服务。
cd "${SCRIPT_DIR}"
"${PYTHON_BIN}" -m app.utils.deployment_preflight --env-file .env
echo "准备数据库..."
"${PYTHON_BIN}" -m app.db.prepare_database

# 2. 停止现有进程
echo "停止现有uvicorn进程..."
is_backend_master() {
    local candidate_pid="$1"
    local command_line
    local candidate_cwd
    command_line="$(ps -o args= -p "${candidate_pid}" 2>/dev/null || true)"
    candidate_cwd="$(readlink -f "/proc/${candidate_pid}/cwd" 2>/dev/null || true)"
    [[ "${candidate_cwd}" = "${SCRIPT_DIR}" ]] &&
        [[ "${command_line}" == *"${PYTHON_BIN} -m uvicorn app.main:app"* ]] &&
        [[ "${command_line}" == *"--port 8000"* ]] &&
        [[ "${command_line}" == *"--env-file .env"* ]]
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

STARTED=false
WEB_UNIT="${WEB_UNIT:-}"

is_backend_listener_ready() {
    local master_pid="$1"
    local listener_pid
    local listener_pgid

    if ! command -v ss >/dev/null 2>&1; then
        curl -fsS --max-time 2 http://localhost:8000/health >/dev/null
        return
    fi

    while read -r listener_pid; do
        listener_pgid="$(ps -o pgid= -p "${listener_pid}" 2>/dev/null | tr -d '[:space:]')"
        if [ "${listener_pgid}" = "${master_pid}" ]; then
            return 0
        fi
    done < <(
        ss -H -ltnp 'sport = :8000' 2>/dev/null |
            grep -oE 'pid=[0-9]+' |
            cut -d= -f2 |
            sort -u
    )
    return 1
}

resolve_web_unit() {
    local unit
    if [ -n "${WEB_UNIT}" ]; then
        systemctl cat "${WEB_UNIT}" >/dev/null 2>&1 && { echo "${WEB_UNIT}"; return 0; }
        return 1
    fi
    for unit in suyuan-web.service suyuan-backend-web.service; do
        systemctl cat "${unit}" >/dev/null 2>&1 && { echo "${unit}"; return 0; }
    done
    return 1
}

web_unit_owns_port() {
    local main_pid port_pid
    main_pid="$(systemctl show "$1" -p MainPID --value)"
    [ -n "${main_pid}" ] && [ "${main_pid}" != "0" ] || return 1
    command -v ss >/dev/null 2>&1 || return 0
    port_pid="$(ss -H -ltnp 'sport = :8000' 2>/dev/null |
        grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u | grep -x "${main_pid}" | head -1)"
    [ -n "${port_pid}" ]
}

# 仅清理属于当前部署目录的残留 uvicorn 进程（排除 systemd 主进程与其他工作树，如江苏 8001）
kill_stale_web_processes() {
    local unit_main_pid="$1" candidate_pid candidate_cwd
    [ -n "${unit_main_pid}" ] || unit_main_pid="0"
    while read -r candidate_pid; do
        [ -n "${candidate_pid}" ] || continue
        [ "${candidate_pid}" = "${unit_main_pid}" ] && continue
        candidate_cwd="$(readlink -f "/proc/${candidate_pid}/cwd" 2>/dev/null || true)"
        [ "${candidate_cwd}" = "${SCRIPT_DIR}" ] || continue
        echo "清理残留 web 进程: ${candidate_pid}"
        kill -TERM "${candidate_pid}" 2>/dev/null || true
    done < <(pgrep -f "${PYTHON_BIN} -m uvicorn app.main:app" 2>/dev/null || true)
}

if command -v systemctl >/dev/null 2>&1 && WEB_UNIT_RESOLVED="$(resolve_web_unit)"; then
    echo "检测到 web systemd 单元 ${WEB_UNIT_RESOLVED}..."
    systemctl stop "${WEB_UNIT_RESOLVED}" || true
    WEB_UNIT_MAIN_PID="$(systemctl show "${WEB_UNIT_RESOLVED}" -p MainPID --value)"
    kill_stale_web_processes "${WEB_UNIT_MAIN_PID}"
    sleep 2
    systemctl start "${WEB_UNIT_RESOLVED}"
    # 本机全量工具注册约需 2 分钟；以健康检查+服务活性为准，端口归属作为附加确认
    for _ in $(seq 1 180); do
        if curl -fsS --max-time 2 http://localhost:8000/health >/dev/null 2>&1 &&
           web_unit_owns_port "${WEB_UNIT_RESOLVED}"; then
            STARTED=true
            break
        fi
        systemctl is-active --quiet "${WEB_UNIT_RESOLVED}" || break
        sleep 1
    done
    systemctl is-active "${WEB_UNIT_RESOLVED}" >/dev/null || {
        echo "[ERROR] web 服务未恢复运行："
        journalctl -u "${WEB_UNIT_RESOLVED}" -n 50 --no-pager || true
        exit 1
    }
    if [ "${STARTED}" != true ] && curl -fsS --max-time 3 http://localhost:8000/health >/dev/null 2>&1; then
        STARTED=true
        echo "[WARNING] web 健康检查通过，但未能确认 8000 端口由 ${WEB_UNIT_RESOLVED} 主进程持有，请人工核对。"
    fi
    NEW_PID="$(systemctl show "${WEB_UNIT_RESOLVED}" -p MainPID --value)"
else
    # 无 systemd 单元时的传统启动路径
    if [ -f "${PID_FILE}" ]; then
        OLD_PID="$(tr -d '[:space:]' < "${PID_FILE}")"
        if [[ "${OLD_PID}" =~ ^[0-9]+$ ]] && kill -0 "${OLD_PID}" 2>/dev/null && is_backend_master "${OLD_PID}"; then
            stop_backend_tree "${OLD_PID}"
        elif [ -n "${OLD_PID}" ]; then
            echo "[WARNING] 忽略失效或不属于当前部署的PID文件: ${OLD_PID}"
        fi
        rm -f "${PID_FILE}"
    fi

    # PID文件可能缺失、过期或只记录了其中一个实例，因此始终扫描实际进程。
    # 工作目录和启动参数校验会排除其他工作树（例如江苏 8001）。
    mapfile -t RUNNING_PIDS < <(pgrep -f "${PYTHON_BIN} -m uvicorn app.main:app" || true)
    for OLD_PID in "${RUNNING_PIDS[@]}"; do
        is_backend_master "${OLD_PID}" && stop_backend_tree "${OLD_PID}"
    done

    echo "启动服务器..."
    export DATABASE_SCHEMA_INIT_ON_STARTUP=false
    WORKERS="${WORKERS:-1}"
    # Authentication must see the raw TCP peer; Nginx owns public-client-IP logging.
    nohup setsid "${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}" --env-file .env --no-proxy-headers > /tmp/backend.log 2>&1 &
    NEW_PID=$!
    echo "${NEW_PID}" > "${PID_FILE}"

    # 等待启动（本机全量工具注册约需 2 分钟）
    for _ in $(seq 1 180); do
        if ! kill -0 "${NEW_PID}" 2>/dev/null; then
            echo "[ERROR] 后端进程启动失败，日志如下："
            tail -80 /tmp/backend.log
            exit 1
        fi
        if is_backend_listener_ready "${NEW_PID}" && curl -fsS --max-time 2 http://localhost:8000/health >/dev/null; then
            STARTED=true
            break
        fi
        sleep 1
    done
fi

# 5. 重启 app worker（fetcher 调度器运行在 worker 进程内）
echo ""
echo "=== 重启 app worker ==="
WORKER_UNIT="${WORKER_UNIT:-}"
WORKER_PID_FILE="${WORKER_PID_FILE:-/tmp/suyuan_backend_worker.pid}"
# worker 内部端口由部署决定（许昌 8011），用于确认端口最终归属服务主进程
WORKER_HEALTH_PORT="${WORKER_HEALTH_PORT:-8011}"

# 自动探测本机真实的 worker systemd 单元名（历史上默认名与实际部署名不一致，
# 导致探测失败后走 nohup 孤儿进程路径、与 systemd 实例抢占内部端口）
resolve_worker_unit() {
    local unit
    if [ -n "${WORKER_UNIT}" ]; then
        systemctl cat "${WORKER_UNIT}" >/dev/null 2>&1 && { echo "${WORKER_UNIT}"; return 0; }
        return 1
    fi
    for unit in suyuan-worker.service suyuan-app-worker.service suyuan-backend-worker.service; do
        systemctl cat "${unit}" >/dev/null 2>&1 && { echo "${unit}"; return 0; }
    done
    return 1
}

worker_unit_owns_port() {
    local main_pid port_pid
    main_pid="$(systemctl show "$1" -p MainPID --value)"
    [ -n "${main_pid}" ] && [ "${main_pid}" != "0" ] || return 1
    command -v ss >/dev/null 2>&1 || return 0
    port_pid="$(ss -H -ltnp "sport = :${WORKER_HEALTH_PORT}" 2>/dev/null |
        grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u | grep -x "${main_pid}" | head -1)"
    [ -n "${port_pid}" ]
}

# 仅清理属于当前部署目录的残留 worker（排除 systemd 主进程与其他工作树，如江苏 8001/8012）
kill_stale_worker_processes() {
    local unit_main_pid="$1" candidate_pid candidate_cwd
    [ -n "${unit_main_pid}" ] || unit_main_pid="0"
    while read -r candidate_pid; do
        [ -n "${candidate_pid}" ] || continue
        [ "${candidate_pid}" = "${unit_main_pid}" ] && continue
        candidate_cwd="$(readlink -f "/proc/${candidate_pid}/cwd" 2>/dev/null || true)"
        [ "${candidate_cwd}" = "${SCRIPT_DIR}" ] || continue
        echo "清理残留 worker 进程: ${candidate_pid}"
        kill -TERM "${candidate_pid}" 2>/dev/null || true
    done < <(pgrep -f "${PYTHON_BIN} -m app\.worker" 2>/dev/null || true)
}

if command -v systemctl >/dev/null 2>&1 && WORKER_UNIT_RESOLVED="$(resolve_worker_unit)"; then
    echo "检测到 worker systemd 单元 ${WORKER_UNIT_RESOLVED}..."
    systemctl stop "${WORKER_UNIT_RESOLVED}" || true
    UNIT_MAIN_PID="$(systemctl show "${WORKER_UNIT_RESOLVED}" -p MainPID --value)"
    kill_stale_worker_processes "${UNIT_MAIN_PID}"
    sleep 2
    systemctl start "${WORKER_UNIT_RESOLVED}"
    # worker 启动需加载全量工具后才监听内部端口；确认端口最终由服务主进程持有，
    # 防止历史遗留的孤儿进程抢占导致 systemd 实例反复绑定失败
    WORKER_PORT_READY=false
    for _ in $(seq 1 150); do
        if worker_unit_owns_port "${WORKER_UNIT_RESOLVED}"; then
            WORKER_PORT_READY=true
            break
        fi
        systemctl is-active --quiet "${WORKER_UNIT_RESOLVED}" || break
        sleep 1
    done
    systemctl is-active "${WORKER_UNIT_RESOLVED}" >/dev/null || {
        echo "[ERROR] worker 服务未恢复运行："
        journalctl -u "${WORKER_UNIT_RESOLVED}" -n 50 --no-pager || true
        exit 1
    }
    if [ "${WORKER_PORT_READY}" = true ]; then
        echo "worker 内部端口 ${WORKER_HEALTH_PORT} 已由 ${WORKER_UNIT_RESOLVED} 主进程接管。"
    else
        echo "[WARNING] 未确认 ${WORKER_UNIT_RESOLVED} 主进程持有端口 ${WORKER_HEALTH_PORT}（启动较慢或端口配置不同），请人工检查。"
    fi
else
    echo "未找到 worker systemd 单元，直接后台启动 worker..."
    if [ -f "${WORKER_PID_FILE}" ]; then
        OLD_WORKER_PID="$(tr -d '[:space:]' < "${WORKER_PID_FILE}")"
        if [ -n "${OLD_WORKER_PID}" ] && kill -0 "${OLD_WORKER_PID}" 2>/dev/null; then
            kill -TERM "${OLD_WORKER_PID}" 2>/dev/null || true
            for _ in $(seq 1 20); do
                kill -0 "${OLD_WORKER_PID}" 2>/dev/null || break
                sleep 0.5
            done
            kill -KILL "${OLD_WORKER_PID}" 2>/dev/null || true
        fi
        rm -f "${WORKER_PID_FILE}"
    fi
    pkill -TERM -f "${PYTHON_BIN} -m app\.worker" 2>/dev/null || true
    sleep 2
    nohup setsid env APP_ROLE=worker "${PYTHON_BIN}" -m app.worker > /tmp/backend-worker.log 2>&1 &
    NEW_WORKER_PID=$!
    echo "${NEW_WORKER_PID}" > "${WORKER_PID_FILE}"
    echo "worker PID: ${NEW_WORKER_PID}，日志: /tmp/backend-worker.log"
fi

if [ "${STARTED}" != true ]; then
    echo "[ERROR] 新后端进程未在规定时间内接管8000端口，日志如下："
    tail -80 /tmp/backend.log
    exit 1
fi

# 6. 检查状态
echo "=== 服务器状态 ==="
ps aux | grep "uvicorn.*app.main" | grep -v grep
echo ""
echo "测试健康检查..."
curl -fsS --max-time 3 http://localhost:8000/health

echo ""
echo "新进程PID: $NEW_PID"
echo "日志文件: /tmp/backend.log"
