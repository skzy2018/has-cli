CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    log_id INTEGER ,
    ref_transaction_id INTEGER,
    transfer_id INTEGER,
    amount REAL NOT NULL,             -- 支出は負数、収入は正数
    item_name TEXT,
    description TEXT,
    transaction_date DATETIME NOT NULL,
    memo TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id),
    FOREIGN KEY(category_id) REFERENCES categories(id),
    FOREIGN KEY(log_id) REFERENCES data_logs(id),
    FOREIGN KEY(ref_transaction_id) REFERENCES transactions(id),
    FOREIGN KEY(transfer_id) REFERENCES transfers(id)
);
