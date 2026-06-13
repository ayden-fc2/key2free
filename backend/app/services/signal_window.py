from __future__ import annotations

# 框架统一的信号回看窗口：每只股票传入 T 及以前最近 400 根宽表行（含 T 日）。
# 历史不足 400 根的评估日由信号系统直接跳过，策略不需要处理。
SIGNAL_WINDOW_BARS = 400
