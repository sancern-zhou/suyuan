#!/usr/bin/env bash
# 本机发布：构建前端 -> 推送分支到同步枢纽 -> 产出服务器需要的传输件
#
# 用法（Git Bash，在仓库任意目录执行）：
#   release_jiangxi_package.sh                        # 完整发布：push + dist 构建打包
#   release_jiangxi_package.sh --skip-dist            # 纯后端改动：只 push，不打 dist
#   release_jiangxi_package.sh --base <sha>           # 附加增量 git bundle（服务器离线兜底用）
#   release_jiangxi_package.sh --out /d/suyuan-deploy-packages
#
# 产出（默认 D:/suyuan-deploy-packages/）：
#   frontend-dist-<sha>.tar.gz      服务器解压到 frontend/dist 后按 DEPLOY.md 验收
#   suyuan-jiangxi-inc-<base>-<sha>.bundle   --base 时的增量对象包（几 MB 级）
#
# 日常同步约定：
#   本机改动 -> git push zhousc project/jiangxi-noise（本脚本已含）
#   服务器   -> bash backend/scripts/deploy_jiangxi_server.sh --remote hub
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH="project/jiangxi-noise"
HUB="zhousc"
OUT="D:/suyuan-deploy-packages"
BASE=""
SKIP_DIST=0
SKIP_PUSH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --skip-dist) SKIP_DIST=1; shift ;;
    --skip-push) SKIP_PUSH=1; shift ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

cd "$REPO_ROOT"
SHA="$(git rev-parse --short=10 "$BRANCH")"
mkdir -p "$OUT"

if [ "$SKIP_PUSH" = "0" ]; then
  echo "== 1/3 推送 $BRANCH -> $HUB =="
  git push "$HUB" "$BRANCH"
else
  echo "== 1/3 跳过推送 =="
fi

if [ "$SKIP_DIST" = "0" ]; then
  echo "== 2/3 构建前端 dist =="
  (cd frontend && npm run build:standalone) >/dev/null 2>&1 \
    && echo "dist 构建完成" || { echo "dist 构建失败"; exit 1; }
  DIST_TAR="$OUT/frontend-dist-$SHA.tar.gz"
  tar -czf "$DIST_TAR" -C frontend dist
  echo "产出: $DIST_TAR ($(du -h "$DIST_TAR" | cut -f1))"
  echo "服务器发布: tar -xzf $(basename "$DIST_TAR") -C <代码根>/frontend"
else
  echo "== 2/3 跳过 dist =="
fi

if [ -n "$BASE" ]; then
  echo "== 3/3 生成增量 bundle（$BASE..$SHA） =="
  BUNDLE="$OUT/suyuan-jiangxi-inc-$BASE-$SHA.bundle"
  git -c core.autocrlf=false bundle create "$BUNDLE" "$BASE..$BRANCH"
  echo "产出: $BUNDLE ($(du -h "$BUNDLE" | cut -f1))"
  echo "服务器: bash backend/scripts/deploy_jiangxi_server.sh --bundle $(basename "$BUNDLE")"
else
  echo "== 3/3 未指定 --base，跳过 bundle =="
fi

echo "完成。服务器侧日常命令：bash backend/scripts/deploy_jiangxi_server.sh --remote hub"
