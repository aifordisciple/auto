#!/bin/bash
# 僵尸容器清理脚本
# 用于定期清理遗留的 autonome-tool-env 容器
# 建议：通过 cron job 每 6 小时执行一次

set -e

SCRIPT_NAME="cleanup-zombie-containers"
LOG_TAG="autonome-cleanup"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$LOG_TAG] $1"
}

# 清理 autonome-tool-env 僵尸容器（排除预热池容器）
cleanup_tool_env_containers() {
    # 获取所有 autonome-tool-env 容器 ID
    local all_ids=$(docker ps -a --filter "ancestor=autonome-tool-env:latest" -q)

    # 获取预热池容器 ID（标签 autonome.pool=true）
    local pool_ids=$(docker ps -a --filter "ancestor=autonome-tool-env:latest" --filter "label=autonome.pool=true" -q)

    # 计算僵尸容器（排除预热池）
    local zombie_ids=""
    if [ -n "$pool_ids" ]; then
        zombie_ids=$(echo "$all_ids" | grep -v -F "$pool_ids" | tr '\n' ' ')
    else
        zombie_ids=$all_ids
    fi

    local count=$(echo "$zombie_ids" | wc -w | tr -d ' ')

    if [ "$count" -gt 0 ]; then
        log "发现 $count 个僵尸容器（排除预热池），正在清理..."

        # 显示即将清理的容器
        echo "$zombie_ids" | xargs docker inspect --format '{{.Id[:12]}}\t{{.State.Status}}\t{{.Created}}' 2>/dev/null | head -10

        # 强制删除僵尸容器
        echo "$zombie_ids" | xargs docker rm -f

        log "✅ 已清理 $count 个僵尸容器"
    else
        log "✅ 没有发现僵尸容器"
    fi

    # 显示预热池容器状态
    local pool_count=$(echo "$pool_ids" | wc -w | tr -d ' ')
    if [ "$pool_count" -gt 0 ]; then
        log "📊 预热池容器: $pool_count 个（已保留）"
    fi
}

# 清理悬空镜像（可选）
cleanup_dangling_images() {
    local count=$(docker images -f "dangling=true" -q | wc -l)

    if [ "$count" -gt 0 ]; then
        log "发现 $count 个悬空镜像，正在清理..."
        docker image prune -f
        log "✅ 已清理悬空镜像"
    fi
}

# 主函数
main() {
    log "========== 开始清理 =========="

    cleanup_tool_env_containers
    cleanup_dangling_images

    # 显示 Docker 系统状态
    log "========== Docker 系统状态 =========="
    docker system df

    log "========== 清理完成 =========="
}

main "$@"