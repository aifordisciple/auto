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
        headers, raw_body = response.split(b"\r\n\r\n", 1)
    else:
        raw_body = response

    body_str = raw_body.decode('utf-8', errors='ignore').strip()

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
        log.warning(f"JSON 解析回退, 原始数据长度: {len(body_str)}")
        return {"body": body_str}
