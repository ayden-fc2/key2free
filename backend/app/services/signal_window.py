from __future__ import annotations

# Unified maximum signal lookback window. Strategies can still register smaller
# windows; sqx_oversold_repair needs 250 listed bars plus structure history.
SIGNAL_WINDOW_BARS = 260

# Buy/sell lifecycle decisions receive only T-1 and the previous trading bars.
TRADE_HISTORY_WINDOW_BARS = 10
