# Minecraft Studio Service

面向 Minecraft 创作工具的独立服务仓库。它与 `site/`、`media-parser/` 分别维护
代码、运行时与发布节奏；客户端仅通过 API 接入。

## Modules

- `services/skin-generation/`：AI 完整皮肤生成 POC，输出经过校验的 Minecraft
  皮肤 PNG。
- `services/cape-design/`：预留给披风设计能力。
- `services/building-preview/`：预留给建筑预览能力。

新增模块必须保持独立的依赖、运行说明与 API 边界，不能把模型权重或运行环境带入
客户端仓库。

## Local development

从仓库根目录统一管理本地模块：

```bash
bash scripts/dev.sh
bash scripts/dev.sh skin-generation
bash scripts/dev.sh status
bash scripts/dev.sh restart skin-generation
bash scripts/dev.sh stop skin-generation
bash scripts/dev.sh ls
```

启动脚本将 PID 写入 `.dev/pids/`、日志写入 `.dev/logs/`；两者都是本地运行数据。
首次启动皮肤生成模块时，脚本会自动创建其 Python 环境并安装依赖。
