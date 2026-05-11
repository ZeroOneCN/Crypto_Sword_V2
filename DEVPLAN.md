# 三策略组合系统改造执行清单

## 执行约束

- [x] 严格按阶段顺序执行，不跳阶段、不并行跨阶段收尾。
- [x] 每个阶段必须实现、验证通过后才能勾选完成。
- [x] 每个阶段完成后立即更新本文档、使用中文 commit，并立刻 push。
- [x] commit 命名采用模块动作式，不使用 `fix`、`feat` 等英文前缀。
- [x] 当前阶段保留一币一主策略，不实现同币多策略叠仓。
- [x] 历史数据兼容优先，允许通过回落归因规则兼容旧数据。

## 当前代码基线

- [x] 当前主扫描链路只支持单 `scoring.active_preset` 驱动。
- [x] `orders.strategy_name` 已可承接订单级策略归因。
- [x] `positions` 当前没有 `strategy_id` 或等价明确策略字段。
- [x] `cryptopilot/persistence/reports.py` 已具备按 `strategy_name` 聚合的基础能力。
- [x] `cryptopilot/risk/exit_manager.py` 当前是全局 TP/SL 模板，不是分策略模板。
- [x] `Signal` 已包含 `strategy_id`、`preset`、`score`、`top_factors` 字段，可作为多策略链路信号载体。
- [x] `cryptopilot/web/health.py` 与 dashboard 当前仍以单 preset 视图为主。

## 阶段一：整理清单并锁定基线

- [x] 将文档改造成“阶段标题 + 可勾选步骤 + 完成说明”的执行清单结构。
- [x] 固定执行约束，写明阶段顺序、勾选规则、提交推送要求。
- [x] 按当前项目真实结构拆分阶段：
  - 多策略主链路
  - 持仓归因与数据库
  - 分策略风控参数
  - 分策略报表
  - Web/Telegram 展示
  - 验证与收尾
- [x] 锁定当前代码基线，写明单 `active_preset`、`orders.strategy_name`、`positions` 缺失策略字段、`reports.py` 聚合基础、`ExitManager` 全局模板等事实。

完成说明：`DEVPLAN.md` 已重构为可执行清单，基线已按当前代码核对锁定。
验证结果：已核对 `config.yaml`、`cryptopilot/main.py`、`cryptopilot/persistence/models.py`、`cryptopilot/persistence/reports.py`、`cryptopilot/risk/exit_manager.py`。

## 阶段二：主扫描链路升级为三策略并跑

- [ ] 将 `config.yaml` 从单 `active_preset` 升级为多 preset 启用配置。
- [ ] 保留 `ambush`、`chase`、`composite` 现有因子与阈值定义。
- [ ] 为每个 preset 增加以下配置：
  - 是否启用
  - 风险预算
  - 最大并发数
  - 退出模板名或退出参数组
- [ ] 调整 `cryptopilot/main.py` 扫描启动逻辑，不再只读取单个 `active_preset`。
- [ ] 为每个启用 preset 启动独立评分执行链，或实现等价的多模板评分流程。
- [ ] 确保所有发出的信号稳定带上：
  - `strategy_id`
  - `preset`
  - `score`
  - `top_factors`
- [ ] 明确一币一主策略规则：
  - 同一币同一方向同时命中多个策略时，只允许一个主策略实际开仓
  - 其他策略记录为支持信号或拒绝原因
- [ ] 主策略选择规则固定如下：
  - 费率 / OI 挤空型优先 `chase`
  - 低市值横盘蓄势型优先 `ambush`
  - 其他归 `composite`
  - 若当前代码短期无法稳定识别机会类型，则先按得分最高策略优先，并记录竞争策略列表

完成说明：待完成。
验证结果：待完成后补充。

## 阶段三：持仓、订单、事件统一补齐策略归因

- [ ] 为 `cryptopilot/persistence/models.py` 中 `positions` 增加明确策略归因字段。
- [ ] 更新相关 repository 与持仓同步逻辑，确保持仓记录稳定写入策略归因。
- [ ] 保留现有 `entry_reason` / `exit_reason` 字段，不再只依赖它们间接推断策略来源。
- [ ] 确保开仓后同步持仓时把 `strategy_id` 写入持仓记录。
- [ ] 确保平仓时优先从持仓记录继承策略归因，而不是只依赖 close signal comment。
- [ ] 统一记录以下策略事件：
  - 开仓成功
  - 保护单挂出
  - 部分止盈
  - 移动止损
  - 超时退出
  - 信号被拒绝
- [ ] 写清历史数据回落规则：
  - 历史持仓 / 历史已平仓若无策略字段，先回落到 `entry_reason`
  - 若 `entry_reason` 不足，再回落到 `orders.strategy_name`
- [ ] 保证回落逻辑写入实现与本文档，避免后续归因歧义。

完成说明：待完成。
验证结果：待完成后补充。

## 阶段四：分策略风控与退出模板落地

- [ ] 继续复用 `cryptopilot/risk/exit_manager.py` 现有退出能力，不另起一套退出系统。
- [ ] 升级为按策略注入退出参数，不再使用单一全局 TP 模板。
- [ ] 在配置与代码中明确三套模板：
  - `ambush`：更远 TP2/TP3、更长 sideways defense / timeout、更宽 trailing、更高 trailing activation、更小单笔风险
  - `chase`：更近 TP1/TP2、更短 sideways defense / timeout、更紧 trailing、更强时效退出
  - `composite`：中档模板
- [ ] 开仓 sizing 继续沿用当前 `position_sizer` 思路，通过止损距离反推仓位。
- [ ] 保持一币一主仓，不支持同币多策略叠仓。
- [ ] 落地总组合风险控制：
  - 每策略风险预算
  - 每策略最大并发
  - 单币上限
- [ ] 同题材总风险上限若当前代码暂不支持，先在实现注释和本文档中标为后续扩展，不阻塞本阶段交付。

完成说明：待完成。
验证结果：待完成后补充。

## 阶段五：报表、健康接口、网页端、Telegram 按策略展示

- [ ] 升级 `cryptopilot/persistence/reports.py`，在现有 `strategies` 聚合基础上补齐每策略统计指标。
- [ ] 每策略指标固定包含：
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
- [ ] 保持现有总览报表兼容，不删除总览指标。
- [ ] 升级 `cryptopilot/web/health.py`：
  - `/health/strategy` 返回多策略启用状态、阈值、风控模板摘要
  - `positions` 响应增加策略字段
  - `signals` / `trades` / `logs` 尽量暴露策略归因
- [ ] 升级 dashboard 与预览页：
  - 当前持仓增加“策略”列
  - 系统状态增加“启用策略与预算”
  - 交易绩效增加“按策略拆分”
  - 候选 / 信号日志展示 `preset` 或 `strategy_id`
  - 预览页与正式 dashboard 结构同步
- [ ] 升级 Telegram：
  - 启动消息展示多策略启用状态，而不是单 preset
  - 开仓通知明确策略来源和机会类型
  - 平仓通知继承持仓策略归因
  - 每日报告增加分策略盈利摘要

完成说明：待完成。
验证结果：待完成后补充。

## 阶段六：验证、勾选、提交与推送

- [ ] 每阶段完成后执行基础校验：
  - `python -m compileall -q cryptopilot preview_dashboard.py`
  - 相关 health 接口检查
  - 预览页与正式 dashboard 检查
- [ ] 每阶段完成后将对应阶段和子项从 `- [ ]` 改为 `- [x]`。
- [ ] 每阶段末补充“完成说明 / 验证结果”。
- [ ] 每阶段完成后使用中文 commit，命名采用模块动作式。
- [ ] 每阶段完成后立即 push，不累计到最后一次性推送。
- [ ] 验收场景必须覆盖：
  - 单个币被多个策略同时命中时，只会有一个主策略实际开仓
  - 当前持仓能明确显示所属策略
  - 平仓后报表中的策略统计与开仓归因一致
  - `ambush`、`chase`、`composite` 的 TP/SL 模板实际不同
  - health 接口返回多策略状态而不是单 preset
  - dashboard 能看到分策略信息
  - Telegram 开仓 / 平仓 / 日报都能按策略识别
  - 历史无 `strategy_id` 数据不会导致报表报错，且能按回落规则展示
  - 预览页与正式 dashboard 同步看到新结构

完成说明：待完成。
验证结果：待完成后补充。
