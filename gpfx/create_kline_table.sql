-- ETF Daily K-line Cache Table
-- Cached from Tencent K-line API (web.ifzq.gtimg.cn)
-- Used by simulate.py and _afternoon_check.py for MA20 calculation
-- Populated by daily_update.py

CREATE TABLE IF NOT EXISTS etf_kline (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    fund_code VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    open DECIMAL(10,4),
    high DECIMAL(10,4),
    low DECIMAL(10,4),
    close DECIMAL(10,4),
    volume DECIMAL(20,2),
    is_adj TINYINT(1) DEFAULT 1 COMMENT '1=前复权',
    create_time DATETIME DEFAULT NOW(),
    UNIQUE KEY uk_fund_date (fund_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
