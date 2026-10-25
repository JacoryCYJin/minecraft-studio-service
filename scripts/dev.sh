#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT/.dev"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"

# name|directory|start command|port
SERVICES=(
  "monadical|services/skin-generation|bash scripts/run-local.sh|8011"
  "block|services/block-skin-generation|bash scripts/run-local.sh|8012"
)

usage() {
  cat <<'EOF'
Minecraft Studio Service 开发指令

用法:
  bash scripts/dev.sh <动作> [服务]
  bash scripts/dev.sh start [服务]       启动全部或指定服务
  bash scripts/dev.sh stop [服务]        停止全部或指定服务
  bash scripts/dev.sh restart [服务]     重启全部或指定服务
  bash scripts/dev.sh status [服务]      查看全部或指定服务状态
  bash scripts/dev.sh logs [服务]        查看最近 120 行日志
  bash scripts/dev.sh list               列出服务（别名 ls）
  bash scripts/dev.sh --help             显示帮助，支持 <动作> --help
构建: 本项目没有 build 步骤，运行环境仍由原启动流程管理。

服务: monadical、block（skin-generation 是 monadical 的兼容别名）
未指定服务时操作本项目全部服务。无参数、直接写服务名等旧写法仍兼容并提示规范写法。
EOF
}

ensure_runtime_dirs() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
}

normalize_service_name() {
  case "$1" in
    skin-generation) printf '%s' "monadical" ;;
    *) printf '%s' "$1" ;;
  esac
}

get_service_field() {
  local service
  local index="$2"
  local item name dir cmd port

  service="$(normalize_service_name "$1")"

  for item in "${SERVICES[@]}"; do
    IFS='|' read -r name dir cmd port <<< "$item"
    if [[ "$name" == "$service" ]]; then
      case "$index" in
        1) printf '%s' "$name" ;;
        2) printf '%s' "$dir" ;;
        3) printf '%s' "$cmd" ;;
        4) printf '%s' "$port" ;;
      esac
      return 0
    fi
  done

  return 1
}

service_exists() {
  get_service_field "$1" 1 >/dev/null 2>&1
}

list_services() {
  local item name dir cmd port
  printf '%-24s %-8s %s\n' "SERVICE" "PORT" "COMMAND"
  for item in "${SERVICES[@]}"; do
    IFS='|' read -r name dir cmd port <<< "$item"
    printf '%-24s %-8s %s\n' "$name" "$port" "$cmd"
  done
}

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

pid_on_port() {
  lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

terminate_pid() {
  local pid="$1"
  local child

  if ! is_pid_running "$pid"; then
    return 0
  fi

  while read -r child; do
    [[ -n "$child" ]] && terminate_pid "$child"
  done < <(pgrep -P "$pid" 2>/dev/null || true)

  kill "$pid" 2>/dev/null || true
}

wait_for_pid_exit() {
  local pid="$1"
  local attempts="${2:-20}"
  local i

  for ((i = 0; i < attempts; i++)); do
    ! is_pid_running "$pid" && return 0
    sleep 0.2
  done

  return 1
}

wait_for_port_release() {
  local port="$1"
  local attempts="${2:-25}"
  local i

  for ((i = 0; i < attempts; i++)); do
    ! port_in_use "$port" && return 0
    sleep 0.2
  done

  return 1
}

wait_for_port_listen() {
  local port="$1"
  local attempts="${2:-25}"
  local i

  for ((i = 0; i < attempts; i++)); do
    port_in_use "$port" && return 0
    sleep 0.2
  done

  return 1
}

clear_service_port() {
  local service="$1"
  local port="$2"
  local pids pid

  pids="$(pid_on_port "$port")"
  [[ -z "$pids" ]] && return 0

  echo "[$service] 检测到端口 $port 上有残留进程，正在清理: $(echo "$pids" | tr '\n' ' ')"
  while read -r pid; do
    [[ -n "$pid" ]] && terminate_pid "$pid"
  done <<< "$pids"

  if wait_for_port_release "$port" 15; then
    return 0
  fi

  while read -r pid; do
    [[ -n "$pid" ]] && is_pid_running "$pid" && kill -9 "$pid" 2>/dev/null || true
  done <<< "$pids"

  wait_for_port_release "$port" 10
}

ensure_service_dependencies() {
  local service="$1"
  local workdir="$2"

  case "$service" in
    monadical|block)
      if [[ ! -x "$workdir/.venv/bin/python" ]]; then
        echo "[$service] 未检测到本地 Python 环境，正在初始化依赖..."
        (cd "$workdir" && bash scripts/bootstrap.sh)
      fi
      ;;
  esac
}

pid_file_for() {
  if [[ "$1" == "monadical" && ! -f "$PID_DIR/monadical.pid" && -f "$PID_DIR/skin-generation.pid" ]]; then
    printf '%s/%s.pid' "$PID_DIR" "skin-generation"
    return 0
  fi
  printf '%s/%s.pid' "$PID_DIR" "$1"
}

log_file_for() {
  printf '%s/%s.log' "$LOG_DIR" "$1"
}

read_pid() {
  local pid_file
  pid_file="$(pid_file_for "$1")"
  [[ -f "$pid_file" ]] && cat "$pid_file"
}

start_service() {
  local service
  local dir cmd port workdir pid pid_file log_file listener_pid

  service="$(normalize_service_name "$1")"

  if ! service_exists "$service"; then
    echo "未知服务: $service" >&2
    echo "可用服务: monadical, block" >&2
    exit 1
  fi

  dir="$(get_service_field "$service" 2)"
  cmd="$(get_service_field "$service" 3)"
  port="$(get_service_field "$service" 4)"
  workdir="$ROOT/$dir"
  pid_file="$(pid_file_for "$service")"
  log_file="$(log_file_for "$service")"

  if [[ ! -d "$workdir" ]]; then
    echo "目录不存在: $workdir" >&2
    exit 1
  fi

  pid="$(read_pid "$service" || true)"
  if is_pid_running "$pid"; then
    echo "[$service] 已在运行 (pid=$pid, port=$port)"
    return 0
  fi

  if port_in_use "$port"; then
    clear_service_port "$service" "$port" || true
    if port_in_use "$port"; then
      echo "[$service] 端口 $port 仍被占用，无法启动。占用进程: $(pid_on_port "$port" | tr '\n' ' ')" >&2
      exit 1
    fi
  fi

  ensure_service_dependencies "$service" "$workdir"

  (
    cd "$workdir"
    nohup bash -lc "exec $cmd" >"$log_file" 2>&1 < /dev/null &
    echo $! >"$pid_file"
  )

  wait_for_port_listen "$port" 25 || true
  listener_pid="$(pid_on_port "$port" | head -n 1)"
  [[ -n "$listener_pid" ]] && echo "$listener_pid" >"$pid_file"

  pid="$(read_pid "$service")"
  if is_pid_running "$pid" && port_in_use "$port"; then
    echo "[$service] 已启动 (pid=$pid, port=$port, log=$log_file)"
  else
    echo "[$service] 启动失败，查看日志: $log_file" >&2
    exit 1
  fi
}

stop_service() {
  local service
  local pid pid_file port

  service="$(normalize_service_name "$1")"

  if ! service_exists "$service"; then
    echo "未知服务: $service" >&2
    exit 1
  fi

  pid_file="$(pid_file_for "$service")"
  port="$(get_service_field "$service" 4)"
  pid="$(read_pid "$service" || true)"

  if is_pid_running "$pid"; then
    terminate_pid "$pid"
    wait_for_pid_exit "$pid" 10 || true
    is_pid_running "$pid" && kill -9 "$pid" 2>/dev/null || true
    echo "[$service] 已停止 (pid=$pid)"
  else
    echo "[$service] 未在运行"
  fi

  port_in_use "$port" && clear_service_port "$service" "$port" || true
  rm -f "$pid_file"
}

restart_service() {
  stop_service "$1"
  start_service "$1"
}

print_status() {
  local item name dir cmd port pid target="${1:-}"
  printf '%-24s %-8s %-8s %s\n' "SERVICE" "PORT" "PID" "STATUS"

  for item in "${SERVICES[@]}"; do
    IFS='|' read -r name dir cmd port <<< "$item"
    [[ -z "$target" || "$name" == "$target" ]] || continue
    pid="$(read_pid "$name" || true)"
    if is_pid_running "$pid"; then
      printf '%-24s %-8s %-8s %s\n' "$name" "$port" "$pid" "running"
    elif port_in_use "$port"; then
      printf '%-24s %-8s %-8s %s\n' "$name" "$port" "-" "port busy"
    else
      printf '%-24s %-8s %-8s %s\n' "$name" "$port" "-" "stopped"
    fi
  done
}

logs() {
  local target="${1:-}" item name dir cmd port file
  for item in "${SERVICES[@]}"; do
    IFS='|' read -r name dir cmd port <<< "$item"
    [[ -z "$target" || "$name" == "$target" ]] || continue
    file="$(log_file_for "$name")"
    if [[ -f "$file" ]]; then
      printf '\n--- %s ---\n' "$name"
      tail -n 120 "$file"
    else
      echo "[$name] 暂无日志: $file"
    fi
  done
}

cli_error() {
  echo "[dev] $*；使用 bash scripts/dev.sh --help 查看用法" >&2
  return 2
}

run_service_action() {
  local action="$1" target="$2" item name rest
  ensure_runtime_dirs
  if [[ -n "$target" ]]; then
    "${action}_service" "$target"
  else
    for item in "${SERVICES[@]}"; do
      IFS='|' read -r name rest <<< "$item"
      "${action}_service" "$name"
    done
  fi
}

main() {
  local action="${1:-start}" target arg
  for arg in "$@"; do
    case "$arg" in -h|--help) usage; return 0 ;; esac
  done
  if [[ "$action" == help ]]; then
    [[ $# -le 2 ]] || { cli_error "help 最多接受一个动作"; return 2; }
    usage
    return 0
  fi
  if [[ $# -eq 0 ]]; then
    echo "[兼容] 无参数仍只启动 monadical；请改用: bash scripts/dev.sh start monadical" >&2
    action=start
    set -- start monadical
  fi
  shift || true
  case "$action" in
    list|ls)
      [[ $# -eq 0 ]] || { cli_error "list 不接受服务参数"; return 2; }
      list_services
      return
      ;;
    all)
      echo "[兼容] 请改用: bash scripts/dev.sh start${*:+ $*}" >&2
      action=start
      ;;
    monadical|block|skin-generation)
      [[ $# -eq 0 ]] || { cli_error "服务名后不接受额外参数，请使用 start <服务>"; return 2; }
      echo "[兼容] 请改用: bash scripts/dev.sh start $action" >&2
      set -- "$action"
      action=start
      ;;
    start|stop|restart|status|logs) ;;
    *) cli_error "不支持的动作: $action"; return 2 ;;
  esac
  [[ $# -le 1 ]] || { cli_error "$action 最多接受一个服务"; return 2; }
  target="${1:-}"
  [[ -z "$target" ]] || target="$(normalize_service_name "$target")"
  if [[ -n "$target" ]] && ! service_exists "$target"; then
    cli_error "未知服务: $target"
    return 2
  fi
  case "$action" in
    status) print_status "$target" ;;
    logs) logs "$target" ;;
    *) run_service_action "$action" "$target" ;;
  esac
}

main "$@"
