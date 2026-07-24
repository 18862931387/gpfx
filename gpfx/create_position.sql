-- 持仓表: 记录当前持仓 + 交易流水
CREATE TABLE IF NOT EXISTS position (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fund_code VARCHAR(10) NOT NULL,
    fund_name VARCHAR(100),
    trade_date DATE NOT NULL,
    trade_type VARCHAR(10) NOT NULL COMMENT 'buy/sell',
    shares INT NOT NULL COMMENT '本次成交股数',
    price DECIMAL(10,4) NOT NULL COMMENT '成交单价',
    amount DECIMAL(12,2) NOT NULL COMMENT '成交金额',
    shares_after INT NOT NULL COMMENT '成交后总持仓',
    cash_after DECIMAL(12,2) NOT NULL COMMENT '成交后剩余现金',
    note VARCHAR(200),
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_fund (fund_code),
    INDEX idx_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
