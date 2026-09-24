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
