# AGENTS.md

`minecraft-studio-service/` 是 Minecraft 创作能力的独立服务仓库。它不属于
`site/` 的运行时，也不得依赖 `media-parser/`。

## Scope

- 当前模块：`services/skin-generation/`（Monadical 文本生成）与
  `services/block-skin-generation/`（BLOCK 预览图转换），两者独立运行。
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
bash scripts/dev.sh start monadical
bash scripts/dev.sh start block
bash scripts/dev.sh start             # 本项目两个服务
bash scripts/dev.sh stop block
bash scripts/dev.sh restart block
bash scripts/dev.sh status [block]
bash scripts/dev.sh logs [block]
bash scripts/dev.sh list
bash scripts/dev.sh --help

cd services/skin-generation
.venv/bin/python -m compileall app scripts/verify-artifact.py
```

- `scripts/dev.sh` 是本仓库本地服务的唯一日常启动入口；它管理 `.dev/` 下的
  PID 与日志，并在首次缺少环境时调用模块的 `scripts/bootstrap.sh`。
- 模块内的 `scripts/run-local.sh` 仅供根启动脚本调用，不作为日常手动启动命令。

## Commands

工作区根目录使用 `bash scripts/dev.sh mc <动作> [服务]`；子仓库根目录使用 `bash scripts/dev.sh <动作> [服务]`。服务为 monadical、block，skin-generation 保留为 monadical 的兼容别名。方括号仅表示可选参数。
未指定服务的显式 start、stop、restart、status、logs 针对本项目全部服务。为兼容旧行为，子仓库无参数仍仅启动 monadical 并提示正式写法；旧 all 和直接写服务名也保留提示。外层无动作的 mc 则仍兼容启动本项目全部服务。
本项目没有 build 步骤，不把 Python 语法检查伪装成构建。运行环境仍按原启动流程和各模块 .venv 管理。
脚本修改后执行 `bash -n scripts/dev.sh`，核验 list、status、logs、帮助和无效参数；不为命令解析验证而启动模型服务或重启用户正在使用的服务。

统一约定：正式动作使用 `start / stop / restart / status / logs / list`，`ls` 仅作 `list` 的别名。工作区入口为 `bash scripts/dev.sh <项目> <动作> [目标]`，子仓库入口省略项目名。`-h`、`--help`（包括动作后的帮助）只展示帮助，不启停服务；参数错误返回 2，查询到未运行状态仍返回 0。未知动作、未知目标、多余参数必须在操作前拒绝。旧的省略动作写法暂时兼容并输出迁移提示，帮助和示例只推荐正式写法。

## Development

- 本地服务仅监听 `127.0.0.1`，除非用户明确要求，不开放局域网或公网端口。
- 变更 API 时先更新对应模块 README；不得与任一前端仓库共享文件路径或环境。
- 新模块必须有自己的 README、运行时忽略规则和验证命令。
- Git 分支、提交和发布遵循 workspace 根目录 `AGENTS.md` 与 `git-rule`。

## Git

- 本目录是独立仓库，遵循工作区 `git-rule`；以下口令发给 Agent，不在终端运行：
  - `mc push`：验证、提交已确认任务的改动并推送任务分支；不创建 PR、不合并。
  - `mc pr`：验证、提交、推送，创建或更新对应 PR，返回链接后停止；不合并、不切回 `main`。
  - `mc merge`：验证、提交、推送，创建或复用对应 PR，squash merge 后切回 `main`，执行 `git pull origin main`。
- 一条口令包含所需前置步骤，无须依次发送 push、pr、merge。完整 merge 口令已授权合并，不在正常流程末尾重复询问；push 和 pr 不授权合并。
- 只处理已确认任务或用户指定范围，保留其他任务的工作区及暂存改动；核对待推送提交，不能把其他仓库或不明归属改动一并上传。能明确区分时直接按范围处理，无法判断时才澄清。
- 验证或后续步骤失败未解决前，不进入下一阶段；没有新改动不创建空提交。复用 PR 前核对仓库、源分支、目标分支；恢复流程时检查现状，避免重复提交或重复 PR。
- 批准修改文件不等于授权上传；`rules commit` 只在外层本地提交规则，不包含本仓库。版本、发布、标签及忽略规则保持不变，以 git-rule 和本仓库约束为准。
