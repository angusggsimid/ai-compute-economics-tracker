"""网络取数的重试助手：只对**瞬时**故障重试，确定性失败立刻抛出。

动机：阻塞性数据源（OpenRouter 用量/牌价、neocloud 报价）任何一次网络抖动
都会让整条流水线变红、页面停止更新。实测遇到过 SEC 的瞬时 403、Foundry 的 523。
重试不是"静默兜底"——重试用尽后仍然照常抛出，失败依旧显式暴露。
"""

from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# 值得重试的 HTTP 状态：限流与服务端错误
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504, 522, 523, 524}


def _status_of(exc: BaseException) -> int | None:
    for attr in ("code", "status", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def is_transient(exc: BaseException) -> bool:
    """瞬时故障判定：超时/连接层错误/限流/5xx。4xx（除 408/425/429）视为确定性失败。"""
    name = type(exc).__name__
    if name in ("URLError", "TimeoutError", "ConnectionError", "ReadTimeout", "ConnectTimeout",
                "ChunkedEncodingError", "IncompleteRead", "RemoteDisconnected",
                "ProtocolError", "ConnectionResetError", "socket.timeout"):
        return True
    status = _status_of(exc)
    if status is not None:
        return status in RETRY_STATUS or status >= 500
    # requests 的超时/连接异常走类名判断（避免硬依赖 requests）
    return "Timeout" in name or "Connection" in name


def retry_call(
    fn: Callable[[], T],
    *,
    label: str,
    attempts: int = 3,
    base_delay: float = 1.5,
) -> T:
    """执行 fn，瞬时故障时按退避重试。全部用尽后抛出最后一次异常。"""
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — 交给 is_transient 分类
            last = exc
            if attempt >= attempts or not is_transient(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            # 显式打印，重试事实可见（不掩盖上游问题）
            print(f"[retry] {label} 第 {attempt} 次失败（{type(exc).__name__}: {exc}），{delay:.1f}s 后重试")
            time.sleep(delay)
    assert last is not None
    raise last


def get_with_retry(fetch: Callable[[], Any], *, label: str, attempts: int = 3) -> Any:
    """给一次性的取数函数套上重试。"""
    return retry_call(fetch, label=label, attempts=attempts)
