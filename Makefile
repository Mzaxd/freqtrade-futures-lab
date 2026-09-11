.PHONY: install download quality is-backtests hyperopt val-backtests walkforward stress oos reports

FREQTRADE_VERSION ?= 2026.8

install:
	python3.11 -m venv .venv || uv venv --python 3.11 .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/freqtrade --version

download:
	bash scripts/download_data.sh 20190101 20260912

quality:
	.venv/bin/python scripts/data_quality_report.py

# In-sample baseline: 2021-01-01 .. 2022-12-31
is-backtests:
	bash scripts/run_backtest.sh TrendBaselineV1 20210101-20230101 is
	bash scripts/run_backtest.sh DonchianBreakoutV2 20210101-20230101 is
	bash scripts/run_backtest.sh TrendVolFundingV3 20210101-20230101 is
	.venv/bin/python scripts/summarize_results.py is \
	  user_data/backtest_results/is_*.zip

hyperopt-%:
	bash scripts/run_hyperopt.sh $* 150 SharpeHyperOptLoss

# Validation: 2023 (used for strategy selection only)
val-backtests:
	bash scripts/run_backtest.sh TrendBaselineV1 20230101-20240101 val
	bash scripts/run_backtest.sh DonchianBreakoutV2 20230101-20240101 val
	bash scripts/run_backtest.sh TrendVolFundingV3 20230101-20240101 val
	.venv/bin/python scripts/summarize_results.py val \
	  user_data/backtest_results/val_*.zip

walkforward-%:
	bash scripts/run_walkforward.sh $*

stress-%:
	.venv/bin/python scripts/stress_test.py $* 20210101-20240101 $*

# Out-of-sample: run ONCE, only after the candidate is frozen
oos-%:
	bash scripts/run_backtest.sh $* 20240101-20260912 oos
	.venv/bin/python scripts/summarize_results.py oos_$* \
	  user_data/backtest_results/oos_$*.zip
