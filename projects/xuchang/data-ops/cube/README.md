# xuchang-cube — 许昌数据语义层（Cube Core 0.35）

指标口径的**唯一定义与对外供数 API**。上游是 DataCrawler MySQL 采集表
（`SsfbCity*` / `SsfbSite*` / `SsfbCityRanking`，由 suyan fetcher 直接抓取维护，
无独立 sync/ODS 层），下游是智能体（`xuchang_cube_metrics` 工具点数查询）。

```
河南实时发布系统 ──suyuan fetchers(每小时/每日)──▶ DataCrawler MySQL
                                                    │
                                    本目录 schema/*.js（口径唯一定义）
                                                    ▼
                                    Cube REST http://127.0.0.1:4610（docker）
```

## 已建模

- **SsfbCityHour / SsfbCityDay**：18 城市组（含济源）小时/日六参数+AQI
- **SsfbCityRanking**：月/年累计排名（HJ663 重算，升序并列，官方对照列）
- **SsfbSiteHour / SsfbSiteDay**：许昌县级站（县/区归属，剔除国控）

口径细则见各 schema 文件头注释；与 fetcher 采集逻辑一致由测试守卫
（`tests/fetchers/test_xuchang_henan_ranking_recalc.py` 等）。

## 部署（宿主机 docker）

```bash
cd /root/suyuan/projects/xuchang/data-ops/cube
docker pull cubejs/cube:v0.35.81

# 凭据不进 git：从 backend/.env 读取生成运行时 env（模板见 .env.example）
CRAWLER_MYSQL_PASSWORD=$(grep CRAWLER_MYSQL_PASSWORD /root/suyuan/backend/.env | cut -d= -f2)
CUBEJS_API_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 64)
cat > /data/docker/xuchang-cube.env <<EOF
CUBEJS_DB_TYPE=mysql
CUBEJS_DB_HOST=172.17.0.1
CUBEJS_DB_PORT=13307
CUBEJS_DB_NAME=DataCrawler
CUBEJS_DB_USER=root
CUBEJS_DB_PASS=$CRAWLER_MYSQL_PASSWORD
CUBEJS_API_SECRET=$CUBEJS_API_SECRET
CUBEJS_CACHE_AND_QUEUE_DRIVER=memory
CUBEJS_WEB_SOCKETS=false
EOF

docker run -d --name suyan-xuchang-cube --restart unless-stopped \
  -p 127.0.0.1:4610:4000 \
  -v /root/suyuan/projects/xuchang/data-ops/cube/schema:/cube/conf/model:ro \
  --env-file /data/docker/xuchang-cube.env \
  cubejs/cube:v0.35.81
```

- 只监听 127.0.0.1（消费方都在本机）；production 模式强制 JWT
- 连库账号与采集工具同权限（root/本地回环），语义层不引入新权限
- `CUBEJS_CACHE_AND_QUEUE_DRIVER=memory` 必须（0.35 默认 cubestore 在容器内不可持久）

## 查询方法

```bash
# JWT: HS256, payload {"type":"standard"} 与 CUBEJS_API_SECRET 签名
# Agent 侧由 xuchang_cube_metrics 工具自动签发
curl -X POST http://127.0.0.1:4610/cubejs-api/v1/load \
  -H "Authorization: <JWT>" -H "Content-Type: application/json" \
  -d '{"query":{"measures":["SsfbCityRanking.rankZong","SsfbCityRanking.avgZong"],
       "dimensions":["SsfbCityRanking.city"],
       "filters":["SsfbCityRanking.period = 2026-10","SsfbCityRanking.periodType = monthly"]}}'
```

## 修改口径的正确姿势

1. 改 fetcher 采集/重算逻辑（`backend/app/fetchers/xuchang_henan_ssfb_publish.py`、
   `xuchang_henan_ranking_recalc.py`）
2. 同步改本目录 `schema/*.js`（口径注释与字段映射）
3. `docker restart suyan-xuchang-cube`
