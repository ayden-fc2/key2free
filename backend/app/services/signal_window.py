from __future__ import annotations

# Unified maximum signal lookback window. Strategies can still register smaller
# windows; sharp_rise_pullback_leader needs the current maximum 200-bar window.
SIGNAL_WINDOW_BARS = 200

# Buy/sell lifecycle decisions receive only T-1 and the previous trading bars.
TRADE_HISTORY_WINDOW_BARS = 10
