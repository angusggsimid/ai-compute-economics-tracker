"""周序列完整性判定——图表与四时钟引擎必须共用同一把尺子。

背景：抓取窗口的起点周是残周（OpenRouter 只覆盖该周后几天），其 token 量约为
次周的 1/7。若把它当完整周，会同时造成两种失真：
1. 增长倍数虚标（0.75T 起算 → ×172；实际应从首个完整周 5.38T 起算 → ×24）；
2. "52 个完整周"的达标度被高估一周。

因此：残周的识别与剔除只允许有一处实现，图与时钟都调用它。
"""

from __future__ import annotations

from typing import Any, Sequence

# 首周低于次周该比例即判为残周。0.5 意味着"不足次周一半"，
# 正常周际波动远达不到这个幅度，故不会误伤真实数据。
PARTIAL_WEEK_RATIO = 0.5


def is_partial_first_week(values: Sequence[float]) -> bool:
    """首值是否明显低于次值（残周特征）。样本不足 2 个时返回 False。"""
    nums = [float(v) for v in values[:2] if v is not None]
    if len(nums) < 2 or nums[1] <= 0:
        return False
    return nums[0] < PARTIAL_WEEK_RATIO * nums[1]


def drop_partial_first_week(rows: list[dict[str, Any]], value_key: str) -> tuple[list[dict[str, Any]], str | None]:
    """返回 (剔除残周后的行, 被剔除的日期)。行需按日期升序。"""
    ordered = sorted(rows, key=lambda r: str(r.get("date") or ""))
    if not ordered:
        return rows, None
    try:
        vals = [float(r[value_key]) for r in ordered]
    except (KeyError, TypeError, ValueError):
        return ordered, None
    if not is_partial_first_week(vals):
        return ordered, None
    dropped = str(ordered[0].get("date"))
    return ordered[1:], dropped


def complete_week_count(weeks: Sequence[dict[str, Any]], value_key: str = "total_tokens") -> int:
    """完整周数（剔除残周）。用于四时钟的 52 周达标判定。"""
    vals = [w.get(value_key) for w in weeks]
    nums = [float(v) for v in vals if isinstance(v, (int, float))]
    if len(nums) >= 2 and is_partial_first_week(nums):
        return len(nums) - 1
    return len(nums)
