"""
Docker API 共享工具函数

提取自 bio_tools.py 和 container_pool_service.py 中的重复代码，
统一 Docker 守护进程 Unix Socket 通信逻辑。
"""

import json
import socket
from typing import Any, Optional, Union

from app.core.logger import log
from app.core.sandbox_config import DOCKER_SOCKET


def docker_api_request(
    method: str,
    path: str,
    data: Optional[str] = None,
    return_raw: bool = False,
    timeout: int = 30
) -> Union[dict, list, str]:
    """
    直接通过 Unix Socket 调用 Docker Engine API

    Args:
        method: HTTP 方法 (GET, POST, DELETE 等)
        path: API 路径，如 "/containers/json"
        data: 请求体字符串 (JSON)
        return_raw: 是否返回原始文本（用于日志等非 JSON 响应）
        timeout: Socket 超时时间（秒）

    Returns:
        解析后的 JSON 数据，或原始文本（当 return_raw=True 时）
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(DOCKER_SOCKET)

    body = data.encode('utf-8') if data else None

    # 使用 HTTP/1.0 强制服务器发送完毕后断开连接
    request = f"{method} {path} HTTP/1.0\r\n"
    request += "Host: localhost\r\n"
    request += "Connection: close\r\n"
    if body:
        request += f"Content-Length: {len(body)}\r\n"
    request += "Content-Type: application/json\r\n\r\n"

    if body:
        request = request.encode('utf-8') + body
    else:
        request = request.encode('utf-8')

    sock.sendall(request)

    # 安全地读取全部数据，直到连接自然关闭
    response = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk

    sock.close()

    # 解析响应（分离 Headers 和 Body）
    if b"\r\n\r\n" in response:
        headers_raw, raw_body = response.split(b"\r\n\r\n", 1)
    else:
        headers_raw = b""
        raw_body = response

    # 解析 HTTP 状态行，提取状态码用于错误日志
    headers_str = headers_raw.decode('utf-8', errors='ignore')
    status_line = headers_str.split('\r\n')[0] if headers_str else ''
    status_code = 0
    if status_line.startswith('HTTP/'):
        parts = status_line.split(' ')
        if len(parts) >= 2:
            try:
                status_code = int(parts[1])
            except ValueError:
                pass

    body_str = raw_body.decode('utf-8', errors='ignore').strip()

    # 记录非成功 HTTP 状态码
    if status_code >= 400:
        log.warning(
            f"[docker_api] {method} {path} → HTTP {status_code}, "
            f"body_len={len(body_str)}, body_head={body_str[:200]}"
        )

    if not body_str:
        return "" if return_raw else {}

    # 如果是获取日志等非 JSON 响应，直接返回纯文本
    if return_raw:
        return body_str

    # 用最安全的截取方式提取 JSON
    start_dict = body_str.find('{')
    end_dict = body_str.rfind('}')

    start_list = body_str.find('[')
    end_list = body_str.rfind(']')

    try:
        if start_dict != -1 and end_dict != -1 and (start_list == -1 or start_dict < start_list):
            return json.loads(body_str[start_dict:end_dict+1])
        elif start_list != -1 and end_list != -1:
            return json.loads(body_str[start_list:end_list+1])

        return json.loads(body_str)
    except Exception as e:
        log.warning(
            f"[docker_api] JSON 解析失败, {method} {path}, "
            f"HTTP {status_code}, body_len={len(body_str)}, "
            f"body_head={body_str[:300]}"
        )
        return {"body": body_str, "_http_status": status_code}
