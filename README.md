# CryptoPilot V2

CryptoPilot V2 是一个面向 Binance 合约的多策略自动交易系统。当前代码已经从单 `active_preset` 主链路，升级为三策略并跑模式：

- `ambush`：埋伏低市值、长时间横盘、等待启动的山寨币
- `chase`：追多，偏费率与 OI 驱动的短线挤空机会
- `composite`：综合评分，做均衡型机会筛选

系统包含以下核心能力：

- 多策略并行扫描、评分、主策略归因
- 基于可用余额与止损距离的动态仓位计算
- 分策略风险预算、并发上限、退出模板
- 持仓/订单/事件/报表/Telegram/网页端全链路策略归因
- FastAPI 仪表盘与预览页
- SQLite 持久化
- API Key 本地加密存储

---

## 1. 当前系统是怎么开仓的

这个项目不是“只看余额就无限开仓”，而是多层约束同时生效。

### 1.1 总持仓上限

配置项：

```yaml
risk:
  max_positions: 10
```

含义：

- 全局最多同时持有 `10` 个仓位
- 达到上限后，新的开仓信号会被拒绝

### 1.2 单策略并发上限

配置项在 `config.yaml -> scoring.presets`：

```yaml
scoring:
  presets:
    ambush:
      max_concurrent: 2
    chase:
      max_concurrent: 2
    composite:
      max_concurrent: 4
```

含义：

- `ambush` 最多同时开 `2` 个主仓
- `chase` 最多同时开 `2` 个主仓
- `composite` 最多同时开 `4` 个主仓

### 1.3 同币种不重复开主仓

系统会检查当前是否已经持有该币种仓位：

- 如果已有 `MOCAUSDT` 持仓，就不会再次为 `MOCAUSDT` 开主仓
- 即使这个币同时命中多个策略，也只允许一个主策略实际开仓

### 1.4 单仓大小由余额和风险参数共同决定

单仓不是固定张数，而是按 `available_balance` 计算，核心公式在 `cryptopilot/risk/position_sizer.py`：

```text
risk_amount = available_balance * risk_pct / 100
stop_distance = entry_price * stop_loss_pct / 100
risk_qty = risk_amount / stop_distance * leverage

max_notional = available_balance * max_position_pct / 100 * leverage
max_qty = max_notional / entry_price

final_qty = min(risk_qty, max_qty)
```

实际含义：

- 余额决定“这一仓最多能开多大”
- `risk_budget` / `risk_per_trade` 决定“愿意为这一仓亏多少钱”
- `stop_loss_pct` 越宽，仓位会自然变小
- `max_position_pct` 会限制单仓最大名义价值

结论：

- `max_positions` / `max_concurrent` / 同币已持仓检查，决定“还能不能继续开”
- `available_balance` + 风险参数，决定“每一仓开多大”

---

## 2. 项目目录

```text
AI_Trader/
├─ cryptopilot/              主程序
│  ├─ core/                  配置、日志、异常
│  ├─ exchange/              Binance REST / WS 交互
│  ├─ market/                行情缓存、扫描、轮询
│  ├─ risk/                  仓位控制、退出管理、风控
│  ├─ persistence/           SQLite 模型、仓储、报表
│  ├─ notification/          Telegram 通知
│  └─ web/                   dashboard 与 health API
├─ data/
│  ├─ crypto_pilot.db        SQLite 数据库
│  ├─ keys.enc               加密后的 API Key
│  └─ logs/                  运行日志
├─ config.yaml               主要业务配置
├─ .env                      敏感配置，不提交 Git
├─ .env.example              环境变量示例
├─ preview_dashboard.py      预览页入口，端口 1689
├─ DEVPLAN.md                改造执行文档
└─ README.md
```

---

## 3. 运行环境

建议环境：

- Python `3.10+`
- Windows PowerShell
- Binance Futures 账户
- Telegram Bot，可选

安装依赖：

```powershell
pip install -r requirements.txt
```

主要依赖包括：

- `fastapi`
- `uvicorn`
- `httpx`
- `websockets`
- `aiosqlite`
- `loguru`
- `pydantic`
- `python-telegram-bot`

---

## 4. 首次配置

### 4.1 配置 `.env`

先复制示例文件：

```powershell
Copy-Item .env.example .env
```

`.env` 里主要有这些变量：

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
ENCRYPTION_PASSWORD=your_strong_password
ENCRYPTION_SALT=your_random_salt
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ALLOWED_USERS=username1,username2
```

说明：

- `BINANCE_API_KEY` / `BINANCE_API_SECRET`：交易 API
- `ENCRYPTION_PASSWORD` / `ENCRYPTION_SALT`：本地加密密钥，建议自己替换为强随机值
- `TELEGRAM_*`：Telegram 通知相关，可选

注意：

- `.env` 已被 `.gitignore` 忽略，不要提交
- 当前 `.env.example` 只是模板，不建议原值直接用于正式环境

### 4.2 API Key 加密存储机制

程序首次启动时会做以下事情：

- 读取 `.env` 中的 Binance Key
- 使用 `AES-256-GCM` 加密后写入 `data/keys.enc`
- 后续运行优先从 `data/keys.enc` 解密加载

如果出现以下情况，程序会自动重新加密：

- `data/keys.enc` 不存在
- `.env` 中的 API Key 与当前加密存储不一致

---

## 5. 关键配置文件 `config.yaml`

这是项目最重要的业务配置文件。大部分调参都在这里完成。

### 5.1 交易所与运行环境

```yaml
exchange:
  testnet: false
  trading_type: futures
```

说明：

- `testnet: true`：测试网
- `testnet: false`：实盘
- `trading_type` 当前主要使用 `futures`

### 5.2 风控总开关

```yaml
risk:
  margin_type: crossed
  max_daily_loss_pct: 8.0
  max_positions: 10
  max_position_pct: 8
  max_leverage: 10
  default_leverage: 2
```

说明：

- `margin_type`：当前默认全仓
- `max_daily_loss_pct`：日内最大亏损百分比，触发后停止交易
- `max_positions`：总持仓上限
- `max_position_pct`：单仓最大资金占比
- `max_leverage`：杠杆硬上限
- `default_leverage`：默认杠杆

### 5.3 多策略扫描与启用方式

```yaml
scoring:
  active_preset: ambush
  buy_threshold: 50
  sell_threshold: -45
  min_confidence: 0.65
  top_k_per_preset: 3
  max_signals_per_cycle: 1
```

说明：

- 当前实际运行以 `scoring.presets.*.enabled` 为准
- `active_preset` 仍保留为兼容/默认展示字段，不再是唯一策略入口
- `top_k_per_preset`：每个策略保留多少个高分候选
- `max_signals_per_cycle`：每轮最多进入执行链路的信号数

### 5.4 三个策略的当前定位

#### `ambush`

适合：

- 小市值
- 长时间横盘
- 等待启动
- 想吃更远 TP 的机会

当前配置特点：

- `risk_budget: 0.25`
- `max_concurrent: 2`
- `stop_loss_pct: 7.5`
- `tp1/tp2/tp3: 4 / 9 / 15`
- 更宽 trailing
- 更长 sideways defense / timeout

#### `chase`

适合：

- 费率、OI、成交量共振
- 短线挤空或追多机会
- 讲究时效和执行速度

当前配置特点：

- `risk_budget: 0.25`
- `max_concurrent: 2`
- `stop_loss_pct: 4.5`
- `tp1/tp2/tp3: 2 / 4 / 6`
- 更紧 trailing
- 更短 sideways defense / timeout

#### `composite`

适合：

- 没有特别极端标签
- 需要综合资金费率、市值、OI、横盘、波动、均线等多因子平衡判断

当前配置特点：

- `risk_budget: 0.50`
- `max_concurrent: 4`
- `stop_loss_pct: 5.5`
- `tp1/tp2/tp3: 3 / 6 / 10`
- 风格介于 `ambush` 和 `chase` 之间

---

## 6. 如何启动

### 6.1 启动正式系统

```powershell
python -m cryptopilot.main
```

启动后会同时拉起：

- 主扫描与交易执行链路
- Binance 行情与账户同步
- FastAPI health 与正式 dashboard

默认正式地址：

- 仪表盘：[http://localhost:1688/](http://localhost:1688/)
- 健康检查：[http://localhost:1688/health](http://localhost:1688/health)

### 6.2 启动预览页

如果你只是想看前端布局，不想接交易所，可以单独启动：

```powershell
python preview_dashboard.py
```

预览地址：

- 预览页：[http://localhost:1689/](http://localhost:1689/)

说明：

- 预览页使用 mock 数据
- 正式 dashboard 和预览页共用同一套 `DASHBOARD_HTML` 模板
- 预览页适合调布局、模块位置、文案展示

---

## 7. 常用 health 接口

系统提供了比较完整的本地接口，便于排查和二次接入。

常用接口：

- `/health`：基础存活状态
- `/health/strategy`：当前多策略启用状态、阈值、退出模板摘要
- `/health/positions`：当前持仓，含策略字段、持仓时长、SL/TP
- `/health/orders`：当前挂单统计
- `/health/report`：综合报表
- `/health/report/today`
- `/health/report/7d`
- `/health/report/30d`
- `/health/signals`：近期信号
- `/health/candidates`：候选池
- `/health/trades`：近期成交
- `/health/logs?lines=200`：读取最近日志，便于排查异常

示例：

```powershell
curl http://localhost:1688/health/strategy
curl http://localhost:1688/health/positions
curl "http://localhost:1688/health/logs?lines=200"
```

---

## 8. 如何改参数

下面按实际运维最常改的参数分类说明。

### 8.1 开关某个策略

修改：

```yaml
scoring:
  presets:
    ambush:
      enabled: true
    chase:
      enabled: true
    composite:
      enabled: true
```

说明：

- 改为 `false` 就会停用该策略
- 启用状态会直接体现在 `/health/strategy` 和 dashboard

### 8.2 改总持仓上限

修改：

```yaml
risk:
  max_positions: 10
```

建议：

- 小资金先保守，例如 `3` 到 `5`
- 多策略并跑时，不建议一开始就拉得过高

### 8.3 改单策略并发上限

修改：

```yaml
scoring:
  presets:
    ambush:
      max_concurrent: 2
```

说明：

- 控制某一类策略最多同时占用多少个主仓
- 这个值过大，容易让单一风格占满总仓位

### 8.4 改单策略风险预算

修改：

```yaml
scoring:
  presets:
    composite:
      risk_budget: 0.50
```

说明：

- 这是单笔风险百分比
- 值越大，允许单仓亏损的预算越高
- 同时会直接影响 `PositionSizer` 计算出来的开仓数量

经验上：

- `ambush` 适合更小风险预算
- `chase` 和 `composite` 可以按执行风格微调

### 8.5 改止损与三段止盈

修改：

```yaml
scoring:
  presets:
    ambush:
      stop_loss_pct: 7.5
      tp1_pct: 4.0
      tp2_pct: 9.0
      tp3_pct: 15.0
      tp1_ratio: 0.25
      tp2_ratio: 0.30
      tp3_ratio: 0.45
```

说明：

- `stop_loss_pct`：止损宽度
- `tp1_pct/tp2_pct/tp3_pct`：三档止盈目标
- `tp1_ratio/tp2_ratio/tp3_ratio`：每档平仓比例

建议：

- `ambush` 适合更远 TP、更宽止损、更长持仓
- `chase` 适合更近 TP、更紧止损、更快退出
- `composite` 适合中间值

### 8.6 改 trailing 和横盘退出

修改：

```yaml
scoring:
  presets:
    chase:
      trail_distance_pct: 1.2
      trail_activation_pct: 0.35
      sideways_defense_minutes: 30
      sideways_exit_minutes: 75
      sideways_range_pct: 1.2
      pre_tp_guard_min_roi_pct: 0.15
```

说明：

- `trail_distance_pct`：回撤多少触发移动止损
- `trail_activation_pct`：盈利达到多少后启用 trailing
- `sideways_defense_minutes`：横盘保护启动时机
- `sideways_exit_minutes`：横盘超时退出时机
- `sideways_range_pct`：横盘判定范围
- `pre_tp_guard_min_roi_pct`：到达 TP 前的最小收益保护阈值

### 8.7 改扫描阈值

修改：

```yaml
scoring:
  buy_threshold: 50
  sell_threshold: -45
  min_confidence: 0.65
  top_k_per_preset: 3
  max_signals_per_cycle: 1
```

说明：

- `buy_threshold` 越高，越难出开多信号
- `min_confidence` 越高，越严格
- `top_k_per_preset` 越高，每轮保留的候选越多
- `max_signals_per_cycle` 越高，每轮可能进入执行链路的信号越多

### 8.8 改单策略因子权重

示例：

```yaml
scoring:
  presets:
    chase:
      factors:
        - { name: funding, weight: 0.60 }
        - { name: volume, weight: 0.20 }
        - { name: oi, weight: 0.10 }
        - { name: anomaly, weight: 0.10 }
```

说明：

- `weight` 越大，说明这个因子对总评分影响越大
- 建议修改后观察 `/health/strategy` 与 `/health/candidates`

### 8.9 改 Telegram 开关

修改：

```yaml
notification:
  telegram_enabled: true
```

同时确保 `.env` 里已填：

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

---

## 9. 日常操作建议

### 9.1 首次启动流程

1. 配好 `.env`
2. 检查 `config.yaml`
3. 先用测试网或小资金运行
4. 启动 `python -m cryptopilot.main`
5. 打开 dashboard 检查 `/health/strategy`、`/health/positions`
6. 确认 Telegram 启动消息正常

### 9.2 调参后的标准动作

每次改完配置，建议至少做这几步：

```powershell
python -m compileall -q cryptopilot preview_dashboard.py
python preview_dashboard.py
python -m cryptopilot.main
```

然后检查：

- [http://localhost:1689/](http://localhost:1689/) 预览布局是否正常
- [http://localhost:1688/health/strategy](http://localhost:1688/health/strategy) 是否返回新策略参数
- [http://localhost:1688/health/logs?lines=200](http://localhost:1688/health/logs?lines=200) 是否有异常

### 9.3 实盘前重点检查

- `exchange.testnet` 是否为你想要的环境
- API Key 是否正确
- `risk.max_positions` 是否合理
- 各策略 `enabled` / `risk_budget` / `max_concurrent` 是否符合预期
- `max_position_pct` 与 `default_leverage` 是否过激进
- Telegram 是否开启并能收到消息

---

## 10. 网页端现在能看到什么

当前正式 dashboard 与预览页已经同步，重点模块包括：

- 系统状态
- 当前持仓
- 交易绩效
- 候选与信号
- 近期成交
- 30 天净盈亏轨迹
- 运行日志

其中多策略相关展示已包括：

- 持仓所属策略
- 启用策略与预算
- 按策略拆分的绩效
- 信号所属 `preset` / `strategy_id`
- 日志读取最近 `200` 行

---

## 11. 报表与策略归因

当前系统的统计不是只看订单，而是尽量走完整的策略归因链路：

- 开仓信号带 `strategy_id`、`preset`
- 持仓记录落库 `strategy_id` / `strategy_preset`
- 平仓继承持仓归因
- 报表按策略维度聚合
- Telegram 与 dashboard 统一展示策略来源

当前报表可关注的指标包括：

- `trades`
- `pnl`
- `fee`
- `win_rate`
- `avg_hold_time`
- `avg_win`
- `avg_loss`
- `profit_factor`
- `exit_reason breakdown`
- `TP1/TP2/TP3` 命中统计

---

## 12. 常见问题

### Q1：为什么有余额却不开仓？

常见原因：

- 已达到 `risk.max_positions`
- 已达到某个策略的 `max_concurrent`
- 该币种已有持仓
- 没过 `buy_threshold` / `min_confidence`
- 单仓数量算出来过小或为 0
- 风控开关触发，例如日内亏损超限

建议先看：

- `/health/strategy`
- `/health/positions`
- `/health/signals`
- `/health/logs?lines=200`

### Q2：为什么看到挂单，但没有当前持仓？

项目已经在 `orders` 接口里尽量过滤“无持仓的历史残留保护单”。如果仍看到异常，优先检查：

- 是否是交易所侧残留挂单
- 是否刚平仓但保护单未及时撤掉
- 是否是历史订单，不属于当前活跃持仓

### Q3：为什么改了参数页面没变化？

先确认：

- 是否已经重启正式进程
- 是否访问的是 `1688` 正式页还是 `1689` 预览页
- `/health/strategy` 返回是否已经变化

### Q4：预览页和正式页为什么要分开？

因为职责不同：

- `1688`：接真实运行数据
- `1689`：只看布局与 mock 数据

两者共用同一套 dashboard 模板，方便先调前端，再看正式效果。

---

## 13. 快速命令清单

安装依赖：

```powershell
pip install -r requirements.txt
```

语法快速检查：

```powershell
python -m compileall -q cryptopilot preview_dashboard.py
```

启动正式系统：

```powershell
python -m cryptopilot.main
```

启动预览页：

```powershell
python preview_dashboard.py
```

查看正式 health：

```powershell
curl http://localhost:1688/health
```

查看多策略状态：

```powershell
curl http://localhost:1688/health/strategy
```

查看最近 200 行日志：

```powershell
curl "http://localhost:1688/health/logs?lines=200"
```

---

## 14. 版本说明

当前 README 已按现有代码更新为三策略并跑口径，重点覆盖：

- 持仓上限与仓位计算
- `ambush / chase / composite` 三策略
- 分策略风控与退出参数
- 正式 dashboard 与预览页
- health 接口
- 参数修改方法
- 日常运维与排错流程

如果后续你继续调整策略结构，优先同步更新这几个文件：

- `config.yaml`
- `cryptopilot/core/config.py`
- `cryptopilot/main.py`
- `cryptopilot/web/health.py`
- `README.md`
