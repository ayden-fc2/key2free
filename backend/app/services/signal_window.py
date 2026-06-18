from __future__ import annotations

# Unified strategy lookback window: pass T and the previous 199 wide-table rows.
SIGNAL_WINDOW_BARS = 200

# Buy/sell lifecycle decisions receive only T-1 and the previous trading bars.
TRADE_HISTORY_WINDOW_BARS = 10
