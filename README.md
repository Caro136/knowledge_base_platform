# 知识库管理平台

集**知识多源维护、四维细粒度权限鉴权、AI 鉴权检索问答、数据运营看板、知识自动沉淀**于一体的企业知识库管理平台。

- 产品需求：[`docs/知识库管理平台PRD.md`](docs/知识库管理平台PRD.md)（v0.2）
- 技术设计：[`docs/知识库管理平台技术设计规格SPEC.md`](docs/知识库管理平台技术设计规格SPEC.md)（v0.1）
- 原始要求：[`docs/知识库管理平台项目要求.md`](docs/知识库管理平台项目要求.md)

## 技术栈（已锁定）

| 层 | 选型 |
|----|------|
| 前端 | Vue 3 + Vite + Element Plus + Pinia + Vue Router + ECharts |
| 后端 | Python 3.12 + FastAPI + LangGraph 工作流 |
| 存储 | MySQL 8.0（平台数据）· Milvus 2.5（向量）· MongoDB 7.0（会话）· MinIO（文件） |
| 模型 | 云 LLM/VLM + 本地 BGE-M3 与 BGE-reranker（GPU） |
| 架构 | 单体分层（Modular Monolith），单端口对外并托管前端产物 |

## 目录结构

```
knowledge_base_platform/
├── docs/                     需求、PRD、技术设计规格
├── backend/                  后端服务（FastAPI）
│   ├── app/
│   │   ├── core/             配置中心 / 错误码 / 统一响应 / 异常 / 日志 / 安全工具
│   │   ├── db/               声明基类、会话管理、建表工具
│   │   ├── models/           ORM 模型（权限域 / 知识域 / 运营沉淀域）
│   │   ├── schemas/          Pydantic 请求响应模型
│   │   ├── routers/          接口层（注册入口 + 健康检查）
│   │   ├── main.py           应用入口
│   │   └── seed.py           建表 + 菜单权限点 + 初始管理员
│   ├── uv.toml               包索引（国内镜像）
│   └── .env.example          环境变量模板
├── frontend/                 前端控制台（Vue3）
│   ├── src/
│   │   ├── api/              axios 实例与接口定义
│   │   ├── router/           路由与访问守卫
│   │   ├── store/            Pinia 状态（用户登录态）
│   │   ├── directives/       按钮级权限指令
│   │   ├── layout/           侧边栏 + 顶栏布局
│   │   ├── components/       通用组件
│   │   └── views/            业务页面
│   └── .npmrc                npm 国内镜像
└── docker/
    └── docker-compose.yml    依赖服务编排（MySQL/MongoDB/Milvus/MinIO）
```

## 快速开始

### 1. 启动依赖服务

```bash
cd docker
docker compose up -d
docker compose ps          # 等待 mysql 与 milvus 变为 healthy
```

> 拉取镜像缓慢时，请为 Docker Desktop 配置国内镜像加速。
> 本机已有 MySQL/MongoDB 实例时，可只启动 `milvus` 与 `minio`，并修改 `.env` 连接地址。

#### 端口占用处理

默认端口：`8080` 应用 · `3306` MySQL · `27017` MongoDB · `19530/9091` Milvus · `9000/9001` MinIO · `8000` Attu。

若与既有服务冲突（例如本机已安装 MySQL 占用 3306），二选一：

1. **复用既有服务**：不启动对应容器，仅把 `backend/.env` 中的连接地址指向既有实例；
2. **改用其他端口**：修改 `docker/docker-compose.yml` 的端口映射，并同步修改 `backend/.env`
   （例如 MySQL 改为 `3307:3306`，则 `MYSQL_PORT=3307`）。

### 2. 启动后端

```bash
cd backend
cp .env.example .env        # 按需修改数据库口令、JWT_SECRET、模型配置

uv sync                     # 安装依赖（已配置清华镜像，见 uv.toml）
uv run python -m app.seed   # 建表 + 菜单权限点 + 初始管理员

uv run python -m app.main   # 启动，默认 http://127.0.0.1:8080
```

验证：

```bash
curl http://127.0.0.1:8080/healthz          # 存活探针
curl http://127.0.0.1:8080/healthz/ready    # 就绪探针（检查 MySQL）
```

接口文档：http://127.0.0.1:8080/docs

### 3. 启动前端

```bash
cd frontend
npm install                 # 已配置 npmmirror 镜像，见 .npmrc
npm run dev                 # http://127.0.0.1:5173（/api 自动代理到 8080）
```

生产构建后由后端直接托管：

```bash
cd frontend && npm run build
# 产物 frontend/dist 由后端按 .env 的 STATIC_DIR 托管，访问 http://127.0.0.1:8080/
```

默认管理员账号见 `backend/.env` 的 `INIT_ADMIN_USERNAME` / `INIT_ADMIN_PASSWORD`。

## 当前进度

| 任务 | 内容 | 状态 |
|------|------|------|
| T-01 | 后端骨架：配置中心、统一响应、错误码、异常处理、结构化日志、健康检查 | ✅ 已完成 |
| T-02 | 数据层：全部 ORM 模型、建表脚本、菜单权限点与管理员种子数据 | ✅ 已完成 |
| T-03 | 基础设施：docker compose（MySQL/MongoDB/Milvus/MinIO/Attu） | ✅ 已完成 |
| T-04 | 前端骨架：工程配置、路由守卫、布局、用户态、axios 拦截器、权限指令 | ✅ 已完成 |
| T-05 ~ T-37 | 认证、RBAC、知识导入解析、鉴权引擎、问答、看板、知识沉淀、端到端交付 | ⏳ 待开发 |

> 骨架阶段说明：登录页可正常打开，但 `/api/auth/login` 等业务接口 **尚未实现**（属 T-05 范围），
> 点击登录会收到后端的 404 响应，这是预期行为。

## 已完成部分的验证方式

```bash
# 后端
cd backend && uv run python -c "import app.main; print('应用可导入')"
uv run python -m app.main            # 启动后访问 /healthz 与 /docs

# 前端
cd frontend && npm run build         # 构建通过则骨架无误
```

## 关键约定

- **统一响应**：除 SSE 与文件流外，接口一律返回 `{ code, message, data }`，`code === 0` 为成功。
- **错误码段位**：`100xx` 参数校验 · `200xx` 认证权限 · `300xx` 业务规则 · `400xx` 依赖系统。
- **鉴权**：除登录接口外均需 `Authorization: Bearer <token>`；操作权限以后端校验为准，前端指令仅作展示收敛。
- **数据权限**：知识单元默认无任何权限（拒绝优先），切片缺失 `doc_id` 锚点一律拒绝。
- **密钥管理**：`.env` 不入版本库；生产环境必须替换 `JWT_SECRET` 与初始管理员口令。

## 待确认事项

PRD §11 与 SPEC §11 列出了仍需业务方确认的事项，其中影响架构的三项：

1. LLM / VLM 供应商与文档解析服务选型，以及**内网是否允许出网**
2. 非功能指标（并发、知识库规模、响应时长目标）
3. 「切片调整」的交互粒度（是否需要切片级编辑并写回向量库）

## 许可证

仅供学习与内部使用。
