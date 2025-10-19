import sqlite3
import os
from pathlib import Path

ddl_files = [
    "accounts.sql", "categories.sql", "tags.sql",
    "transactions.sql", "transfers.sql", "assets.sql",
    "transaction_tags.sql", "data_logs.sql", "files.sql", 
    "agents.sql", "archives.sql", "csvfiles.sql"
]

def init_database(db_path_arg:str, ddl_path_arg: str):
    """Initialize the database with DDL files."""
    db_path = Path(db_path_arg)
    #os.makedirs(db_path.parent, exist_ok=True)
    print(f"Database path: {db_path}")
    
    #ddl_dir = Path(__file__).parent.parent / "db" / "ddl"
    ddl_dir = Path(ddl_path_arg)
    
    conn = sqlite3.connect(str(db_path))
    try:
        for ddl_file in ddl_files:
            ddl_path = ddl_dir / ddl_file
            if ddl_path.exists():
                with open(ddl_path, 'r', encoding='utf-8') as f:
                    ddl_content = f.read()
                conn.executescript(ddl_content)
                print(f"Executed DDL: {ddl_file}")
        conn.commit()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        conn.close()



#if __name__ == "__main__":
#
#    init_database('database.sqlite', ddl_files)
