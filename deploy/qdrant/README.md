# 本地知识库 Qdrant

每个项目分支需要独立的本地知识库时，以稳定且唯一的项目标识作为 Compose 项目名启动。不同项目还必须分配不同端口：

```bash
LOCAL_QDRANT_PORT=6334 \
  docker compose -p suyuan-main \
  -f /home/xckj/suyuan/deploy/qdrant/docker-compose.local.yml up -d
```

并在该项目的 `backend/.env` 中设置：

```dotenv
LOCAL_QDRANT_HOST=localhost
LOCAL_QDRANT_PORT=6334
```

例如另一分支可使用 `-p suyuan-jiangsu-ops` 和 `LOCAL_QDRANT_PORT=6335`。Compose 会据此隔离容器、网络和持久化 volume。

不要将 `LOCAL_QDRANT_*` 指向共享服务。共享库使用 `SHARED_QDRANT_*`；在兼容期未设置这些变量时，服务会回退至既有的 `QDRANT_*`。

共享索引由所有管理员协作发布和维护；管理员可在任意项目分支创建、上传、修改和删除共享库。检索会并发查询共享与本地库后再统一去重、重排。

共享库的 PostgreSQL 元数据（知识库、文档、chunk、图谱）必须与共享 Qdrant 处于同一套中心数据库；否则向量命中无法完成状态校验和来源溯源。多个项目使用独立 PostgreSQL 时，应将共享知识库请求接入同一个中心服务，而不是只复用 Qdrant 地址。
