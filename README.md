# CryptoPilot — 币安自动交易系统

基于 Binance 合约/现货的自动化交易程序。异步事件驱动架构，集成 WebSocket 实时行情、模块化策略引擎、多层风控、Telegram 通知、SQLite 持久化以及 Web 仪表盘。

---

## 环境要求

- Python 3.10+
- Windows / Linux / macOS
- Binance 账户（建议先用测试网验证）
- （可选）Telegram Bot Token，用于消息推送

---

## 快速开始

### 1. 进入项目目录

```bash
cd CryptoPilot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 Binance API 密钥和加密密码
```

编辑 `config.yaml`：
- `exchange.testnet: true` 使用测试网
- `exchange.trading_type: futures` 或 `spot`
- 在 `strategies` 下配置要运行的策略

### 4. 首次运行 — 加密 API 密钥

首次运行时，程序会从 `.env` 读取 API 密钥，用 AES-256-GCM 加密后存入 `data/keys.enc`。后续运行直接从磁盘解密，`.env` 中的密钥可删除。

### 5. 启动

**Windows：**
```bash
python -m cryptopilot.main
```

**Linux/macOS：**
```bash
chmod +x start.sh
./start.sh
```

### 6. 验证

```bash
curl http://localhost:1688/health
```

浏览器打开 `http://localhost:1688/` 可查看实时仪表盘。

---

## 架构

```
WebSocket 行情数据
        │
        ▼
┌──────────────────┐
│  MarketDataCache  │ ← K线 / Ticker / 深度
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────┐
│  StrategyEngine   │────▶│  信号队列     │
│  (4 种内置策略)    │     └──────┬───────┘
└──────────────────┘            │
                                ▼
┌──────────────────────────────────────────┐
│           OrderExecutor                    │
│  市价 · 限价 · OCO · 止损 · 止盈           │
│  ┌──────────┐  ┌──────────────┐          │
│  │ SL / TP  │  │ OCO (二合一)  │          │
│  │ (并行下单) │  │  (自动互撤)   │         │
│  └──────────┘  └──────────────┘          │
└────────────────┬─────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌───────┐  ┌──────────┐  ┌──────────┐
│仓位管理│  │订单管理   │  │限速器    │
└───┬───┘  └────┬─────┘  └──────────┘
    │           │
    ▼           ▼
┌──────────────────────────────────────┐
│              SQLite 数据库             │
│  orders · fills · positions · account │
└──────────────────┬───────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌────────────┐  ┌─────────┐
│Telegram│  │健康检查 API │  │仪表盘    │
│  Bot   │  │ :1688/health│  │ :1688/  │
└────────┘  └────────────┘  └─────────┘
```

---

## 配置说明

### `.env` — 密钥（切勿提交到 Git）

| 变量 | 说明 |
|----------|------|
| `BINANCE_API_KEY` | 币安 API Key（仅开交易权限，不开提币） |
| `BINANCE_API_SECRET` | API Secret |
| `ENCRYPTION_PASSWORD` | 本地 AES 加密密钥的密码 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（可选） |
| `TELEGRAM_CHAT_ID` | 推送目标 Chat ID |
| `TELEGRAM_ALLOWED_USERS` | 允许交互的用户名，逗号分隔 |

### `config.yaml` — 应用设置

```yaml
exchange:
  testnet: true              # true = 测试网, false = 实盘
  trading_type: futures      # futures 或 spot

risk:
  max_daily_loss_pct: 2.0    # 熔断阈值：当日亏损超过此百分比即停止交易
  max_positions: 5           # 最大同时持仓数
  max_position_pct: 20       # 单币种最大仓位占比（%）
  max_leverage: 10           # 杠杆硬上限
  default_leverage: 3        # 默认杠杆

websocket:
  streams: [kline_1m, ticker]  # kline_1m, kline_5m, kline_1h, ticker, depth
  reconnect_max_attempts: 100
  reconnect_base_delay: 1       # 秒，指数退避，上限 60s

order:
  default_type: market
  rate_limit_weight_per_minute: 1200

notification:
  telegram_enabled: false

web:
  host: 127.0.0.1
  port: 1688

logging:
  level: INFO
  retention_days: 30
```

---

## 内置策略

### 1. `ma_crossover` — 双均线交叉
快线上穿慢线 → 做多。快线下穿慢线 → 做空。

```yaml
strategies:
  - name: ma_crossover
    symbol: BTCUSDT
    parameters:
      fast_ma: 7
      slow_ma: 25
      interval: 1m
    risk:
      leverage: 3
      stop_loss_pct: 2
      take_profit_pct: 5
```

### 2. `rsi` — RSI 超买超卖反转
RSI 上穿超卖线 → 做多。下穿超买线 → 做空。

```yaml
  - name: rsi
    symbol: ETHUSDT
    parameters:
      period: 14
      oversold: 30
      overbought: 70
      interval: 5m
```

### 3. `bollinger_breakout` — 布林带突破
价格突破上轨 → 做多。跌破下轨 → 做空。

```yaml
  - name: bollinger_breakout
    symbol: BTCUSDT
    parameters:
      period: 20
      num_std: 2.0
      interval: 5m
```

### 4. `volume_breakout` — 成交量异动
成交量超过均量 N 倍 → 跟随价格方向开仓。

```yaml
  - name: volume_breakout
    symbol: BTCUSDT
    parameters:
      lookback: 20
      volume_mult: 2.5
      min_price_move_pct: 0.3
      interval: 5m
```

---

## 风控体系

| 功能 | 说明 |
|---------|-------------|
| **硬止损** | 每次开仓自动向交易所提交 `STOP_MARKET` 订单，程序崩溃也生效 |
| **止盈单** | 开仓同时挂 `TAKE_PROFIT_MARKET` 订单 |
| **OCO 订单** | 止损/止盈二选一触发，另一方自动撤销 |
| **移动止损** | 内存跟踪，随价格有利方向逐步上移止损位 |
| **熔断机制** | 当日亏损超过阈值 → 停止所有策略，紧急平仓 |
| **保证金监控** | 每 30 秒检查保证金率与强平距离，80% 警告、90% 紧急减仓 |
| **锁利机制** | 浮盈达标 → 自动平掉部分仓位 + 移动止损至保本 |
| **限速器** | 滑动窗口权重计数，遵守币安 API 频率限制 |

---

## 健康检查与仪表盘

浏览器访问 `http://localhost:1688/` 查看实时仪表盘。

| API 接口 | 说明 |
|--------------|-------------|
| `GET /health` | 系统状态（OK / DEGRADED） |
| `GET /health/strategies` | 所有策略状态 |
| `GET /health/positions` | 当前持仓及浮动盈亏 |
| `GET /health/circuit` | 熔断器状态 |
| `GET /health/margin` | 保证金监控阈值 |
| `GET /health/report` | 完整交易报表 |
| `GET /health/report/summary` | 轻量级交易摘要 |

### 报表指标

- 总交易 / 盈利 / 亏损笔数
- 胜率 (%)
- 总盈亏 ($)
- 平均盈利 / 平均亏损
- 盈亏比（Profit Factor）
- 最大回撤 (%)
- 年化夏普比率

---

## Telegram Bot

### 配置

1. 通过 [@BotFather](https://t.me/BotFather) 创建 Bot
2. 将 Token 和 Chat ID 填入 `.env`
3. `config.yaml` 中设置 `notification.telegram_enabled: true`

### 交互指令

| 指令 | 功能 |
|---------|--------|
| `/status` | 查看策略状态 |
| `/pause` | 暂停所有策略 |
| `/resume` | 恢复所有策略 |
| `/close_all` | 紧急平掉全部仓位 |
| `/help` | 显示可用指令 |

### 自动推送

- 订单成交（价格、数量、方向）
- 开仓 / 平仓及盈亏
- 熔断触发
- 策略异常
- 每日净值总结（定时推送）

---

## 进程守护（崩溃自动重启）

### Windows

以管理员身份运行：

```powershell
powershell -ExecutionPolicy Bypass -File daemon_setup.ps1
```

将 CryptoPilot 注册为计划任务：
- 开机自启
- 崩溃后 5 秒自动重启
- 以 SYSTEM 账户运行

```powershell
# 查看状态
Get-ScheduledTask -TaskName CryptoPilot | Select State

# 启动 / 停止
Start-ScheduledTask -TaskName CryptoPilot
Stop-ScheduledTask -TaskName CryptoPilot

# 移除
Unregister-ScheduledTask -TaskName CryptoPilot -Confirm:$false
```

### Linux

```bash
# 安装 supervisor
sudo apt install supervisor

# 复制配置
sudo cp supervisor.conf /etc/supervisor/conf.d/cryptopilot.conf

# 编辑配置中的路径和用户名
sudo nano /etc/supervisor/conf.d/cryptopilot.conf

# 启动
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl start cryptopilot
```

---

## 数据库

**5 张表**存储在 `data/crypto_pilot.db`（SQLite，WAL 模式）：

| 表名 | 主要字段 |
|-------|------------|
| `orders` | symbol, strategy_name, side, type, price, qty, status, client_order_id |
| `fills` | order_id, price, qty, commission |
| `positions` | symbol, side, qty, entry_price, mark_price, leverage, liquidation_price |
| `account_snapshots` | total_balance, available_balance, unrealized_pnl, margin_ratio |
| `strategy_events` | strategy_id, event_type, symbol, details (JSON) |

所有时间均为 ISO 8601 UTC 格式。日志每日 0 点滚动，保留 30 天。

---

## 添加新策略

1. 在 `cryptopilot/strategy/examples/` 下创建新文件

2. 继承 `StrategyBase` 并实现核心方法：
   ```python
   class MyStrategy(StrategyBase):
       async def on_init(self) -> None:
           # 加载历史数据，初始化指标
           ...

       async def on_kline(self, kline: KlineData) -> None:
           # 每根新 K 线更新指标
           ...

       async def on_signal(self) -> Signal | None:
           # 返回交易信号或 None
           return Signal(
               strategy_id=self.strategy_id,
               symbol=self.symbol,
               action="OPEN_LONG",  # OPEN_LONG / OPEN_SHORT / CLOSE_LONG / CLOSE_SHORT
               order_type="MARKET",
               comment="交易理由",
           )
   ```

3. 在 `cryptopilot/main.py` 中注册：
   ```python
   from cryptopilot.strategy.examples.my_strategy import MyStrategy
   available_strategies["my_strategy"] = MyStrategy
   ```

4. 在 `config.yaml` 的 `strategies:` 下添加配置

---

## 风险警示

**本软件涉及真实资金交易。** 务必：

1. 先用 **币安测试网**（`exchange.testnet: true`）
2. 使用 **极小金额**（< 10 USDT 等值）测试
3. 验证所有流程无误后再放大
4. API Key **只开交易权限**，**不开提币权限**
5. API Key 绑定 **IP 白名单**
6. 初期密切监控系统运行

作者对任何资金损失概不负责，请自行承担风险。

---

## 项目文件结构

```
CryptoPilot/
├── config.yaml              # 非敏感配置
├── .env.example             # 密钥模板
├── .gitignore
├── requirements.txt
├── start.sh                 # Linux/macOS 一键启动
├── daemon_setup.ps1         # Windows 计划任务守护
├── supervisor.conf          # Linux supervisor 配置
├── README.md
│
├── cryptopilot/
│   ├── main.py              # 入口 — 组装所有模块
│   ├── core/                # 配置、日志、异常
│   ├── security/            # AES-256-GCM 密钥加密
│   ├── market/              # WebSocket 管理、行情缓存、数据类型
│   ├── strategy/            # 策略基类、引擎、4 个示例策略
│   ├── trading/             # 订单执行器（REST）、限速器、精度处理
│   ├── risk/                # 仓位计算、熔断、移动止损、保证金监控、锁利
│   ├── notification/        # 事件总线、Telegram Bot
│   ├── persistence/         # SQLite、数据仓库、交易报表
│   ├── web/                 # FastAPI 健康检查 + 仪表盘
│   └── utils/               # 时间与数字工具
│
└── data/                    # 运行时数据（自动创建）
    ├── keys.enc             # 加密后的 API 密钥
    ├── crypto_pilot.db      # SQLite 数据库
    └── logs/                # 每日日志
```
