
import sqlite3
import csv
from pathlib import Path

import datetime
from datetime import datetime

from typing import Tuple, List, Dict,Optional


class transferNameClass:
    def __init__(self, date):
        self.date = date
        self.count = 0
    def __str__(self):
        return self.date.strftime('%Y%m%d') + "_" + "%d" % self.count
    def count_up(self):
        self.count += 1
    def estimate(self, date):
        if self.date != date:
            self.date = date
            self.count = 0


def insert_record_withCur_notCommit(cursor: sqlite3.Cursor, table_name: str, data: dict) -> Optional[int]:
    """Insert a record into the specified table without committing the transaction.
    
    Args:
        cursor (sqlite3.Cursor): The database cursor.
        table_name (str): The name of the table to insert into.
        data (dict): A dictionary of column names and values to insert.
        
    Returns:
        int: The ID of the inserted record.
    """
    columns = ', '.join(data.keys())
    placeholders = ', '.join(['?' for _ in data] if data else [])

    sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
    cursor.execute(sql, tuple(data.values()))
    return cursor.lastrowid


def db_load_accounts(cur: sqlite3.Cursor, master_data: List[Tuple]) -> dict:
    """
    Load accounts from master data into the database.
    
    Args:
        cur (sqlite3.Cursor): The database cursor.
        master_data (Tuple): A tuple of tuples containing account names and types.
        
    Returns:
        dict: A dictionary mapping account names to their IDs.
    """
    ret = {}
    for name, type in master_data:
        accounts_data = {
            "name": name,
            "account_type": type
        }
        aid = insert_record_withCur_notCommit(cur, 'accounts', accounts_data)
        ret[name] = aid
    return ret



class db_loader:
    def __init__(self, db_path="./db/database.sqlite"):
        self.db = db_path

    def get_connect(self) -> sqlite3.Connection :
        """Connect to the SQLite database."""
        return sqlite3.connect(self.db)

    def do_disconnect(self,conn: sqlite3.Connection) -> None:
        conn.close()

    def get_csv_filename(self, csvfile_id: int) -> Optional[str]:
        """Get the filename of a CSV file by its ID."""
        conn = self.get_connect()
        cursor = conn.cursor()
        query = "SELECT name,loaded_date FROM csvfiles WHERE id = ?"
        cursor.execute(query, (csvfile_id,))
        result = cursor.fetchone()
        cursor.close()
        self.do_disconnect(conn)
        if result:
            if result[1]:
                return None
            return result[0]
        else:
            return None

    def insert_record(self, table_name: str, data: dict) -> Optional[int]:
        """Insert a record into the specified table.
        
        Args:
            table_name (str): The name of the table to insert into.
            data (dict): A dictionary of column names and values to insert.
            
        Returns:
            int: The ID of the inserted record.
        """
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['?' for _ in data])
        
            sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            cursor.execute(sql, tuple(data.values()))
            conn.commit()
            last_row_id = cursor.lastrowid
            return last_row_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            self.do_disconnect(conn)
        

    def load_csv_file(self, csvfile_id):
        """Load data from a CSV file into the database.
        
        Args:
            csvfile_id (str): The ID of the CSV file to load

        Returns:
            dict: Result of the operation
        """

        csv_filename = self.get_csv_filename(csvfile_id)
        if not csv_filename:
            return {"success": False, "error": f"CSV file not found for ID: {csvfile_id}"}

        #csv_path = Path("data/csv") / csv_filename
        csv_path = Path(csv_filename)

        if not csv_path.exists():
            return {"success": False, "error": f"File not found: {csv_filename}"}
        
        # Parse collector and date from filename
        conn = self.get_connect()
        cursor = conn.cursor()

        tnc = transferNameClass( datetime(1975,1,1) )
        
        valid_count = 0
        try:
            
            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")
                
            # Insert into data_logs
            log_data = {
                "csvfile_id": csvfile_id,
                "update_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            # Make sure to commit the data_logs record before referencing it in transactions
            log_id = insert_record_withCur_notCommit(cursor, "data_logs", log_data)
                
            # Read CSV file
            transactions_inserted = 0
            tags_inserted = 0
                
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                _ = next(reader)  # Skip header row

                # 
                
                for row in reader:
                    valid_count += 1
                    if len(row) < 5:  # Ensure there's at least date, account, category_type, category_name, amount
                        continue
                        
                    transaction_date = row[0].strip()
                    account_name = row[1].strip()
                    category_type = row[2].strip()
                    category_name = row[3].strip()
                    transfer_name = None if row[4].strip() in ["", "None"] else row[4].strip()
                    amount = float(row[5].strip())
                        
                    # Optional fields
                    item_name =  None if row[6].strip() in ["", "None"] else row[6].strip()

                    # Parse tags from the 7th column if it exists
                    tags = []
                    if len(row) > 7 and row[7].strip():
                        tags_str = row[7].strip()
                        # Remove brackets if present
                        if tags_str.startswith('[') and tags_str.endswith(']'):
                            tags_str = tags_str[1:-1]
                        # Split by pipe
                        tags = [tag.strip() for tag in tags_str.split('|')]
                        
                    description = None if row[8].strip() in ["", "None"] else row[8].strip()
                    memo = None if row[9].strip() in ["", "None"] else row[9].strip()


                    def ifNone_insert_to_account(local_account_name):
                        """Helper function to insert account if it doesn't exist."""
                        cursor.execute("SELECT id FROM accounts WHERE name = ?", (local_account_name,))
                        local_result = cursor.fetchone()
                        if local_result:
                            return local_result[0]
                        else:
                            account_data = {
                                "name": account_name,
                                "account_type": "その他"  # Default type
                            }
                            return insert_record_withCur_notCommit(cursor, "accounts", account_data)

                    # Get account_id from accounts table, or create if not exists
                    account_id = ifNone_insert_to_account(account_name)
                    
                    # Get category_id from categories table, or create if not exists
                    cursor.execute("SELECT id FROM categories WHERE name = ? AND type = ?", (category_name, category_type))
                    result = cursor.fetchone()
                    if result:
                        category_id = result[0]
                    else:
                        category_data = {
                            "name": category_name,
                            "type": category_type
                        }
                        #category_id = self.insert_record("categories", category_data)
                        category_id = insert_record_withCur_notCommit(cursor, "categories", category_data)


                    try:
                        tnc_date = datetime.strptime(transaction_date, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        tnc_date = datetime.strptime(transaction_date, '%Y-%m-%d')
                    except Exception as e:
                        raise e
                        
                    tnc.estimate(tnc_date)

                    def insert_transaction_data(aid, tid,  amnt):
                        """Helper function to insert transaction data."""
                        transaction_data = {
                            "account_id": aid,
                            "category_id": category_id,
                            "log_id": log_id,
                            "transfer_id": tid,
                            "amount": amnt,
                            "item_name": item_name,
                            "description": description,
                            "transaction_date": transaction_date,
                            "memo": memo
                        }
                        return insert_record_withCur_notCommit(cursor, "transactions", transaction_data)
                   
                    def insert_tag_data(tags,tid):
                        """Helper function to insert tags for a transaction."""
                        cont = 0
                        for tag_name in tags:
                            if not tag_name:
                                continue
                            # Get tag_id from tags table, or create if not exists
                            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                            result = cursor.fetchone()
                            if result:
                                tag_id = result[0]
                            else:
                                #tag_id = self.insert_record("tags", tag_data)
                                tag_id = insert_record_withCur_notCommit(cursor, "tags", {"name": tag_name} )
                            cursor.execute(
                                "INSERT INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)",(tid, tag_id)
                            )
                            cont += 1
                        return cont

                    # If transfer_name is provided, handle it as a transfer transaction
                    if transfer_name:
                        transfer_account_id = ifNone_insert_to_account(transfer_name)
                        transfer_id = insert_record_withCur_notCommit(cursor, "transfers", {"name": tnc.__str__() } )

                        transaction_id = insert_transaction_data(account_id, transfer_id, amount)
                        tags_inserted += insert_tag_data(tags, transaction_id)

                        transfer_transaction_id = insert_transaction_data(transfer_account_id, transfer_id, - amount)
                        tags_inserted += insert_tag_data(tags, transfer_transaction_id)
                        transactions_inserted += 2
                        tnc.count_up()

                    else:
                        transfer_id = None
                        transaction_id = insert_transaction_data(account_id, transfer_id, amount)
                        tags_inserted += insert_tag_data(tags, transaction_id)
                        transactions_inserted += 1
                    
                # Update the csv_files table to mark the file as loaded
                cursor.execute("UPDATE csvfiles SET loaded_date = ? WHERE id = ?", 
                           (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), csvfile_id))
            
            # Commit the transaction
            conn.commit()
                
            return {
                "success": True, 
                "transactions_inserted": transactions_inserted,
                "tags_inserted": tags_inserted,
                "log_id": log_id,
                "filename": csv_filename
            }
        except Exception as e:
            conn.rollback()
            print(f"Error occurred after processing {valid_count} valid rows: {e}")
            return {"success": False, "error": str(e)}
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def register_agent(self, agent_name: str, prompt: Optional[str]) -> Tuple[str, Optional[int]]:
        """Register a new agent if it doesn't exist.

        Args:
            agent_name (str): The name of the agent to register.
        """        
        
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            # agentsテーブルでagent_nameを確認
            check_agent_query = "SELECT id FROM agents WHERE name = ?"
            cursor.execute(check_agent_query, (agent_name,))
            agent_result = cursor.fetchone()
            
            if agent_result:
                agent_id = agent_result[0]
                return f"[cyan]既存のエージェント '{agent_name}' (ID: {agent_id}) を使用します[/cyan]", agent_id
            else:
                # 新しいエージェントを登録
                insert_agent_query = "INSERT INTO agents (name, prompt_file) VALUES (?, ?)"
                cursor.execute(insert_agent_query, (agent_name, prompt))
                conn.commit()
                new_agent_id = cursor.lastrowid
                return f"[green]新しいエージェント '{agent_name}' (ID: {new_agent_id}) を登録しました[/green]", new_agent_id
        except Exception as e:
            conn.rollback()
            return f"[red]エラーが発生しました: {e}[/red]", None
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def del_agent(self, agent_id: int) -> Tuple[str, Optional[int]]:
        """Delete an agent by ID.

        Args:
            agent_id (int): The ID of the agent to delete.
        """        
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            # エージェントを削除
            delete_agent_query = "DELETE FROM agents WHERE id = ?"
            res = cursor.execute(delete_agent_query, (agent_id,))
            conn.commit()
            return f"[green]エージェント '{agent_id}' を削除しました[/green]", res.rowcount
        except Exception as e:
            conn.rollback()
            return f"[red]エラーが発生しました: {e}[/red]", None
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def register_csvfile(self, filename: str, agent_name: str, orgname = None) -> Tuple[List[str], Optional[int]]:
        """Register a new CSV file if it doesn't exist.

        Args:
            filename (str): The name of the CSV file to register.
            agent_name (str): The ID of the agent associated with the CSV file.
        """        
        if not Path(filename).exists():
            return [f"[red]ファイル '{filename}' が見つかりません[/red]"], None
        
        ret_str = []
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            check_agent_query = "SELECT id FROM agents WHERE name = ?"
            #print(f"DEBUG: Checking agent '{agent_name}'")
            cursor.execute(check_agent_query, (agent_name,))
            agent_result = cursor.fetchone()
            #print(f"DEBUG: Checking agent '{agent_name}' result: {agent_result}")
            if agent_result:
                agent_id = agent_result[0]
                ret_str.append(f"[cyan]エージェント '{agent_name}' (ID: {agent_id}) を使用します[/cyan]")
            else:
                insert_agent_query = "INSERT INTO agents (name, prompt_file) VALUES (?, ?)"
                cursor.execute(insert_agent_query, (agent_name, ""))
                agent_id = cursor.lastrowid
                ret_str.append(f"[green]新しいエージェント '{agent_name}' を登録しました[/green]")

            # csvfilesテーブルでfilenameを確認
            check_csv_query = "SELECT id, loaded_date FROM csvfiles WHERE name = ?"
            cursor.execute(check_csv_query, (filename,))
            csv_result = cursor.fetchone()
            
            if csv_result:
                csvfile_id = csv_result[0]
                loaded_date = csv_result[1]
                if loaded_date:
                    ret_str.append(f"[cyan]既存のCSVファイル '{filename}' (ID: {csvfile_id}) は既にロード済みです[/cyan]")
                    return ret_str, None
                else:
                    ret_str.append(f"[cyan]既存のCSVファイル '{filename}' (ID: {csvfile_id}) を使用します[/cyan]")
                    return ret_str, csvfile_id
            else:
                # 新しいCSVファイルを登録
                insert_csv_query = "INSERT INTO csvfiles (agent_id, name, org_name) VALUES (?, ?, ?)"
                cursor.execute(insert_csv_query, (agent_id, filename, orgname))
                new_csvfile_id = cursor.lastrowid
                #print(f"DEBUG: New CSV file ID: {new_csvfile_id}, filename: {filename}, agent_id: {agent_id}")
                conn.commit()
                #print("DEBUG: Commit successful")
                ret_str.append(f"[green]新しいCSVファイル '{filename}' (ID: {new_csvfile_id}) を登録しました[/green]")
                return ret_str, new_csvfile_id

        except Exception as e:
            conn.rollback()
            return [f"[red]エラーが発生しました: {e}[/red]"], None
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def del_csvfile(self, csvfile_id: int) -> Tuple[str, Optional[int]]:
        """Delete an csvfile by ID.

        Args:
            csvfile_id (int): The ID of the csvfile to delete.
        """        
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            # エージェントを削除
            delete_agent_query = "DELETE FROM csvfiles WHERE id = ?"
            res = cursor.execute(delete_agent_query, (csvfile_id,))
            conn.commit()
            return f"[green]csvfile '{csvfile_id}' を削除しました[/green]", res.rowcount
        except Exception as e:
            conn.rollback()
            return f"[red]エラーが発生しました: {e}[/red]", None
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def insert_agent(self, agent_name: str, prompt_file: str) -> Tuple[str, Optional[int]]:
        """Insert a new agent.

        Args:
            agent_name (str): The name of the agent to insert.
            prompt_file (str): The prompt file path for the agent.
        """
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            # Check if agent already exists
            check_agent_query = "SELECT id FROM agents WHERE name = ?"
            cursor.execute(check_agent_query, (agent_name,))
            agent_result = cursor.fetchone()
            
            if agent_result:
                return f"[yellow]エージェント '{agent_name}' は既に存在します (ID: {agent_result[0]})[/yellow]", None
            
            # Insert new agent
            insert_agent_query = "INSERT INTO agents (name, prompt_file) VALUES (?, ?)"
            cursor.execute(insert_agent_query, (agent_name, prompt_file))
            conn.commit()
            new_agent_id = cursor.lastrowid
            return f"[green]エージェント '{agent_name}' を追加しました (ID: {new_agent_id})[/green]", new_agent_id
        except Exception as e:
            conn.rollback()
            return f"[red]エラーが発生しました: {e}[/red]", None
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def insert_account(self, account_name: str, account_type: str) -> Tuple[str, Optional[int]]:
        """Insert a new account.

        Args:
            account_name (str): The name of the account to insert.
            account_type (str): The type of the account.
        """
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            # Check if account already exists
            check_account_query = "SELECT id FROM accounts WHERE name = ?"
            cursor.execute(check_account_query, (account_name,))
            account_result = cursor.fetchone()
            
            if account_result:
                return f"[yellow]アカウント '{account_name}' は既に存在します (ID: {account_result[0]})[/yellow]", None
            
            # Insert new account
            insert_account_query = "INSERT INTO accounts (name, account_type) VALUES (?, ?)"
            cursor.execute(insert_account_query, (account_name, account_type))
            conn.commit()
            new_account_id = cursor.lastrowid
            return f"[green]アカウント '{account_name}' を追加しました (ID: {new_account_id})[/green]", new_account_id
        except Exception as e:
            conn.rollback()
            return f"[red]エラーが発生しました: {e}[/red]", None
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def del_account(self, account_id: int) -> Tuple[str, Optional[int]]:
        """Delete an account by ID.

        Args:
            account_id (int): The ID of the account to delete.
        """
        conn = self.get_connect()
        cursor = conn.cursor()
        try:
            # Check if account has transactions
            check_transactions_query = "SELECT COUNT(*) FROM transactions WHERE account_id = ?"
            cursor.execute(check_transactions_query, (account_id,))
            transaction_count = cursor.fetchone()[0]
            
            if transaction_count > 0:
                return f"[yellow]アカウント ID {account_id} には {transaction_count} 件の取引があります。削除できません[/yellow]", None
            
            # Delete account
            delete_account_query = "DELETE FROM accounts WHERE id = ?"
            res = cursor.execute(delete_account_query, (account_id,))
            conn.commit()
            
            if res.rowcount > 0:
                return f"[green]アカウント ID {account_id} を削除しました[/green]", res.rowcount
            else:
                return f"[yellow]アカウント ID {account_id} が見つかりません[/yellow]", None
        except Exception as e:
            conn.rollback()
            return f"[red]エラーが発生しました: {e}[/red]", None
        finally:
            cursor.close()
            self.do_disconnect(conn)

    def rollback_csv_files(self, csvfile_id: int) -> Tuple[List[str], Optional[int]]:
        """Rollback transactions associated with specific CSV file IDs.

        Args:
            csvfile_id (int): The ID of the CSV file to rollback.
        """
        conn = self.get_connect()
        cursor = conn.cursor()
        try:

            # csvfile情報を取得
            query = "SELECT name, loaded_date FROM csvfiles WHERE id = ?"
            cursor.execute(query, (csvfile_id,))
            result = cursor.fetchone()

            if not result:
                return [f"[yellow]CSVファイルID {csvfile_id} に関連するログが見つかりません[/yellow]"], None

            file_path, loaded_date = result

            if not loaded_date:
                return [f"[yellow]このCSVファイルはまだロードされていません[/yellow]"], None
            
            # data_logsからlog_idを取得
            log_query = "SELECT id FROM data_logs WHERE csvfile_id = ?"
            log_results = cursor.execute(log_query, (csvfile_id,))

            log_ids = [row[0] for row in log_results]

            ret_str = []
            ret_str.append(f"[cyan]ロールバックを実行中...[/cyan]")
            ret_str.append(f"  ファイル: {file_path}")
            ret_str.append(f"  対象log_id数: {len(log_ids)}")

            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")

            ret_str.append(f"ロールバックしました  ログID: {', '.join(map(str, log_ids))}")
            # Delete transactions associated with these log IDs
            delete_trans_query = f"DELETE FROM transactions WHERE log_id IN ({','.join(['?']*len(log_ids))})"
            delete_trans_results = cursor.execute(delete_trans_query, log_ids)
            ret_str.append(f"  削除された取引数: {delete_trans_results.rowcount}")

            # Delete data_logs entries
            delete_logs_query = "DELETE FROM data_logs WHERE csvfile_id = ?"
            delete_logs_results = cursor.execute(delete_logs_query, (csvfile_id,))
            ret_str.append(f"  削除されたLOG数: {delete_logs_results.rowcount}")

            # Reset loaded_date in csvfiles table
            update_csv_query = "UPDATE csvfiles SET loaded_date = NULL WHERE id = ?"
            update_csv_result = cursor.execute(update_csv_query, (csvfile_id,))
            ret_str.append(f"  更新されたCSVファイル数: {update_csv_result.rowcount}")
            ret_str.append(f"[green]ロールバックが完了しました[/green]")

            # Commit the transaction
            conn.commit()
            return ret_str, len(log_ids)

        except Exception as e:
            conn.rollback()
            return [f"[red]エラーが発生しました: {e}[/red]"], None
        finally:
            cursor.close()
            self.do_disconnect(conn)



class db_reporter:
    def __init__(self, db_path="./db/database.sqlite"):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        
    def connect(self) -> Optional[str]:
        """Connect to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            return None
        except sqlite3.Error as e:
            return f"[red]データベース接続エラー: {e}[/red]"

    def disconnect(self):
        """Disconnect from the SQLite database."""
        if self.conn:
            self.conn.close()

    def strptime(self, date_str: str, fmt: str = "%Y-%m-%d") -> Optional[datetime]:
        """文字列をdatetimeに変換
        
        Args:
            date_str: 日付文字列
            fmt: フォーマット
            
        Returns:
            変換結果のdatetimeオブジェクト、失敗時はNone
        """
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            return None

    def execute_query(self , query: str, params: Tuple = ()) -> Tuple[Optional[str], List[Tuple]]:
        """Execute a query and return the results."""
        if not self.conn or not self.cursor:
            return "[red]データベースに接続されていません[/red]",[]
        try:   
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            results = self.cursor.fetchall()
            return None, results
        except sqlite3.Error as e:
            return f"[red]クエリ実行エラー: {e}[/red]", []

    def cmd_tables(self) -> Tuple[Optional[str], List[Tuple]]:
        """List all tables in the database."""
        query = "SELECT name FROM sqlite_master WHERE type='table';"
        return self.execute_query(query)

    def cmd_count(self, table_name: str) -> Tuple[Optional[str], List[Tuple]]:
        """Count records in a specified table.

        Args:
            table_name: テーブル名またはall
        """
        if table_name.lower() =="all":
            query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            err,tables = self.execute_query(query)
            if err is None:
                result = []
                for table_row in tables:
                    tbl_name = table_row[0] if table_row else ""
                    count_query = f"SELECT COUNT(*) FROM {tbl_name};"
                    err, count = self.execute_query(count_query)
                    if err is not None:
                        return err, []
                    result.append((tbl_name, count[0][0]))
                return None,result
            else:
                return "テーブルが見つかりません", []
        else:
            query = f"SELECT COUNT(*) FROM {table_name};"
            err, count = self.execute_query(query)
            if err is None:
                return None, [(table_name, count[0][0]) ]
            else:
                return f"テーブル '{table_name}' が見つかりません", []

    def cmd_schema(self, table_name: str) -> Tuple[Optional[str], List[Tuple]]:
        """Get the schema of a specified table."""
        query = f"PRAGMA table_info({table_name});"
        return self.execute_query(query)

    def cmd_print_table(self, table_name: str, limit: Optional[int]) -> Tuple[Optional[str], List[Tuple]]:
        """Execute an arbitrary SQL query."""
        query = f"SELECT * FROM {table_name}"
        if limit is not None:
            query += f" LIMIT {limit}"
        return self.execute_query(query)

    def get_date_format(self, period: str) -> Optional[str]:
        """Get the date format string for SQLite based on the period."""
        if period == "day":
            return "DATE(transaction_date)"
        elif period == "month":
            return "strftime('%Y-%m', transaction_date)"
        elif period == "year":
            return "strftime('%Y', transaction_date)"
        else:
            return None

    def cmd_summary(self, period:str, number:Optional[int], date_str:Optional[str]) -> Tuple[Optional[str], List[Tuple]]:
        """Get a summary of key tables.
        Args:
            period: day, month, year
            number: 直近の期間数
            date_str: 起点となる日付 (YYYY-MM-DD形式)
        """
        # 日付フォーマットを決定
        date_format = self.get_date_format(period)
        if date_format is None:
            return f"[red]無効な期間指定: {period}[/red]", []

        if date_str is not None:
            target_date = self.strptime(date_str)
            if target_date is None:
                return f"[red]日付の形式が不正です。YYYY-MM-DD形式で指定してください。[/red]", []
        else:
            target_date = datetime.now()
            
        # クエリ構築
        query = f"""
        SELECT 
            {date_format} as period,
            SUM(CASE WHEN t.amount < 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as expenses,
            SUM(CASE WHEN t.amount > 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as income,
            SUM(CASE WHEN t.transfer_id is null THEN t.amount ELSE 0 END) as total,
            SUM(CASE WHEN t.transfer_id is not null THEN t.amount ELSE 0 END) as transfer
        FROM transactions t
        WHERE transaction_date IS NOT NULL
        GROUP BY period
        ORDER BY period ASC
        """
        
        if number:
            query += f" LIMIT {number}"

        return self.execute_query(query)


    def cmd_summary_account(self, period:str, number:Optional[int], date_str:Optional[str]) -> Tuple[Optional[str], List[Tuple]]:
        """Get a summary of accounts.
        Args:
            period: day, month, year
            number: 直近の期間数
            date_str: 起点となる日付 (YYYY-MM-DD形式)
        """
        # 日付フォーマットを決定
        date_format = self.get_date_format(period)
        if date_format is None:
            return f"[red]無効な期間指定: {period}[/red]", []
            
        if date_str is not None:
            target_date = self.strptime(date_str)
            if target_date is None:
                return f"[red]日付の形式が不正です。YYYY-MM-DD形式で指定してください。[/red]", []
        else:
            target_date = 'now'

        # クエリ構築（transfer除外）
        query = f"""
        SELECT 
            {date_format} as period,
            a.name as account_name,
            SUM(CASE WHEN t.amount < 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as expenses,
            SUM(CASE WHEN t.amount > 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as income,
            SUM(CASE WHEN t.transfer_id is null THEN t.amount ELSE 0 END) as total,
            SUM(CASE WHEN t.transfer_id is not null THEN t.amount ELSE 0 END) as transfer,
            SUM(t.amount) as balance
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        WHERE t.transaction_date IS NOT NULL
        GROUP BY period, a.name
        ORDER BY period ASC, a.name
        """

        if number:
            # 期間制限を適用
            if period == "day":
                date_limit = f"date('{target_date}', '-{number} days')"
            elif period == "month":
                date_limit = f"date('{target_date}', '-{number} months')"
            else:  # year
                date_limit = f"date('{target_date}', '-{number} years')"
            query = query.replace("WHERE t.transaction_date IS NOT NULL",
                                f"WHERE t.transaction_date IS NOT NULL AND t.transaction_date < '{target_date}' AND t.transaction_date >= {date_limit}")
        
        return self.execute_query(query)


    def cmd_summary_category(self, period:str, number:Optional[int], date_str:Optional[str]) -> Tuple[Optional[str], List[Tuple]]:
        """Get a summary of categories.
        Args:
            period: day, month, year
            number: 直近の期間数
            date_str: 起点となる日付 (YYYY-MM-DD形式)
        """
        # 日付フォーマットを決定
        date_format = self.get_date_format(period)
        if date_format is None:
            return f"[red]無効な期間指定: {period}[/red]", []
            
        if date_str is not None:
            target_date = self.strptime(date_str)
            if target_date is None:
                return f"[red]日付の形式が不正です。YYYY-MM-DD形式で指定してください。[/red]", []
        else:
            target_date = 'now'

        # クエリ構築（transfer除外）
        query = f"""
        SELECT 
            {date_format} as period,
            a.name as account_name,
            c.name as category_name,
            SUM(CASE WHEN t.amount < 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as expenses,
            SUM(CASE WHEN t.amount > 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as income,
            SUM(CASE WHEN t.transfer_id is null THEN t.amount ELSE 0 END) as total,
            SUM(CASE WHEN t.transfer_id is not null THEN t.amount ELSE 0 END) as transfer,
            SUM(t.amount) as balance
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.transaction_date IS NOT NULL
        GROUP BY period, a.name, c.name
        ORDER BY period ASC, a.name, c.name
        """

        if number:
            # 期間制限を適用
            if period == "day":
                date_limit = f"date('{target_date}', '-{number} days')"
            elif period == "month":
                date_limit = f"date('{target_date}', '-{number} months')"
            else:  # year
                date_limit = f"date('{target_date}', '-{number} years')"
            query = query.replace("WHERE t.transaction_date IS NOT NULL",
                                f"WHERE t.transaction_date IS NOT NULL AND t.transaction_date < '{target_date}' AND t.transaction_date >= {date_limit}")

        return self.execute_query(query)


    def cmd_sum_logs(self, csvfile_id: int) -> Tuple[Optional[str], List[Tuple]]:
        """Get a summary of transactions for a specific CSV file ID."""
        query = """
        SELECT 
            COUNT(t.id) as transaction_count,
            SUM(CASE WHEN t.amount < 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as total_expenses,
            SUM(CASE WHEN t.amount > 0 AND t.transfer_id is null THEN t.amount ELSE 0 END) as total_income,
            SUM(CASE WHEN t.transfer_id is null THEN t.amount ELSE 0 END) as net_total,
            SUM(CASE WHEN t.transfer_id is not null THEN t.amount ELSE 0 END) as total_transfer
        FROM transactions t
        JOIN data_logs dl ON t.log_id = dl.id
        WHERE dl.csvfile_id = ?
        """
        return self.execute_query(query, (csvfile_id,))


    def cmd_balance(self, as_of_date: str) -> Tuple[Optional[str], List[Tuple]]:
        """Get the balance of each account as of a specific date.
        
        Args:
            as_of_date (str): The date to calculate the balance up to (YYYY-MM-DD format).

        """
        # 日付の形式を検証
        target_date = self.strptime(as_of_date)
        if target_date is None:
            return f"[red]日付の形式が不正です。YYYY-MM-DD形式で指定してください。[/red]", []

        # クエリ構築
        query = """
        SELECT 
            a.name as account_name,
            SUM(CASE WHEN t.amount < 0 THEN t.amount ELSE 0 END) as total_expenses,
            SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as total_income,
            SUM(t.amount) as total
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.transaction_date <= ?
        GROUP BY account_name
        ORDER BY account_name
        """
        return self.execute_query(query, (as_of_date,))

    def cmd_csvfiles(self, csvfile_id: int) -> Tuple[Optional[str], List[Tuple]]:
        """List all CSV files in the database."""
        query = """
        SELECT c.name, a.name as agent_name, c.loaded_date 
        FROM csvfiles c
        JOIN agents a ON c.agent_id = a.id
        WHERE c.id = ?
        """
        return self.execute_query(query, (csvfile_id,))


class DatabaseManager(db_reporter, db_loader):
    def __init__(self, db_path="./db/database.sqlite"):
        super().__init__(db_path)

    def get_connect(self):
        if self.conn is None:
            self.connect()

        return self.conn

    def do_disconnect(self,conn: sqlite3.Connection):
        pass
