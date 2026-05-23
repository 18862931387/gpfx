-- 回测结果表
CREATE TABLE IF NOT EXISTS backtest_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id INT NOT NULL,
    fund_code VARCHAR(10) NOT NULL,
    period_label VARCHAR(20),
    initial_capital DECIMAL(12,2),
    final_value DECIMAL(12,2),
    total_return DECIMAL(8,2),
    total_profit DECIMAL(12,2),
    max_drawdown DECIMAL(8,2),
    trade_count INT,
    created_at DATETIME DEFAULT NOW(),
    UNIQUE KEY uk_strategy_fund_period (strategy_id, fund_code, period_label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
