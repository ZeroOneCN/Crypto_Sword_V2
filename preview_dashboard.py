"""Standalone dashboard preview with mock data."""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from cryptopilot.web.dashboard import DASHBOARD_HTML

app = FastAPI(docs_url=None, redoc_url=None)

_MOCK_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT",
    "MOCAUSDT", "PROVEUSDT", "HOTUSDT", "ALLUSDT", "LINKUSDT",
]

_MOCK_POSITIONS = [
    {
        "symbol": "MOCAUSDT", "side": "LONG", "qty": 150.0, "leverage": 2,
        "entry_price": 0.06230, "mark_price": 0.06415, "unrealized_pnl": 27.75,
        "roi_pct": 5.94, "margin_type": "cross", "notional": 9.62,
        "strategy_preset": "ambush", "support_presets": "composite",
        "opened_at": (datetime.now(tz=timezone.utc) - timedelta(hours=3, minutes=12)).isoformat(),
        "hold_seconds": 11520, "sl_price": 0.05850, "tp_price": 0.07150,
    },
    {
        "symbol": "PROVEUSDT", "side": "LONG", "qty": 50.0, "leverage": 2,
        "entry_price": 0.2150, "mark_price": 0.2098, "unrealized_pnl": -2.60,
        "roi_pct": -4.84, "margin_type": "cross", "notional": 10.49,
        "strategy_preset": "composite", "support_presets": "",
        "opened_at": (datetime.now(tz=timezone.utc) - timedelta(minutes=47)).isoformat(),
        "hold_seconds": 2820, "sl_price": 0.1980, "tp_price": 0.2400,
    },
    {
        "symbol": "HOTUSDT", "side": "SHORT", "qty": 3200.0, "leverage": 2,
        "entry_price": 0.00312, "mark_price": 0.00305, "unrealized_pnl": 2.24,
        "roi_pct": 4.49, "margin_type": "cross", "notional": 9.76,
        "strategy_preset": "chase", "support_presets": "",
        "opened_at": (datetime.now(tz=timezone.utc) - timedelta(days=1, hours=5)).isoformat(),
        "hold_seconds": 104400, "sl_price": 0.00330, "tp_price": 0.00280,
    },
]


def _mock_health():
    return {"websocket_connected": True, "version": "2.0.0-preview"}


def _mock_account():
    return {
        "total_balance": 97.00,
        "available_balance": 66.61,
        "unrealized_pnl": 27.39,
        "margin_ratio": 0.0057,
        "margin_ratio_str": "0.57%",
        "margin_display": "USDT 全仓 0.57%",
        "maintenance_margin": 0.5510,
        "margin_balance": 96.19,
        "margin_type": "cross",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


def _mock_circuit():
    return {"tripped": False, "loss_pct": 0.0}


def _mock_strategy():
    return {
        "preset": "composite",
        "enabled_presets": ["ambush", "chase", "composite"],
        "buy_threshold": 45,
        "sell_threshold": -45,
        "preset_details": {
            "ambush": {
                "risk_budget": 0.25, "max_concurrent": 2, "exit_template": "ambush",
                "stop_loss_pct": 7.5, "tp1_pct": 4.0, "tp2_pct": 9.0, "tp3_pct": 15.0,
            },
            "chase": {
                "risk_budget": 0.25, "max_concurrent": 2, "exit_template": "chase",
                "stop_loss_pct": 4.5, "tp1_pct": 2.0, "tp2_pct": 4.0, "tp3_pct": 6.0,
            },
            "composite": {
                "risk_budget": 0.50, "max_concurrent": 4, "exit_template": "composite",
                "stop_loss_pct": 5.5, "tp1_pct": 3.0, "tp2_pct": 6.0, "tp3_pct": 10.0,
            },
        },
    }


def _mock_candidates():
    cands = []
    for sym in _MOCK_SYMBOLS[:10]:
        change = round(random.uniform(-8, 15), 2)
        direction = "LONG" if change > 0 else "HOLD"
        cands.append({
            "symbol": sym,
            "price": round(random.uniform(0.01, 85000), 4),
            "change_24h": change,
            "scanner_score": random.randint(30, 85),
            "composite_score": random.randint(20, 100),
            "preset_scores": {
                "ambush": random.randint(20, 100),
                "chase": random.randint(20, 100),
                "composite": random.randint(20, 100),
            },
            "direction": direction,
            "confidence": round(random.uniform(0.3, 1.0), 2) if direction == "LONG" else 0,
        })
    return {"candidates": cands, "total": len(cands)}


def _mock_signals():
    now = datetime.now(tz=timezone.utc)
    return {
        "signals": [
            {
                "time": now.isoformat(),
                "symbol": "ALLUSDT",
                "action": "OPEN_LONG",
                "score": 85,
                "detail": "市值+横盘共振，主策略开仓",
                "preset": "ambush",
                "strategy_id": "ambush_ALLUSDT",
                "supporting_presets": ["composite"],
                "opportunity_type": "ambush",
            },
            {
                "time": (now - timedelta(seconds=30)).isoformat(),
                "symbol": "TUSDT",
                "action": "OPEN_LONG",
                "score": 55.7,
                "detail": "已达策略最大并发数",
                "preset": "chase",
                "strategy_id": "chase_TUSDT",
                "supporting_presets": [],
                "opportunity_type": "chase",
            },
            {
                "time": (now - timedelta(minutes=1)).isoformat(),
                "symbol": "DEXEUSDT",
                "action": "OPEN_LONG",
                "score": 72,
                "detail": "费率与成交量共振",
                "preset": "composite",
                "strategy_id": "composite_DEXEUSDT",
                "supporting_presets": ["chase"],
                "opportunity_type": "composite",
            },
        ],
        "total": 3,
    }


def _mock_trades():
    trades = []
    for i in range(10):
        preset = random.choice(["ambush", "chase", "composite"])
        side = random.choice(["BUY", "SELL"])
        trades.append({
            "filled_at": (datetime.now(tz=timezone.utc) - timedelta(minutes=i * 20)).isoformat(),
            "symbol": random.choice(_MOCK_SYMBOLS[:5]),
            "side": side,
            "price": round(random.uniform(0.01, 3000), 5),
            "qty": round(random.uniform(10, 500), 4),
            "commission": round(random.uniform(0.01, 0.5), 6),
            "strategy_name": preset,
            "strategy_id": f"{preset}_{random.choice(_MOCK_SYMBOLS[:5])}",
            "preset": preset,
            "type": "MARKET",
        })
    return {"trades": trades, "total": len(trades)}


def _mock_orders():
    return {
        "total": 10,
        "total_algo_orders": 3,
        "by_symbol": [
            {"symbol": "MOCAUSDT", "stop_orders": 1, "tp_orders": 3, "total": 4},
            {"symbol": "PROVEUSDT", "stop_orders": 1, "tp_orders": 3, "total": 4},
            {"symbol": "HOTUSDT", "stop_orders": 1, "tp_orders": 1, "total": 2},
        ],
    }


def _mock_pnl():
    return {
        "net_pnl_1d": random.uniform(-5, 8),
        "net_pnl_7d": random.uniform(-15, 25),
        "net_pnl_30d": random.uniform(-30, 60),
        "net_pnl_total": random.uniform(-20, 80),
        "net_pnl_1d_pct": random.uniform(-5, 5),
        "net_pnl_7d_pct": random.uniform(-10, 12),
        "net_pnl_30d_pct": random.uniform(-18, 22),
        "net_pnl_total_pct": random.uniform(-25, 35),
        "trade_count_1d": random.randint(0, 5),
        "trade_count_7d": random.randint(4, 22),
        "trade_count_30d": random.randint(12, 60),
        "win_rate_1d": random.choice([0, 50, 100]),
        "win_rate_7d": random.uniform(40, 75),
        "win_rate_30d": random.uniform(42, 71),
        "commission_7d": random.uniform(0.5, 3.0),
        "funding_7d": random.uniform(-1, 0.5),
        "symbols_traded": random.randint(5, 15),
        "unrealized_pnl": random.uniform(-3, 9),
        "total_equity": random.uniform(92, 118),
    }


def _mock_positions():
    return {"positions": _MOCK_POSITIONS, "count": len(_MOCK_POSITIONS)}


def _mock_daily_pnl():
    days = []
    for i in range(30):
        days.append({
            "date": (datetime.now(tz=timezone.utc) - timedelta(days=29 - i)).strftime("%Y-%m-%d"),
            "pnl": round(random.uniform(-8, 12), 2),
            "trades": random.randint(0, 5),
        })
    return {"daily_pnl": days}


def _mock_report():
    strategies = {
        "ambush": {
            "trades": 6, "pnl": 18.42, "fee": 1.12, "win_rate": 66.7, "avg_hold_time": "9h40m",
            "avg_win": 7.18, "avg_loss": -5.66, "profit_factor": 1.94,
            "exit_reason_breakdown": {"TP_HIT": 3, "SIGNAL_CLOSE": 2, "SL_HIT": 1},
            "tp_hits": {"TP1": 4, "TP2": 2, "TP3": 1},
        },
        "chase": {
            "trades": 9, "pnl": 7.86, "fee": 1.84, "win_rate": 55.6, "avg_hold_time": "58m",
            "avg_win": 2.44, "avg_loss": -1.65, "profit_factor": 1.47,
            "exit_reason_breakdown": {"TP_HIT": 5, "SIGNAL_CLOSE": 3, "SL_HIT": 1},
            "tp_hits": {"TP1": 6, "TP2": 3, "TP3": 0},
        },
        "composite": {
            "trades": 11, "pnl": 12.73, "fee": 2.11, "win_rate": 63.6, "avg_hold_time": "3h24m",
            "avg_win": 3.91, "avg_loss": -2.18, "profit_factor": 1.81,
            "exit_reason_breakdown": {"TP_HIT": 6, "SIGNAL_CLOSE": 4, "SL_HIT": 1},
            "tp_hits": {"TP1": 7, "TP2": 4, "TP3": 2},
        },
    }
    trades = []
    for i in range(8):
        strategy = random.choice(["ambush", "chase", "composite"])
        trades.append({
            "symbol": random.choice(_MOCK_SYMBOLS[:6]),
            "side": random.choice(["LONG", "SHORT"]),
            "strategy": strategy,
            "entry_price": round(random.uniform(0.01, 100), 4),
            "exit_price": round(random.uniform(0.01, 100), 4),
            "pnl": round(random.uniform(-8, 16), 2),
            "pnl_pct": round(random.uniform(-12, 18), 2),
            "opened_at": (datetime.now(tz=timezone.utc) - timedelta(hours=i + 2)).isoformat(),
            "closed_at": (datetime.now(tz=timezone.utc) - timedelta(hours=i)).isoformat(),
            "hold_seconds": random.randint(900, 36000),
            "exit_reason": random.choice(["TP_HIT", "SIGNAL_CLOSE", "SL_HIT"]),
            "tp_tiers_hit": random.choice([["TP1"], ["TP1", "TP2"], ["TP1", "TP2", "TP3"], []]),
        })
    return {
        "total_trades": 26,
        "winning_trades": 16,
        "losing_trades": 10,
        "win_rate": 61.5,
        "total_pnl": 39.01,
        "total_pnl_pct": 18.42,
        "avg_win": 4.33,
        "avg_loss": -2.61,
        "avg_hold_time_seconds": 12180,
        "profit_factor": 1.77,
        "max_drawdown_pct": 8.6,
        "sharpe_ratio": 2.18,
        "start_balance": 78.40,
        "current_balance": 97.00,
        "strategies": strategies,
        "trades": trades,
        "daily_pnl": _mock_daily_pnl()["daily_pnl"],
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _mock_margin():
    return {"running": True, "warning_threshold": 0.80, "critical_threshold": 0.90}


def _mock_logs(lines: int = 200):
    now = datetime.now(tz=timezone.utc)
    rows = []
    count = max(1, min(int(lines or 200), 200))
    for i in range(count):
        ts = (now - timedelta(seconds=i * 5)).strftime("%H:%M:%S")
        level = random.choices(["INFO", "INFO", "INFO", "WARNING", "DEBUG"], weights=[5, 5, 3, 1, 2])[0]
        messages = {
            "INFO": [
                "评分心跳: 候选池=18个，本轮评分=3个",
                "雷达信号: ambush OPEN_LONG score=72.3 support=composite",
                "行情数据已就绪: 89个币种",
                "WS 交易客户端已连接 (0 权重下单)",
                "账户快照: 余额=97.00，可用=66.61，浮盈=27.39",
            ],
            "WARNING": [
                "信号被拒绝: chase 已达最大并发数 TUSDT OPEN_LONG",
                "横盘防守: MOCAUSDT 止损已收紧至保本位",
            ],
            "DEBUG": [
                "Algo orders fetch skipped",
                "缓存命中 MOCAUSDT_1m_50",
            ],
        }
        rows.append({"time": ts, "level": level, "msg": random.choice(messages[level])})
    return {"lines": rows, "file": "logs/engine.log (preview)"}


@app.get("/", response_class=HTMLResponse)
async def root():
    return DASHBOARD_HTML


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/health")
async def health():
    return _mock_health()


@app.get("/health/account")
async def health_account():
    return _mock_account()


@app.get("/health/positions")
async def health_positions():
    return _mock_positions()


@app.get("/health/circuit")
async def health_circuit():
    return _mock_circuit()


@app.get("/health/strategy")
async def health_strategy():
    return _mock_strategy()


@app.get("/health/candidates")
async def health_candidates():
    return _mock_candidates()


@app.get("/health/signals")
async def health_signals():
    return _mock_signals()


@app.get("/health/trades")
async def health_trades():
    return _mock_trades()


@app.get("/health/orders")
async def health_orders():
    return _mock_orders()


@app.get("/health/pnl")
async def health_pnl():
    return _mock_pnl()


@app.get("/health/volume")
async def health_volume():
    return {
        "volume_1d": random.uniform(100, 1200),
        "volume_7d": random.uniform(3000, 9000),
        "volume_30d": random.uniform(9000, 38000),
        "volume_total": random.uniform(18000, 85000),
        "trades_1d": random.randint(0, 5),
        "trades_7d": random.randint(6, 24),
        "trades_30d": random.randint(18, 80),
        "trades_total": random.randint(30, 180),
    }


@app.get("/health/report")
async def health_report():
    return _mock_report()


@app.get("/health/report/30d")
async def health_report_30d():
    return {"daily_pnl": _mock_report()["daily_pnl"]}


@app.get("/health/margin")
async def health_margin():
    return _mock_margin()


@app.get("/health/logs")
async def health_logs(lines: int = 200):
    return _mock_logs(lines)


if __name__ == "__main__":
    import uvicorn

    print("仪表盘预览模式启动: http://localhost:1689")
    uvicorn.run(app, host="0.0.0.0", port=1689, log_level="warning")
