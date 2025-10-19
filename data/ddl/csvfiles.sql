-- This is the new table definition for csvfiles with archive_id column
CREATE TABLE csvfiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    org_name TEXT,
    agent_id INTEGER NOT NULL,
    archive_id INTEGER DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    loaded_date DATETIME DEFAULT NULL,
    FOREIGN KEY(agent_id) REFERENCES agents(id),
    FOREIGN KEY(archive_id) REFERENCES archive(id)
);
