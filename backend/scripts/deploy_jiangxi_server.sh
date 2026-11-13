#!/usr/bin/env bash
# 江西噪声部署机一键更新：同步代码 -> 预检 -> 成对重启 web/worker -> 端口确认
#
# 同步来源二选一：
#   --remote hub                       服务器可达 GitLab（推荐，日常增量）
#   --bundle /path/to/inc.bundle       离线兜底：本地生成的增量 bundle
#
# 常用参数：
#   --branch project/jiangxi-noise     同步分支（默认同左）
#   --force-reset                      硬同步到远端 tip（丢弃服务器上对已跟踪文件的本地改动；
#                                      .env/backend_data_registry 等未跟踪内容不受影响）
#   --skip-restart                     只同步+预检，不重启
#   --python /path/to/python           后端解释器（默认取 BACKEND_PYTHON 环境变量或 python）
#   --web-port 8000                    web 端口（端口确认用）
#
# 示例：
#   deploy_jiangxi_server.sh --remote hub
#   deploy_jiangxi_server.sh --bundle /tmp/inc.bundle --force-reset
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BRANCH="project/jiangxi-noise"
MODE="" REMOTE="hub" BUNDLE="" FORCE=0 SKIP_RESTART=0 WEB_PORT=8000
BACKEND_PYTHON="${BACKEND_PYTHON:-python}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) MODE="remote"; REMOTE="$2"; shift 2 ;;
    --bundle) MODE="bundle"; BUNDLE="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --force-reset) FORCE=1; shift ;;
    --skip-restart) SKIP_RESTART=1; shift ;;
    --python) BACKEND_PYTHON="$2"; shift 2 ;;
    --web-port) WEB_PORT="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

[ -n "$MODE" ] || { echo "必须指定 --remote 或 --bundle"; exit 1; }
cd "$REPO_ROOT"

CURRENT="$(git branch --show-current)"
[ "$CURRENT" = "$BRANCH" ] || { echo "当前分支 $CURRENT != $BRANCH，请先 git checkout $BRANCH"; exit 1; }

echo "== 1/4 同步代码 =="
if [ "$MODE" = "remote" ]; then
  git fetch "$REMOTE" "$BRANCH"
  if [ "$FORCE" = "1" ]; then
    git reset --hard "$REMOTE/$BRANCH"
  else
    git pull --ff-only "$REMOTE" "$BRANCH" \
      || { echo "存在分叉（服务器上有对已跟踪文件的本地改动）。" \
             "确认无保留价值后加 --force-reset 重跑；有保留价值则先提交到 deploy/* 分支推回 GitLab。"; exit 1; }
  fi
else
  [ -f "$BUNDLE" ] || { echo "bundle 不存在: $BUNDLE"; exit 1; }
  git fetch "$BUNDLE" "$BRANCH:refs/remotes/bundle/$BRANCH"
  if [ "$FORCE" = "1" ]; then
    git reset --hard "refs/remotes/bundle/$BRANCH"
  else
    git merge --ff-only "refs/remotes/bundle/$BRANCH" \
      || { echo "无法快进，确认后加 --force-reset 重跑。"; exit 1; }
  fi
fi
echo "当前版本: $(git log --oneline -1)"

echo "== 2/4 部署预检 =="
(cd backend && "$BACKEND_PYTHON" -m app.utils.deployment_preflight --env-file .env)

if [ "$SKIP_RESTART" = "1" ]; then
  echo "== 跳过重启 =="
else
  echo "== 3/4 重启 web + worker（成对） =="
  for pidfile in /tmp/suyuan-web.pid /tmp/suyuan-worker.pid; do
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      kill "$(cat "$pidfile")" && echo "已停止 $(basename "$pidfile"): $(cat "$pidfile")"
    fi
  done
  sleep 2
  cd backend
  nohup setsid "$BACKEND_PYTHON" -m uvicorn app.main:app \
    --host 0.0.0.0 --port "$WEB_PORT" --workers 1 --env-file .env --no-proxy-headers \
    > /tmp/suyuan-web.log 2>&1 < /dev/null &
  echo $! > /tmp/suyuan-web.pid
  nohup setsid "$BACKEND_PYTHON" -m app.worker \
    > /tmp/suyuan-worker.log 2>&1 < /dev/null &
  echo $! > /tmp/suyuan-worker.pid
  sleep 3
  echo "== 4/4 端口确认 =="
  ss -ltnp | grep -E ":$WEB_PORT " || { echo "✗ web 端口未监听，查 /tmp/suyuan-web.log"; exit 1; }
  ss -ltnp | grep -E "app.worker|python.*worker" >/dev/null \
    || { echo "✗ worker 未运行，查 /tmp/suyuan-worker.log"; exit 1; }
  cd "$REPO_ROOT"
fi

echo "完成。可选：平台接口发版探测"
echo "  cd backend && $BACKEND_PYTHON scripts/probe_jiangxi_noise_apis.py --env-file .env"
