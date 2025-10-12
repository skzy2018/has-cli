CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,               -- 口座名（銀行名・カード名）
    account_type TEXT NOT NULL,       -- 種類（銀行口座、クレジットカード等）
    currency TEXT DEFAULT 'JPY',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name)
);

