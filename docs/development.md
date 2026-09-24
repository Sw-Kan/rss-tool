# 开发流程

## 环境

- Node ≥ 20（已验证 24.19.0）、Python ≥ 3.11（已验证 3.12.3）
- pnpm：`corepack enable pnpm`
- 后端依赖装在 `backend/.venv`，用 **uv** 创建与安装（系统缺 `python3-venv` 时 pip 建不了 venv）

## 首次启动

```bash
make setup          # uv 建 venv + 装后端依赖 + pnpm install
make dev            # 后端 :8000 + 前端 :5173
```

打开 http://localhost:5173 。首次可用登录页的「跳过，以 user 身份进入」直接进入。

## Docker

```bash
make up        # 构建并启动，浏览器打开 http://localhost:8080
make down      # 停止（保留数据卷）
docker compose down -v   # 连数据卷一起删，等于恢复出厂
docker compose logs -f backend
```

- 前端由 nginx 提供静态文件，并把 `/api` 反代到后端的 8000（cookie 必须同源，所以不能只发布后端端口）。
- 后端只在内网监听，宿主只暴露 **8080**；要改端口用 `WEB_PORT=9000 make up`。
- 数据放 named volume `rss-tool_rss-data`（`/data`：`rss.db`、`secret.key`、`uploads/`）。`secret.key` 一起持久化，所以**容器重启后登录状态不丢**。
- 容器内默认 `ALLOW_PRIVATE_FETCH=false`。要塞进自建 RSSHub 或局域网源，用
  `ALLOW_PRIVATE_FETCH=true make up`（compose 里已透传这个变量）。
- 两个构建上下文各自带 `.dockerignore`：尤其前端必须排除 `node_modules`，否则
  `COPY . .` 会把宿主机的二进制覆盖进镜像。

## 数据库

`backend/data/rss.db`（自动创建）。**无迁移**：改表结构就删库重建：

```bash
make db-reset       # 删除 rss.db 与 uploads/，下次启动重建
```

数据与上传文件都在 `backend/data/`，删除该目录即清空全部本地数据。

## 调试

| 场景 | 做法 |
|---|---|
| 看 API 文档 | http://localhost:8000/docs |
| 单独调某个源 | `curl -X POST localhost:8000/api/feeds/{id}/refresh`（需 cookie） |
| 前端绕过代理直连 | `frontend/.env.local` 里设 `VITE_API_BASE=http://localhost:8000` |
| 看调度器是否在跑 | 后端日志里的 `scheduler: user ... 每 N 分钟刷新` |
| 加自建 RSSHub / 局域网源 | 设 `ALLOW_PRIVATE_FETCH=true` 后重启后端；默认会被 SSRF 防护拒绝 |
| 看全文抽取效果 | 库里查：`sqlite3 backend/data/rss.db "select extract_status,content_source,count(*) from articles group by 1,2"` |
| 关掉全文抽取 | 设 `EXTRACT_ENABLED=false`（调试抓取管线时用） |
| 本机 RSSHub | `docker start rsshub`；容器内用 `http://rsshub:1200`，宿主用 `http://127.0.0.1:1200`，两者都需要 `ALLOW_PRIVATE_FETCH=true` |
| 看自动化是否触发 | 后端日志 `automation: 规则「…」跳过/动作失败`；库里 `user_item_state` 看收藏与已读 |
| 看代理是否生效 | 设置 → 代理 → 测试连接；返回里会写明「经由 …」或「跟随系统」 |
| 看图片缓存 | `du -sh backend/data/media`；库里 `select status,count(*),sum(bytes) from media_cache group by 1` |
| 关掉图片缓存 | 设 `MEDIA_CACHE_ENABLED=false`（图片交回浏览器直连） |
| 看服务器时区 | `docker compose exec backend date`；定时规则的 HH:MM 按它解释 |
| 看定时规则是否在跑 | 后端日志 `scheduler: 定时规则 tick 已注册；当前服务器时间 …` |
| 不花钱验证 AI 链路 | 起个假上游（见下），供应商填 `http://127.0.0.1:8977/v1` |
| 看 AI 用量 | `sqlite3 backend/data/rss.db "select kind,sum(tokens_in+tokens_out) from ai_results group by 1"` |

## 测试

```bash
make test       # pytest + vitest
make lint       # ruff + eslint
make typecheck  # tsc --noEmit
```

抓取相关测试用 `respx` 拦截，不打真实网络。

## 手工验收清单

对应各模块的验收标准，发布前逐条走一遍。

- [ ] 登录页点「跳过」→ 进入阅读器，侧边栏底部显示 `user` / `example@example.com`
- [ ] 注册新账号 → 数据与 `user` 完全隔离（看不到对方的已读与订阅）
- [ ] 设置 → 订阅源 → 添加一个 RSS 源 → 侧边栏出现其 logo 与名称
- [ ] 目录刷新后列表出现文章；**再次刷新**不产生重复且已读/收藏保持
- [ ] 加一个坏源（如 `http://localhost:8000/nope`）→ 只该源报错，其它源正常
- [ ] 一级过滤：全部 / 文章 / 图片 / 视频 切换结果正确
- [ ] 收藏 ⊕ 视频 = 只有收藏的视频；目录 ⊕ 图片 = 只有该目录内图片源的图片
- [ ] 拖拽侧边栏与列表分隔条后刷新页面，宽度保持
- [ ] 图片页 6 列瀑布流无重叠；视频页宽屏每行 5 个；滚到底自动加载下一页
- [ ] 标记已读 / 收藏后刷新保持；批量已读后未读计数下降
- [ ] 正文里的 `<script>` 不执行（用一条含 script 的测试 feed 验证）
- [ ] 某源只给摘要（RSSHub 之类）时，刷新后正文被补成原网页全文；该源再刷新一次不会退回摘要
- [ ] 原网页抓取失败（404/超时）时保留 feed 摘要，且下轮刷新不再反复请求同一页面
- [ ] 导出 OPML 能被第三方阅读器导入，且目录层级保留
- [ ] 上传 >3MB 或改名的文本文件当头像 → 被拒；首字母头像 5 色可切换
- [ ] 主题切深色后刷新保持；刷新间隔改为 5 分钟后调度器按新间隔触发
- [ ] 导出我的数据（JSON）可被 `jq` 解析且含已读/收藏记录
- [ ] 设置 → AI：添加供应商、填地址/Key/模型、关掉开关后「AI 总结」按钮变灰
- [ ] 阅读一篇文章点「AI 总结」出结果；再点一次不再产生上游请求（库里 `ai_results` 只有一行）
- [ ] 「标题翻译」显示在原文标题下方；刷新页面后两者都还在（走 `/api/ai/results` 回填）
- [ ] 把 API Key 改错 → 提示上游 401；改回正确后可以直接重试成功（失败不写库）
- [ ] 把上限设成比当前用量小的值 → 下一次生成提示已达上限，可命中缓存的仍能打开
- [ ] 设置 → 外观 → 语言切到 English：导航、列表、设置弹窗、AI tab、aria 标签全部变英文，刷新后保持
- [ ] 切到 English 后点「Summary」→ 上游收到的 prompt 是英文（可用假上游打印请求体验证）
- [ ] 登录页右上角胶囊在未登录状态下也能切换语言，并按浏览器语言给默认值
- [ ] 设置 → 集成：填 RSSHub 服务地址 → 点卡片左侧的循环图标 → 显示「连接正常 · Nms」
- [ ] 集成里加一条路由参数（如 `limit` / `/twitter/user` / `20`），然后添加订阅时只填 `/twitter/user/xxx` → 库里存的地址已带上参数
- [ ] 集成 → Obsidian 填绝对路径 → 自动化加一条「新文章到达 + 标题包含 X → 保存到 Obsidian」→ 刷新后仓库里出现 md 文件
- [ ] 设置 → 代理：切到「本地 HTTP 代理」填一个不存在的地址 → 测试连接报失败；切回「默认」→ 恢复
- [ ] 设置 → 自动化：新建规则、改条件与动作、关掉开关 → 刷新后只有开启的规则生效
- [ ] 切换设置弹窗的六个 tab，窗口尺寸始终 960×760（外壳不动，只有内容区滚动）
- [ ] 图片页与视频页的封面经 `/api/media` 加载；`backend/data/media/` 出现文件，刷新页面不再重复请求上游
- [ ] 找一张防盗链的图（直连 403），经缓存后能正常显示
- [ ] 正文里的相对路径图片（`<img src="/img/x.png">`）能正确显示（按原文地址解析）
- [ ] 把 `MEDIA_CACHE_MAX_MB` 调到 1，加载几十张图后旧文件被淘汰、目录不超预算
- [ ] 阅读器首页空态出现「添加订阅源」主按钮；点开后能填地址/名称/类型/目录并添加成功
- [ ] 列表头最左的「+」随时可打开同一个弹窗；从某个目录进来时目录已预选
- [ ] 把源的类型改成「图片」→ 该源条目出现在图片页、从文章页消失；改回「自动」恢复
- [ ] 在目录上右键 → 新建/重命名/删除；在区块空白处右键 → 只有「新建目录」可点
- [ ] 删除目录 → 弹窗确认 → 源回到「未分组」，源本身还在
- [ ] AI 设置里点垃圾桶 → 弹窗确认 → 供应商消失（不再有飘到左上角的菜单）
- [ ] 集成 → 添加参数 → 弹窗里填 name/scope/value 保存 → 表格出现该行（以前存不进去）
- [ ] 集成 → 自定义导出 → 改 schema → 测试推送能看到成功或具体报错
- [ ] 自动化：加第二个条件、切换「并且/或者」、把「当」改成定时并设时间
- [ ] 定时规则：时间设成当前分钟后一分钟内自动执行，且当天不重复执行
- [ ] 点「收藏」再点某个目录 → 进入的是该目录本身，不是「目录里的收藏」
- [ ] 停在一个类型（如「图片」）上点「收藏」→ 看到收藏的图片，「图片」与「收藏」两行同时高亮
- [ ] 在收藏里再点一次「收藏」→ 退出收藏，回到该类型的普通视图
- [ ] 在收藏里改点「文章」→ 变成收藏的文章（类型叠加，收藏不丢）

### 不花钱验证 AI 链路

```bash
python3 - <<'EOF' &
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])) or b"{}")
        out = {"choices": [{"message": {"content": "一句话总结。\n• 要点一"}}],
               "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        raw = json.dumps(out).encode()
        self.send_response(200); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", 8977), H).serve_forever()
EOF
```

然后「设置 → AI → 添加供应商 → 自定义」，地址填 `http://127.0.0.1:8977/v1`，模型随便填，
Key 留空即可（空 key 不发鉴权头）。

## 提交

Conventional Commits + 模块 scope，见 `AGENTS.md` §9。DoD 见 §10。
