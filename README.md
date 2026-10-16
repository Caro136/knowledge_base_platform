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
| 存储 | MySQL 8.0（平台数据）· Milvus（向量）· MongoDB（会话）· MinIO（内网虚拟机，原文件与图片） |
| 模型 | 云 LLM/VLM + 本地 BGE-M3 与 BGE-reranker（GPU） |
| 架构 | 单体分层（Modular Monolith），单端口对外并托管前端产物 |

## 依赖服务策略：复用宿主机既有实例

依赖服务默认**不启动容器**，由 `backend/.env` 指向宿主机既有实例：

| 服务 | 默认地址 | 来源 |
|------|---------|------|
| MySQL | 127.0.0.1:3306 | 宿主机既有实例 |
| MongoDB | 127.0.0.1:27017 | 宿主机既有实例 |
| Milvus | 127.0.0.1:19530 | 宿主机既有实例 |
| MinIO | 192.168.10.102:9000 | 内网虚拟机实例（无需容器） |

`docker/docker-compose.yml` 中的对应服务已归入 `local-stack` profile，**默认不启动**；
仅当宿主机缺少某服务、需要一套完整本地环境时才启用（此时使用备用端口 3307 / 27018 / 19531 / 8001，避免与既有服务冲突）：

```bash
docker compose -f docker/docker-compose.yml --profile local-stack up -d
```

> 对象存储使用内网虚拟机上的 MinIO 实例（地址与账号见 `backend/.env` 的 `MINIO_*`）。
> MinIO 官方镜像已从 Docker Hub 下架，故本项目 compose 中不启动该容器。
> 若需退回本地文件系统，把 `.env` 的 `STORAGE_BACKEND` 改为 `local` 即可。

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
│   │   ├── processor/        导入流程（LangGraph 图 / 节点 / 任务调度器）
│   │   ├── utils/            工具（文本切片 / 模型客户端 / MinerU 客户端）
│   │   ├── services/         领域服务（认证 / 组织权限 / 知识 / 向量 / 对象存储）
│   │   ├── routers/          接口层（认证 / 菜单 / 用户 / 角色 / 部门 / 健康检查）
│   │   ├── deps.py           依赖注入：当前用户与操作权限校验
│   │   ├── main.py           应用入口
│   │   └── seed.py           建表 + 菜单权限点 + 初始管理员
│   ├── scripts/
│   │   ├── init_mysql.sql            MySQL 建库脚本（在既有实例上执行一次）
│   │   ├── smoke_common.py           冒烟测试公共工具
│   │   ├── smoke_test_api.py         认证与组织权限冒烟测试
│   │   └── smoke_test_knowledge.py   知识台账与导入任务冒烟测试
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
    └── docker-compose.yml    依赖服务编排（默认不启动）
```

## 快速开始

### 1. 初始化数据库（在既有 MySQL 上执行一次）

```bash
mysql -h127.0.0.1 -P3306 -uroot -p < backend/scripts/init_mysql.sql
```

该脚本创建 `kb_platform` 库，并可选创建专用账号 `kb`（默认密码见脚本内注释）。

### 2. 启动后端

```bash
cd backend
cp .env.example .env        # 若尚无 .env；按实际情况填写数据库账号与模型配置

uv sync                     # 安装依赖（已配置清华镜像，见 uv.toml）
uv run python -m app.seed   # 建表 + 菜单权限点 + 初始管理员 + 演示部门/角色

uv run python -m app.main   # 启动，默认 http://127.0.0.1:8080
```

验证：

```bash
curl http://127.0.0.1:8080/healthz          # 存活探针
curl http://127.0.0.1:8080/healthz/ready    # 就绪探针（检查 MySQL）
uv run python -m scripts.smoke_test_api         # 认证与组织权限（31 项）
uv run python -m scripts.smoke_test_knowledge   # 知识台账与上传（28 项）
uv run python -m scripts.smoke_test_authz       # 数据权限鉴权（23 项）
uv run python -m scripts.smoke_test_chat        # AI 鉴权问答（22 项）
uv run python -m scripts.smoke_test_precipitation  # 知识沉淀闭环（22 项）
uv run python -m scripts.smoke_test_dashboard   # 运营看板聚合（17 项）
uv run python -m scripts.smoke_test_import      # 导入流程·直读路径（14 项）
```

接口文档：http://127.0.0.1:8080/docs

### 3. 启动前端

```bash
cd frontend
npm install                 # 已配置 npmmirror 镜像，见 .npmrc
npm run dev                 # http://127.0.0.1:5175（/api 自动代理到 8080）
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
| T-01 | 后端骨架：配置中心、统一响应、错误码、异常处理、结构化日志、健康检查 | ✅ |
| T-02 | 数据层：14 张表的 ORM 模型、建表脚本、菜单权限点与管理员种子数据 | ✅ |
| T-03 | 基础设施：docker compose（依赖服务归入 local-stack，默认复用宿主机实例） | ✅ |
| T-04 | 前端骨架：工程配置、路由守卫、布局、用户态、axios 拦截器、权限指令 | ✅ |
| T-05 | 认证：登录 / JWT 签发解析 / 当前用户信息（含权限点与菜单树） | ✅ |
| T-06 | RBAC：操作权限守卫、菜单树按权限裁剪与空目录剪除 | ✅ |
| T-07 | 组织 CRUD：部门树、用户账号、角色管理 | ✅ |
| T-08 | 角色权限分配：权限树读写（覆盖式），非法 ID 拦截 | ✅ |
| T-09 | 前端组织管理页：部门树维护、用户管理、角色管理与权限分配树 | ✅ |
| T-10 | 知识单元 CRUD：台账检索、编辑（PATCH 语义）、启停用、删除级联清理、格式清单 | ✅ |
| T-11 | 上传与任务登记：批量上传、格式白名单、对象存储落地、doc_id 与任务表 | ✅ |
| T-12 | 导入 DAG：格式路由、MinerU 云解析、图片语义化、表格线性化、按标题切片 | ✅ |
| T-13 | 向量化与入库：BGE-M3 稠密+稀疏向量、Milvus 写入、`doc_id` 锚点、幂等重建 | ✅ |
| T-16 | 动态数据权限鉴权引擎：四维 OR 判定、批量过滤、fail-closed 降级、鉴权解释 | ✅ |
| T-17 | 四维数据权限配置：权限查询与覆盖式分配（支持批量赋权） | ✅ |
| T-19 ~ T-24 | 问答链路：混合检索(RRF)、鉴权过滤、精排截断、流式生成、引用溯源、会话存储 | ✅ |
| T-14/T-15 | 前端知识管理页：台账、拖拽导入与进度、编辑删除、批量赋权入口 | ✅ |
| T-18 | 权限实体选择器组件（知识单元与 FAQ 共用） | ✅ |
| T-26 | 前端问答工作台：SSE 流式渲染、引用溯源、受限提示、多会话 | ✅ |
| T-27（埋点部分） | 问答流水落库与 Token 用量统计（按决策 D3 不记录拦截明细） | ✅ |
| T-25 / T-30 / T-31 | FAQ 挖掘与快速应答缓存：频次聚合、候选推荐、审核发布、毫秒级命中 | ✅ |
| T-32 / T-33 | 知识缺口识别（决策 D2 三条件）、清单与转建补充任务 | ✅ |
| T-34 | 前端沉淀页：FAQ 审核区 + 知识缺口清单 | ✅ |
| T-28 | 看板聚合接口：总览指标、访问趋势、高频提问榜、热门知识榜 | ✅ |
| T-29 | 前端运营看板：指标卡 + ECharts 趋势/环形图 + 排行榜 | ✅ |
| T-35 ~ T-37 | 端到端验收、安全加固与交付说明 | ⏳ |

> - **T-05~T-08**：31 项冒烟测试通过（`scripts/smoke_test_api.py`）——登录、越权拦截（20002）、
>   权限点与菜单裁剪、组织 CRUD、角色授权读写、参数校验与测试数据清理。
>   T-09 完成后，「登录 → 控制台 → 用户/角色/部门维护 → 角色权限分配」界面链路已打通。
> - **T-10/T-11**：28 项冒烟测试通过（`scripts/smoke_test_knowledge.py`）——7 类格式清单、
>   批量上传（部分成功）、MinIO 实际写入、台账与详情、编辑、导入任务查询、
>   删除级联清理（对象存储对象与权限条目均已清除）、越权拦截。
> - **T-12/T-13**：直读路径 14 项 + 解析路径 13 项冒烟测试通过
>   （`scripts/smoke_test_import.py`）——导入任务阶段推进、表格线性化、
>   稠密（1024 维）与稀疏向量入库、`doc_id` 权限锚点、知识单元状态回填、
>   删除时向量级联清理。解析路径由 MinerU 云 API 实测完成。
> - **T-16/T-17**：23 项冒烟测试通过（`scripts/smoke_test_authz.py`）——复现 PRD §2.9.9 的
>   跨部门知识隔离场景：四维 OR 判定、未配置权限默认拒绝、超管全放行、
>   覆盖式赋权**即时生效**、鉴权解释可说明「为什么看不到」、悬空实体与越权操作均被拦截。
> - **图片链路**：13 项冒烟测试通过（`scripts/smoke_test_import.py --sample-image`）——
>   图片经视觉模型生成中文描述后入库，图片知识可被文本检索命中（决策 D1 闭环）。
> - **T-19~T-24**：22 项冒烟测试通过（`scripts/smoke_test_chat.py`）——混合检索与 RRF 融合、
>   鉴权过滤（置于重排之前）、精排与断崖截断、SSE 流式生成（实测 88 个正文增量）、
>   引用溯源、多轮会话、会话隔离；**越权防护**三连验证：回答不含受限数值、
>   引用不含受限文档、无任何有权内容时返回权限受限提示且**不调用大模型**。
> - **前端（T-14/T-15/T-18/T-26）**：构建通过，三个页面已接入真实接口。
>   前端无自动化测试，**交互需按下节清单人工验证**。

### 前端手动验证清单

```bash
# 终端 A
cd backend && uv run python -m app.main
# 终端 B
cd frontend && npm run dev        # 打开 http://127.0.0.1:5175
```

1. 用 `admin` 登录 → 侧边栏出现全部菜单；
2. **知识管理** → 「导入文档」抽屉 → 拖入一个 Markdown/PDF → 观察进度条逐阶段推进至「处理完成」；
3. 选中该知识单元 → 「数据权限」→ 勾选部门/角色/个人 → 保存 → 台账的权限标签应即时更新；
4. 用另一个账号登录 → 侧边栏与按钮应只保留被授权的项；
5. **智能问答** → 就知识库内的内容提问 → 应看到流式输出与「引用来源」列表（悬浮可看切片摘录）；
6. 向无权限的账号提问受限话题 → 应出现黄色权限受限提示，且不产生正文；
7. **FAQ 沉淀** → 反复提问同一问题达到阈值（默认 5 次）→ 「FAQ 审核」应出现自动生成的候选 →
   编辑答案并发布 → 再问同一问题应**秒回**且无流式过程；
8. **知识缺口** → 提一个知识库完全没覆盖的问题 → 「知识缺口」应出现该问题与频次 →
   「转建补充任务」应生成任务并从待处理清单中移除；
9. **运营看板** → 提几个问题后回到看板 → 访问次数、Token 消耗、趋势折线、高频提问榜
   应随刚才的操作增长（数据源是问答流水，非模拟数据）。

### 模型服务验证

```bash
# 直读路径（不依赖外部服务）
uv run python -m scripts.smoke_test_import

# 解析路径：现场生成 .docx 样本，走 MinerU 云解析
uv run python -m scripts.smoke_test_import --sample-docx

# 解析路径：指定本地文件
uv run python -m scripts.smoke_test_import --file <文件路径>
```

## 已实现接口

| 方法 | 路径 | 权限点 | 说明 |
|------|------|--------|------|
| POST | `/api/auth/login` | 公开 | 登录，返回 token 与用户信息 |
| GET | `/api/auth/me` | 登录 | 当前用户信息（含 perms / menus） |
| POST | `/api/auth/logout` | 登录 | 登出（前端清除凭证） |
| GET | `/api/menu/mine` | 登录 | 当前用户菜单树 |
| GET | `/api/menu/tree` | `role:perm` | 全量菜单树（含按钮） |
| GET | `/api/dept/tree` | `dept:list` 等 | 部门树 |
| POST/PUT/DELETE | `/api/dept[/{id}]` | `dept:create/update/delete` | 部门维护 |
| GET | `/api/user/list` | `user:list` 等 | 用户列表（分页） |
| POST/PUT/DELETE | `/api/user[/{id}]` | `user:create/update/delete` | 用户维护 |
| GET | `/api/role/list` | `role:list` 等 | 角色列表 |
| POST/PUT/DELETE | `/api/role[/{id}]` | `role:create/update/delete` | 角色维护 |
| GET/PUT | `/api/role/{id}/menus` | `role:perm` | 角色权限分配（覆盖式） |
| GET | `/api/knowledge/supported-formats` | `knowledge:*` | 支持的 7 类文档格式与扩展名 |
| POST | `/api/knowledge/upload` | `knowledge:import` | 批量上传（multipart，返回 accepted / rejected） |
| GET | `/api/knowledge/status/{task_id}` | `knowledge:*` | 导入任务阶段与状态 |
| GET | `/api/knowledge/list` | `knowledge:list` 等 | 知识单元台账（分页、多条件筛选、含权限摘要） |
| GET/PUT/DELETE | `/api/knowledge/{doc_id}` | `knowledge:query/update/delete` | 详情 / 编辑（PATCH 语义）/ 删除（级联清理） |
| GET | `/api/knowledge/{doc_id}/assets/{name}` | `knowledge:*` | 知识单元图片资源（答案配图，返回图片流） |
| POST | `/api/chat/query` | `ai:chat` | 发起问答，返回 task_id（生成过程经 SSE 推送） |
| GET | `/api/chat/stream/{task_id}` | `ai:chat` | SSE 流：stage / delta / references / notice / done |
| GET | `/api/chat/sessions` | `ai:chat` | 当前用户的会话列表 |
| GET/DELETE | `/api/chat/history/{session_id}` | `ai:chat` | 会话消息历史 / 删除会话 |
| GET | `/api/precipitation/faq/list` | `faq:list` | 候选与已发布 FAQ 列表 |
| GET | `/api/precipitation/faq/published` | `ai:chat` | 已发布 FAQ（对话台常见问题） |
| PUT | `/api/precipitation/faq/{id}/audit` | `faq:audit` | 审核发布 / 驳回 |
| DELETE | `/api/precipitation/faq/{id}` | `faq:delete` | 删除 FAQ（不再命中缓存） |
| GET/POST | `/api/precipitation/faq/{id}/perms`、`/faq/perms/assign` | `faq:audit` | FAQ 数据权限（清空即公开） |
| GET | `/api/precipitation/gap/list` | `gap:list` | 知识缺口清单 |
| PUT | `/api/precipitation/gap/{id}/resolve` | `gap:handle` | 标记缺口已解决 |
| POST | `/api/precipitation/gap/{id}/task` | `gap:handle` | 缺口转建知识补充任务 |
| GET | `/api/dashboard/overview` | `dashboard:view` | 总览：PV/UV、知识单元、Token、延时、命中率、缺口数 |
| GET | `/api/dashboard/trend` | `dashboard:view` | 访问趋势（按天 PV / UV） |
| GET | `/api/dashboard/top-questions` | `dashboard:view` | 高频提问排行 |
| GET | `/api/dashboard/top-docs` | `dashboard:view` | 热门知识单元排行 |
| GET | `/healthz`、`/healthz/ready` | 公开 | 健康检查 |

## 关键约定

- **统一响应**：除 SSE 与文件流外，接口一律返回 `{ code, message, data }`，`code === 0` 为成功；
  字段对外输出 camelCase（内部 snake_case）。
- **错误码段位**：`100xx` 参数校验 · `200xx` 认证权限 · `300xx` 业务规则 · `400xx` 依赖系统。
- **鉴权**：除登录接口外均需 `Authorization: Bearer <token>`；操作权限以后端校验为准，前端指令仅作展示收敛。
- **数据权限**：知识单元默认无任何权限（拒绝优先），切片缺失 `doc_id` 锚点一律拒绝。
- **密钥管理**：`.env` 不入版本库；生产环境必须替换 `JWT_SECRET` 与初始管理员口令。

## 待确认事项

PRD §11 与 SPEC §11 列出了仍需业务方确认的事项，其中亟待处理的：

1. ~~视觉模型配置~~ **已解决**：`VLM_MODEL` 已切换为专属实例上的 `qwen3-vl-plus`，
   图片语义化链路实测通过（见 T-12/T-13 验证）。
2. 嵌入与重排运行在 **CPU**（已确认）：宿主机 PyTorch 为 CPU 构建。
   如需启用 GPU 加速，先安装 CUDA 版 PyTorch，再把 `BGE_DEVICE` 改为 `cuda:0`、`BGE_FP16=1`。
3. 非功能指标（并发、知识库规模、响应时长目标）。
4. 「切片调整」的交互粒度（是否需要切片级编辑并写回向量库）。

## 许可证

仅供学习与内部使用。
