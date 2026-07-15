from __future__ import annotations

import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from app.entities.stock_data_context import StockDailyFrame
from app.services.strategy_lifecycle import MarketViews, StrategyContext
from strategies.sharp_rise_pullback_leader.strategy import (
    SharpRisePullbackLeaderLifecycle,
    _calculate_raw_buy_price,
    _trailing_exit_for_day,
)


class SharpRisePullbackLeaderSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lifecycle = SharpRisePullbackLeaderLifecycle()

    def test_builds_exact_s_h_l_t_model_and_bug_price(self) -> None:
        frame = self._valid_frame()
        trade_date = frame.trade_dates[-1]
        result = self.lifecycle._select_signal_from_frame(
            code="sh.600000",
            row={"name": "测试股票", "close": 12.0, "turnover_rate": 6.0},
            frame=frame,
            trade_date=trade_date,
        )

        self.assertIsNotNone(result)
        extras = result["signal"]["extras"]
        self.assertEqual(extras["s_date"], frame.trade_dates[0].isoformat())
        self.assertEqual(extras["s_to_t_bars"], 24)
        self.assertEqual(extras["h_date"], frame.trade_dates[18].isoformat())
        self.assertEqual(extras["h_to_t_bars"], 6)
        self.assertEqual(extras["l_date"], frame.trade_dates[21].isoformat())
        self.assertAlmostEqual(extras["h_high"], 120.0)
        self.assertAlmostEqual(extras["l_low"], 108.0)
        self.assertAlmostEqual(extras["h_to_l_drawdown"], 0.10)
        self.assertAlmostEqual(extras["bug_price"], 117.6)
        self.assertEqual(result["signal"]["max_watch_days"], 5)

    def test_rejects_high_outside_three_to_ten_bars(self) -> None:
        frame = self._valid_frame()
        highs = list(frame.columns["qfq_high"])
        highs[18] = 116.0
        highs[12] = 121.0
        frame.columns["qfq_high"] = highs

        result = self.lifecycle._select_signal_from_frame(
            code="sh.600000",
            row={"name": "测试股票", "close": 12.0, "turnover_rate": 6.0},
            frame=frame,
            trade_date=frame.trade_dates[-1],
        )
        self.assertIsNone(result)

    def test_signal_selection_excludes_st_and_star_market_only(self) -> None:
        frame = self._valid_frame()
        trade_date = frame.trade_dates[-1]
        rows = []
        candidates = (
            ("sz.000001", "正常股票", 0.0),
            ("sz.000002", "ST测试", 0.0),
            ("sz.000003", "字段风险", 1.0),
            ("sh.688001", "科创测试", 0.0),
        )
        for code, name, is_st in candidates:
            rows.append(
                {
                    "trade_date": trade_date,
                    "code": code,
                    "name": name,
                    "close": 12.0,
                    "qfq_high": 115.0,
                    "qfq_low": 110.0,
                    "qfq_close": 111.0,
                    "ma_10": 114.0,
                    "ma_20": 112.0,
                    "ma_30": 110.0,
                    "is_st": is_st,
                    "turnover_rate": 6.0,
                }
            )

        class FakeView:
            def cross_section(self, columns: object) -> pd.DataFrame:
                return pd.DataFrame(rows)

            def iter_stock_history(self, *, columns: object, window: int, codes: object):
                for code in codes:
                    yield code, StockDailyFrame(
                        code=code,
                        trade_dates=frame.trade_dates,
                        columns=frame.columns,
                    )

        signals = self.lifecycle.select_signals(trade_date=trade_date, view=FakeView())
        self.assertEqual([signal["code"] for signal in signals], ["sz.000001"])

    def test_three_buy_price_branches(self) -> None:
        first, first_branch = _calculate_raw_buy_price(
            l_low=100.0,
            l_ma10=110.0,
            l_ma20=100.0,
            t_ma10=120.0,
            t_ma20=115.0,
        )
        second, second_branch = _calculate_raw_buy_price(
            l_low=105.0,
            l_ma10=110.0,
            l_ma20=100.0,
            t_ma10=120.0,
            t_ma20=115.0,
        )
        third, third_branch = _calculate_raw_buy_price(
            l_low=110.0,
            l_ma10=110.0,
            l_ma20=100.0,
            t_ma10=120.0,
            t_ma20=115.0,
        )

        self.assertAlmostEqual(first, 120.75)
        self.assertEqual(first_branch, "l_low_at_or_below_l_ma20_1_01")
        self.assertAlmostEqual(second, 120.0)
        self.assertEqual(second_branch, "l_low_between_ma20_1_01_and_ma10_0_99")
        self.assertAlmostEqual(third, 126.0)
        self.assertEqual(third_branch, "l_low_above_l_ma10_0_99")

    def _valid_frame(self) -> StockDailyFrame:
        length = 25
        dates = [date(2026, 1, 1) + timedelta(days=index) for index in range(length)]
        highs = [116.0] * length
        highs[18] = 120.0
        lows = [113.0] * length
        lows[18] = 115.0
        lows[19] = 112.0
        lows[20] = 110.0
        lows[21] = 108.0
        lows[22] = 109.0
        lows[23] = 110.0
        lows[24] = 110.0
        closes = [114.0] * length
        closes[24] = 111.0
        ma10 = [112.0] * length
        ma20 = [110.0] * length
        ma30 = [108.0] * length
        ma10[24] = 114.0
        ma20[24] = 112.0
        ma30[24] = 110.0
        return StockDailyFrame(
            code="sh.600000",
            trade_dates=dates,
            columns={
                "qfq_high": highs,
                "qfq_low": lows,
                "qfq_close": closes,
                "ma_10": ma10,
                "ma_20": ma20,
                "ma_30": ma30,
            },
        )


class SharpRisePullbackLeaderLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lifecycle = SharpRisePullbackLeaderLifecycle()
        self.signal = {
            "signal_close": 105.0,
            "extras": {"bug_price": 110.0, "l_low": 100.0},
        }
        self.watch_item = SimpleNamespace(
            code="sh.600000",
            code_name="测试股票",
            added_trade_index=0,
            max_watch_days=5,
            signal=self.signal,
        )

    @patch(
        "strategies.sharp_rise_pullback_leader.strategy._load_qfq_5min_bars",
        return_value=(),
    )
    def test_buys_only_when_range_covers_bug_price(self, _minute_bars: object) -> None:
        context = self._context(trade_index=1, watch_pool={self.watch_item.code: self.watch_item})
        market = MarketViews(
            today_bars={self.watch_item.code: (105.0, 111.0, 104.0, 109.0, 1000.0, 0.0, 0.0, 104.0)}
        )

        decisions = self.lifecycle.decide_buys(context=context, market=market)

        self.assertEqual(len(decisions), 1)
        self.assertAlmostEqual(decisions[0].price, 110.0)
        self.assertGreater(decisions[0].quantity, 0)
        self.assertAlmostEqual(decisions[0].signal["extras"]["highest_price_since_buy"], 110.0)

    def test_l_low_invalidation_prevents_buy_and_removes_watch(self) -> None:
        context = self._context(trade_index=1, watch_pool={self.watch_item.code: self.watch_item})
        market = MarketViews(
            today_bars={self.watch_item.code: (105.0, 111.0, 99.0, 109.0, 1000.0, 0.0, 0.0, 104.0)}
        )

        self.assertEqual(self.lifecycle.decide_buys(context=context, market=market), [])
        watch = self.lifecycle.update_watch_pool(context=context, raw_signals=[], market=market)
        self.assertEqual(watch.remove, {self.watch_item.code})

    def test_full_day_gap_above_bug_price_removes_watch_without_buy(self) -> None:
        context = self._context(trade_index=1, watch_pool={self.watch_item.code: self.watch_item})
        market = MarketViews(
            today_bars={self.watch_item.code: (112.0, 115.0, 111.0, 114.0, 1000.0, 0.0, 0.0, 109.0)}
        )

        self.assertEqual(self.lifecycle.decide_buys(context=context, market=market), [])
        watch = self.lifecycle.update_watch_pool(context=context, raw_signals=[], market=market)
        self.assertEqual(watch.remove, {self.watch_item.code})

    def test_fifth_observation_day_expires_after_buy_attempt(self) -> None:
        context = self._context(trade_index=5, watch_pool={self.watch_item.code: self.watch_item})
        market = MarketViews(
            today_bars={self.watch_item.code: (105.0, 109.0, 104.0, 108.0, 1000.0, 0.0, 0.0, 104.0)}
        )
        watch = self.lifecycle.update_watch_pool(context=context, raw_signals=[], market=market)
        self.assertEqual(watch.remove, {self.watch_item.code})

    @patch(
        "strategies.sharp_rise_pullback_leader.strategy._load_qfq_5min_bars",
        return_value=(),
    )
    def test_trailing_drawdown_has_no_profit_activation_threshold(self, _minute_bars: object) -> None:
        holding = SimpleNamespace(
            buy_trade_index=0,
            buy_price=115.0,
            quantity=100,
            max_high_since_buy=120.0,
            signal={"extras": {"l_low": 90.0, "highest_price_since_buy": 120.0}},
        )
        context = self._context(trade_index=1, holdings={"sh.600000": holding})
        market = MarketViews(
            today_bars={"sh.600000": (119.0, 121.0, 115.0, 117.0, 1000.0, 0.0, 0.0, 118.0)}
        )

        decisions = self.lifecycle.decide_sells(context=context, market=market)

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].reason, "confirmed_high_drawdown_4pct")
        self.assertAlmostEqual(decisions[0].price, 115.2)

    @patch(
        "strategies.sharp_rise_pullback_leader.strategy._load_qfq_5min_bars",
        return_value=(),
    )
    def test_structure_stop_uses_close_at_or_below_l_low(self, _minute_bars: object) -> None:
        holding = SimpleNamespace(
            buy_trade_index=0,
            buy_price=100.0,
            quantity=100,
            max_high_since_buy=100.0,
            signal={"extras": {"l_low": 95.0, "highest_price_since_buy": 100.0}},
        )
        context = self._context(trade_index=1, holdings={"sh.600000": holding})
        market = MarketViews(
            today_bars={"sh.600000": (100.0, 101.0, 97.0, 95.0, 1000.0, 0.0, 0.0, 100.0)}
        )

        decisions = self.lifecycle.decide_sells(context=context, market=market)

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].reason, "close_at_or_below_l_low")
        self.assertAlmostEqual(decisions[0].price, 95.0)

    @patch(
        "strategies.sharp_rise_pullback_leader.strategy._load_qfq_5min_bars",
        return_value=(),
    )
    def test_daily_fallback_does_not_assume_new_high_precedes_same_day_low(self, _minute_bars: object) -> None:
        holding = SimpleNamespace(
            buy_trade_index=0,
            buy_price=100.0,
            quantity=100,
            max_high_since_buy=100.0,
            signal={"extras": {"l_low": 90.0, "highest_price_since_buy": 100.0}},
        )
        context = self._context(trade_index=1, holdings={"sh.600000": holding})
        market = MarketViews(
            today_bars={"sh.600000": (100.0, 110.0, 104.0, 105.0, 1000.0, 0.0, 0.0, 100.0)}
        )

        decisions = self.lifecycle.decide_sells(context=context, market=market)

        self.assertEqual(decisions, [])
        self.assertAlmostEqual(holding.signal["extras"]["highest_price_since_buy"], 110.0)

    @patch(
        "strategies.sharp_rise_pullback_leader.strategy._load_qfq_5min_bars",
        return_value=((100.0, 110.0, 97.0, 108.0),),
    )
    def test_five_minute_bar_does_not_use_its_new_high_before_its_low(self, _minute_bars: object) -> None:
        price, high = _trailing_exit_for_day(
            code="sh.600000",
            trade_date=date(2026, 7, 15),
            known_high=100.0,
            daily_bar=(100.0, 110.0, 97.0, 108.0, 1000.0, 0.0, 0.0, 100.0),
        )
        self.assertIsNone(price)
        self.assertAlmostEqual(high, 110.0)

    def _context(
        self,
        *,
        trade_index: int,
        holdings: dict[str, object] | None = None,
        watch_pool: dict[str, object] | None = None,
    ) -> StrategyContext:
        return StrategyContext(
            trade_date=date(2026, 7, 15),
            trade_index=trade_index,
            cash=100_000.0,
            total_asset=100_000.0,
            holdings=holdings or {},
            watch_pool=watch_pool or {},
            trade_records={"buys": [], "sells": []},
            params={"run_no": 1},
        )


if __name__ == "__main__":
    unittest.main()
