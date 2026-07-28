# AGENTS.md

`minecraft-studio-service/` 是 Minecraft 创作能力的独立服务仓库。它不属于
`site/` 的运行时，也不得依赖 `media-parser/`。

## Scope

- 当前模块：`services/skin-generation/`，用于本地 AI 完整皮肤生成 POC。
- 预留模块：`services/cape-design/`、`services/building-preview/`。
- 各模块通过独立 HTTP API 对外提供能力；网站或其他客户端只能调用 API，不能
  引入模型运行时代码或权重。
- 不把模型权重、生成产物、用户参考图、`.venv/` 或密钥提交到 Git。

## Python

- 每个 Python 服务使用其自身目录中的 `.venv/`。
- 不使用系统 Python 或其他仓库的环境。
- 皮肤 POC 的运行与验证：

```bash
cd minecraft-studio-service
bash scripts/dev.sh
bash scripts/dev.sh status
bash scripts/dev.sh stop skin-generation

cd services/skin-generation
.venv/bin/python -m compileall app scripts/verify-artifact.py
```

- `scripts/dev.sh` 是本仓库本地服务的唯一日常启动入口；它管理 `.dev/` 下的
  PID 与日志，并在首次缺少环境时调用模块的 `scripts/bootstrap.sh`。
- 模块内的 `scripts/run-local.sh` 仅供根启动脚本调用，不作为日常手动启动命令。

## Development

- 本地服务仅监听 `127.0.0.1`，除非用户明确要求，不开放局域网或公网端口。
- 变更 API 时先更新对应模块 README；不得与任一前端仓库共享文件路径或环境。
- 新模块必须有自己的 README、运行时忽略规则和验证命令。
- Git 分支、提交和发布遵循 workspace 根目录 `AGENTS.md` 与 `git-rule`。
