# research_lowvol/esb 预注册 — 宇宙替换 BTC→BNB(ETH/SOL/BNB),2026-11-08,先于回测写定

户主问题:去掉 BTC 换成 ETH/SOL/BNB,效果如何、要多少资金。

## 1. 注册设计

- **白名单替换**:`config_futures_esb.json` = config_futures.json 逐字复制,仅白名单
  BTC/ETH/SOL → ETH/SOL/BNB。
- **BTC 保留为外部参照物**(注册决策,不改):B 的 regime 门(BTC>SMA100×1.03)、
  A/C 的 recycle(RECYCLE_REF=BTC,informative 自动注入)、A/B 的 vt RV30(BTC 日线)
  全部继续由 BTC 驱动。A/C 引擎原生支持(informative_pairs 自动补 BTC 1h);
  B 需要注入子类 `ESB_B_2xvt`(复制 AB_RaySleeves.AB_Ray_B 的 _daily_closes 注入,
  LVG_B_2xvt 的 RV30 走文件级 feather,与白名单无关)。
- **数据**:BNB 1h futures/funding/mark/1d feather 已验证存在(LV1 报告:12 币无缺口)。

## 2. 变体(3 次回测 + 1 组合格,全跑全披露)

| # | 策略 | 白名单 |
|---|---|---|
| E1 | LVG_A_vt60f1 | ESB |
| E2 | ESB_B_2xvt(注入子类,新文件) | ESB |
| E3 | SlowA_12h_r3 | ESB |
| 组装 | ABC-ESB = E1 30% / E2 30% / E3 40%,月度再平衡 | — |

口径同前(wallet 10000、fee 0.0005、timerange 20210101-20261107、--cache none、含 funding)。

## 3. 验收(跑前冻结)

- R1(信息性对照):ABC-ESB vs ABC(BTC/ETH/SOL)逐年 + 全窗 + dd30 对照表
- R2(门槛参考):ESB-ABC 2025≥+36 且 2026≥+22;dd30≥-30
- R3:无论结果,**不替换冠军 cell49**(宇宙替换属新假设,与冠军同等待遇:要换只能进影子);
  若 ESB 显著更差 → 记录证伪;若更好 → 记录为候选,入影子,同样打折

## 4. 风险(跑前)

- 选择效应:宇宙替换是在看过 BTC 宇宙结果之后提出的,方向性偏差不可排除
- BNB 特有风险:交易所代币的监管/事件冲击(2023 SEC 诉讼型崩跌在样本内)、
  2021 BNB 暴涨年可能过度贡献
- funding 数据为归档兜底口径(LV1 已披露),BNB 段精度未单独复核
- BTC 空头危机 alpha(2022)来源被削弱:三币中 ETH/SOL/BNB 的可空性待测
- 粒度改善是确定的(step/minNotional:BTC 0.001/50U vs ETH 0.001/20U、SOL·BNB 0.01/5U)
  ——资金门槛以实测价格重算,不做预估断言

## 5. 账本

+3 回测 +1 组合格;设计自由度:白名单选择 1 项(ETH/SOL/BNB 由户主指定),其余零新参数。
