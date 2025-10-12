CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                -- 食費、住居費、給与など
    type TEXT NOT NULL,                -- 支出(expense), 収入(income)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(type,name)
);
