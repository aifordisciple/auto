"""
Web Terminal WebSocket 端点

提供浏览器终端与 Docker 容器的实时双向通信。

WebSocket 协议：
- URL: /api/terminal/ws/{project_id}?token={jwt}&cols={cols}&rows={rows}
- 认证: JWT token 通过 query param 传递
- 授权: 验证 project.owner_id == user.id
- 通信: 二进制流（Docker PTY raw I/O）

安全措施：
- JWT 认证
- 项目权限校验
- 终端禁用网络（NetworkMode: none）
- 资源限制防止滥用
- 会话超时自动清理

计费策略：
- 按时长计费：每分钟 0.05 CU
- 最低收费：5 分钟
- 实时余额检查：余额不足自动断开
"""

import asyncio
import socket
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from sqlmodel import Session, select

from app.core.database import engine
from app.api.deps import verify_token_and_get_user
from app.models.domain import Project, User
from app.models.billing import TaskType
from app.services.terminal_manager import terminal_manager
from app.core.logger import log

router = APIRouter()


def get_db_session():
    """获取同步数据库会话（用于 WebSocket 中无法使用 Depends）"""
    return Session(engine)


@router.websocket("/ws/{project_id}")
async def websocket_terminal(
    websocket: WebSocket,
    project_id: str,
    token: str = Query(..., description="JWT 认证 token"),
    cols: int = Query(80, ge=20, le=200, description="终端列数"),
    rows: int = Query(24, ge=6, le=100, description="终端行数")
):
    """
    WebSocket 终端端点

    流程：
    1. 验证 JWT token
    2. 验证项目权限
    3. 创建终端容器
    4. 建立双向字节流泵
    5. 清理容器
    """
    session = None
    session_id = None
    docker_sock = None

    try:
        # ==========================================
        # 1. JWT 认证
        # ==========================================
        session = get_db_session()
        try:
            user = verify_token_and_get_user(token, session)
        except HTTPException as e:
            await websocket.close(code=4001, reason=f"认证失败: {e.detail}")
            return

        if not user:
            await websocket.close(code=4001, reason="用户不存在或已被禁用")
            return

        # ==========================================
        # 2. 项目权限校验
        # ==========================================
        project = session.get(Project, project_id)
        if not project:
            await websocket.close(code=4004, reason="项目不存在")
            return

        if project.owner_id != user.id:
            await websocket.close(code=4003, reason="无权访问此项目")
            return

        log.info(f"[Terminal] 🔐 用户 {user.id} 已认证，访问项目 {project_id}")

        # ==========================================
        # 2.5 计费检查与初始化
        # ==========================================
        from app.services.billing_service import BillingService
        from app.services.meters.terminal_meter import TerminalMeter

        billing_service = BillingService(session)
        wallet = billing_service.get_user_wallet(user.id)

        # 检查余额（最低 1 CU）
        if not billing_service.check_available(wallet, min_amount=1.0):
            await websocket.close(code=4002, reason="余额不足，请充值后继续使用终端")
            return

        # 创建计算记录（预估费用）
        estimated_cost = billing_service.estimate_cost(
            task_type=TaskType.TERMINAL,
            estimated_duration_minutes=30.0  # 预估 30 分钟
        )

        compute_record = billing_service.create_compute_record(
            wallet_id=wallet.wallet_id,
            user_id=user.id,
            task_type=TaskType.TERMINAL,
            task_name=f"Web Terminal: {project.name}",
            project_id=project_id,
            estimated_cost=estimated_cost,
        )

        # 冻结预估费用
        billing_service.freeze_credits(
            wallet_id=wallet.wallet_id,
            amount=estimated_cost,
            record_id=compute_record.record_id,
        )

        # 创建计量器
        meter = TerminalMeter(billing_service, session_id=None)

        log.info(f"[Terminal] 💰 计费初始化: wallet={wallet.wallet_id}, estimated={estimated_cost:.2f} CU")

        # ==========================================
        # 3. 接受 WebSocket 连接
        # ==========================================
        await websocket.accept(subprotocol="binary")

        # ==========================================
        # 4. 创建终端容器
        # ==========================================
        terminal_session = await terminal_manager.create_session(
            project_id=project_id,
            user_id=user.id,
            cols=cols,
            rows=rows
        )

        if not terminal_session:
            await websocket.send_bytes("\r\n\x1b[31m[ERROR] Failed to create terminal session\x1b[0m\r\n".encode('utf-8'))
            await websocket.close(code=5000, reason="创建终端失败")
            return

        session_id = terminal_session.session_id
        container_id = terminal_session.container_id

        # 发送欢迎消息
        welcome_msg = (
            f"\r\n"
            f"\x1b[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m\r\n"
            f"\x1b[32m  Autonome Web Terminal\x1b[0m\r\n"
            f"\x1b[90m  Project: {project.name} ({project_id})\x1b[0m\r\n"
            f"\x1b[90m  注意: 终端已禁用网络访问，仅可操作项目目录内文件\x1b[0m\r\n"
            f"\x1b[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m\r\n"
            f"\r\n"
        )
        await websocket.send_bytes(welcome_msg.encode('utf-8'))

        # ==========================================
        # 5. 连接到 Docker PTY
        # ==========================================
        docker_sock = await terminal_manager.attach_to_session(
            session_id,
            websocket.send_bytes
        )

        if not docker_sock:
            await websocket.send_bytes("\r\n\x1b[31m[ERROR] Failed to connect to terminal backend\x1b[0m\r\n".encode('utf-8'))
            await websocket.close(code=5001, reason="连接终端失败")
            return

        log.info(f"[Terminal] ✅ WebSocket 连接已建立: session={session_id}")

        # ==========================================
        # 6. 双向字节流泵
        # ==========================================
        async def pump_from_docker_to_websocket():
            """从 Docker PTY 读取数据，发送到 WebSocket"""
            try:
                loop = asyncio.get_event_loop()
                buffer = b""

                while True:
                    try:
                        # 使用 run_in_executor 避免阻塞
                        data = await loop.run_in_executor(
                            None,
                            lambda: docker_sock.recv(4096)
                        )
                        if not data:
                            break

                        # Docker attach 协议：前 8 字节是 header
                        # 简化处理：直接发送所有数据
                        # 实际 Docker 返回格式: [stream_type(1), 0, 0, 0, size(4 bytes), data...]
                        if len(data) > 8:
                            # 尝试解析 Docker 协议
                            stream_type = data[0]
                            if stream_type in (1, 2):  # stdout 或 stderr
                                # 跳过 8 字节 header
                                payload = data[8:]
                                if payload:
                                    await websocket.send_bytes(payload)
                            else:
                                # 非 Docker 协议，直接发送
                                await websocket.send_bytes(data)
                        else:
                            await websocket.send_bytes(data)

                    except BlockingIOError:
                        # 没有数据可读，等待一会
                        await asyncio.sleep(0.01)
                    except Exception as e:
                        log.debug(f"[Terminal] Docker → WebSocket 结束: {e}")
                        break

            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error(f"[Terminal] Docker → WebSocket 错误: {e}")

        async def pump_from_websocket_to_docker():
            """从 WebSocket 读取数据，发送到 Docker PTY"""
            try:
                while True:
                    # 接收 WebSocket 消息
                    data = await websocket.receive_bytes()

                    # ✨ 更新会话活跃时间（防止被自动回收）
                    terminal_manager.touch_activity(session_id)

                    # 直接转发到 Docker
                    try:
                        docker_sock.sendall(data)
                    except Exception as e:
                        log.debug(f"[Terminal] WebSocket → Docker 发送失败: {e}")
                        break

            except WebSocketDisconnect:
                log.info(f"[Terminal] WebSocket 断开: session={session_id}")
            except Exception as e:
                log.debug(f"[Terminal] WebSocket → Docker 结束: {e}")

        # 并发运行两个泵
        pump_task = asyncio.create_task(pump_from_docker_to_websocket())
        input_task = asyncio.create_task(pump_from_websocket_to_docker())

        # 等待任一任务完成
        done, pending = await asyncio.wait(
            [pump_task, input_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # 取消未完成的任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        log.info(f"[Terminal] WebSocket 连接断开")
    except Exception as e:
        log.error(f"[Terminal] WebSocket 错误: {e}")
        try:
            await websocket.close(code=5000, reason=str(e))
        except:
            pass
    finally:
        # ==========================================
        # 7. 清理资源与计费结算
        # ==========================================

        # 计费结算
        if 'meter' in dir() and meter and 'compute_record' in dir() and compute_record:
            try:
                # 停止计量
                meter.stop_metering(compute_record.record_id)

                # 计算实际费用
                duration_minutes = meter._calculate_duration() / 60.0 if meter.start_time else 0
                actual_cost = max(duration_minutes * 0.05, 5 * 0.05)  # 最低 5 分钟

                # 结算
                billing_service.settle_frozen_credits(
                    wallet_id=wallet.wallet_id,
                    record_id=compute_record.record_id,
                    actual_cost=actual_cost,
                    execution_details={
                        "duration_seconds": meter._calculate_duration(),
                        "session_id": session_id,
                    },
                )

                log.info(f"[Terminal] 💰 计费结算: duration={duration_minutes:.1f}min, cost={actual_cost:.2f} CU")

            except Exception as e:
                log.error(f"[Terminal] 计费结算失败: {e}")
                # 尝试退款
                try:
                    billing_service.refund_frozen_credits(
                        wallet_id=wallet.wallet_id,
                        record_id=compute_record.record_id,
                    )
                except:
                    pass

        # 关闭 Docker socket
        if docker_sock:
            try:
                docker_sock.close()
            except:
                pass

        # 销毁终端会话
        if session_id:
            await terminal_manager.destroy_session(session_id)
            log.info(f"[Terminal] 🧹 会话已清理: {session_id}")

        # 关闭数据库会话
        if session:
            session.close()


@router.post("/resize/{session_id}")
async def resize_terminal(
    session_id: str,
    cols: int = Query(..., ge=20, le=200),
    rows: int = Query(..., ge=6, le=100)
):
    """
    调整终端大小（可选，用于前端 resize 事件）
    """
    success = await terminal_manager.resize_terminal(session_id, cols, rows)
    return {"status": "success" if success else "failed"}