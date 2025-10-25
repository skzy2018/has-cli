#!/usr/bin/env python3
"""
家計簿データベース CLIインターフェースアプリケーション
"""

import os
import sys
import argparse
import readline  # コマンド履歴機能のため
from pathlib import Path
from typing import Optional,Any,List,Tuple
import platform

import configparser

from rich.console import Console
from rich.table import Table
#from rich.prompt import Prompt
from rich.panel import Panel

# db_lib.pyから必要なクラスをインポート
from db_lib import DatabaseManager
from transaction_journalizer import TransactionJournalizer
from init_db import init_database


class UniversalTabCompleter:
    """ユニバーサルタブ補完クラス"""

    def __init__(self, command_setting: dict[str, List[Any]]):
        """初期化
        """
        self.setting = command_setting
        self.commands = self.setting.keys() 
        
    def complete(self, text, state):
        """タブ補完のメイン関数
        """
        if state == 0:
            # 最初の呼び出し時に候補を生成
            line = readline.get_line_buffer()
            parts = line.split()

            self.matches = []
            # コマンド補完
            #print("DEBUG: complete() called, line='{line}', parts={parts}, text='{text}'".format(line=line, parts=parts, text=text))
            if len(parts) == 0 or (len(parts) == 1 and not line.endswith(' ')):
                self.matches = [cmd for cmd in self.commands if cmd.startswith(text)]

            else:
                for k in self.commands:
                    if parts[0] == k:
                        args = self.setting.get(k, [])
                        parts_id = len(parts) - 1 if line.endswith(' ') else len(parts) - 2
                        if parts_id < len(args):
                            arg_info = args[parts_id]
                            if "options" in arg_info:
                                self.matches = [opt for opt in arg_info["options"] if opt.startswith(text)]
                            elif "completer" in arg_info and callable(arg_info["completer"]):
                                self.matches = arg_info["completer"](text)
                            else:
                                self.matches = []
                            #print(f"DEBUG: parts={parts}, args={args}, text='{text}' arg_info={arg_info}")
                            #print(f"DEBUG: self.matches={self.matches}")
                        else:
                            self.matches = []
                        break
        
        # state番目の候補を返す
        if state < len(self.matches):
            return self.matches[state]
        return None


def complete_files(text):
    """ファイル名の補完"""
    matches = []
    # 現在のパスから補完
    if text:
        # ディレクトリ部分とファイル部分を分離
        if '/' in text:
            dir_path = os.path.dirname(text)
            file_prefix = os.path.basename(text)
            search_path = dir_path if dir_path else '.'
        else:
            search_path = '.'
            file_prefix = text
    else:
        search_path = '.'
        file_prefix = ''
        
    try:
        # ディレクトリ内のファイルを検索
        if os.path.exists(search_path):
            for item in os.listdir(search_path):
                if item.startswith(file_prefix):
                    full_path = os.path.join(search_path, item) if search_path != '.' else item
                    if os.path.isdir(full_path):
                        matches.append(full_path + '/')
                    #elif item.endswith('.csv'):
                    else:
                        matches.append(full_path)
    except PermissionError:
        pass
        
    return sorted(matches)


class HasCLI:
    """家計簿データベースCLIアプリケーション"""

    def __init__(self, config_path_str: str = "./config.ini"):
        """初期化
        
        Args:
            db_path: データベースファイルのパス
        """
        self.console = Console()
        self.history_file = Path.home() / ".has_cli_history"
        self.jornalizers = {}

        self.config = configparser.ConfigParser()
        config_path = Path(config_path_str)
        if config_path.exists():
            if not self.config.read(config_path):
                self.console.print(f"[red]エラー: 設定ファイル '{config_path}' が読み込めません[/red]")
                exit(1)
            self.config.read(config_path)

        #self.db_path = self.config.get("database", "database", fallback="./data/db/database.sqlite")
        self.db_path = self.config.get("database", "database")
        self.ddl_dir = self.config.get("database", "ddl_dir")
        self.sql_file_dir = self.config.get("database", "sql_file_dir", fallback='data/sql/')
        self.archive_file_format = self.config.get("archive", "archive_file_format", fallback="archive_{time}.zip")
        self.db_manager = DatabaseManager(self.db_path, self.archive_file_format)
        # タブ補完の設定
        self.completer = UniversalTabCompleter({
            "help": [],
            "tables": [],
            "balance": [],
            "load_csv": [],
            "rollback_csv": [],
            "sum_log": [],
            "ins_agent": [],
            "del_account": [],
            "del_agent": [],
            "del_csvfile": [],
            "ins_agent": [
                { "options":[]},
                {
                    "completer": complete_files,
                }
            ],
            "doSQL": [
                {
                    "completer": self.complete_sqlfiles,
                }
            ],
            "count": [
                {"options": ["all", "accounts", "agents", "categories", "transactions", "tags", "csvfiles"]}
            ],
            "sum": [ 
                {"options": ["day", "month", "year"]} 
            ],
            "sum_account": [ 
                {"options": ["day", "month", "year"]} 
            ],
            "sum_category": [ 
                {"options": ["day", "month", "year"]} 
            ],
            "register": [
                {
                    "completer": complete_files,
                }
            ],
            "journalize": [
                { "options":[]},
                {
                    "completer": complete_files,
                }
            ],
            "archive_csv": [],
            "extract": []
        })
        self.setup_readline()
        
    def setup_readline(self):
        """readlineの設定（コマンド履歴機能）"""
        # 履歴ファイルの読み込み
        if self.history_file.exists():
            try:
                readline.read_history_file(self.history_file)
            except:
                pass
        
        # 履歴の最大保存数を設定
        readline.set_history_length(1000)
        
        # タブ補完を無効化（richのプロンプトと競合を避けるため）
        #readline.parse_and_bind("tab: self-insert")
        # タブ補完の設定
        readline.set_completer(self.completer.complete)

        # OSに応じた設定
        if platform.system() == 'Darwin':
            # Mac (libedit) の場合 タブ文字を正しく認識させるため、^I（Control-I）を使用
            readline.parse_and_bind("bind ^I rl_complete")
            #self.console.print(f"[cyan]システム: macOS (libedit)[/cyan]")
        else:
            # Linux/Unix (GNU readline) の場合
            readline.parse_and_bind("tab: complete")
            #self.console.print(f"[cyan]システム: {platform.system()} (GNU readline)[/cyan]")

        # 区切り文字の設定（スペースのみ）
        readline.set_completer_delims(' \t\n')

    def complete_sqlfiles(self, text: str) -> List[str]:
        """SQLファイル名の補完"""
        li = [ f for f in os.listdir(self.sql_file_dir) if f.startswith(text)]
        return [f for f in li if f.endswith('.sql')]

    def parse_csvfile_ids(self, ids_str: str) -> List[int]:
        """Parse CSV file IDs from string format (e.g., "1,3-5,7")
        
        Args:
            ids_str: String containing IDs with comma and hyphen separators
            
        Returns:
            List of integer IDs
        """
        result = []
        parts = ids_str.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Handle range
                try:
                    start, end = part.split('-')
                    start = int(start.strip())
                    end = int(end.strip())
                    result.extend(range(start, end + 1))
                except ValueError:
                    continue
            else:
                # Handle single ID
                try:
                    result.append(int(part))
                except ValueError:
                    continue
                    
        return sorted(list(set(result)))  # Remove duplicates and sort
        
    def cmd_tables(self):
        """テーブル名のリスト表示"""
        err,results = self.db_manager.cmd_tables()
        if err:
            self.console.print(f"[red]エラー: {err}[/red]")
            return

        if results:
            table = Table(title="データベース内のテーブル")
            table.add_column("テーブル名", style="cyan", no_wrap=True)
            for row in results:
                table.add_row(row[0])
                
            self.console.print(table)
        else:
            self.console.print("[yellow]テーブルが見つかりません[/yellow]")
            
    def cmd_count(self, table_name: str):
        """各テーブルの件数表示
        
        Args:
            table_name: テーブル名またはall
        """
        err, results = self.db_manager.cmd_count(table_name)
        if err:
            self.console.print(f"[red]エラー: {err}[/red]")
            return
            
        if table_name.lower() =="all":
            result_table = Table(title="全テーブルの件数")
        else:
            result_table = Table(title=f"{table_name}テーブルの件数")

        result_table.add_column("テーブル名", style="cyan", no_wrap=True)
        result_table.add_column("件数", justify="right", style="green")
        for row in results:
            result_table.add_row(row[0], str(row[1]))
        self.console.print(result_table)

                
    def cmd_print_table(self, table_name: str, limit: Optional[int] = None):
        """テーブルの内容表示
        
        Args:
            table_name: テーブル名
            limit: 表示件数制限
        """
        # カラム情報を取得
        err,columns = self.db_manager.cmd_schema(table_name)
        if err is not None:
            self.console.print(f"[red]エラー '{err}' [/red]")
            return
            
        # データを取得
        err, results = self.db_manager.cmd_print_table(table_name, limit=limit)
        if err is not None:
            self.console.print(f"[red]エラー '{err}' [/red]")
            return
        
        # データ行を追加
        if results:
            # テーブル表示
            result_table = Table(title=f"{table_name}テーブル")
            # カラムヘッダーを追加
            for col in columns:
                result_table.add_column(col[1], style="cyan", no_wrap=False)
            for row in results:
                result_table.add_row(*[str(val) if val is not None else "" for val in row])
        else:
            self.console.print("[yellow]データがありません[/yellow]")
            return
            
        self.console.print(result_table)

    def cmd_summary(self, period: str, number: Optional[int] = None, date_str: Optional[str] = None):
        """日次/月次/年次の取引サマリ
        
        Args:
            period: day, month, year
            number: 直近の期間数
            date_str: 起点となる日付 (YYYY-MM-DD形式)
        """
        err,results = self.db_manager.cmd_summary(period, number, date_str)
        if err is not None:
            self.console.print(f"[red]エラー: {err}[/red]")
            return
        period_name = {"day":"日付","month":"年月","year":"年"}.get(period, "期間")
        
        if results:
            table = Table(title=f"{period_name}別 取引サマリ")
            table.add_column(period_name, style="cyan", no_wrap=True)
            table.add_column("支出", justify="right", style="red")
            table.add_column("収入", justify="right", style="green")
            table.add_column("合計", justify="right", style="yellow")
            table.add_column("振替", justify="right", style="blue")
            
            for row in results:
                table.add_row(
                    str(row[0]),
                    f"{row[1]:,.0f}" if row[1] else "0",
                    f"{row[2]:,.0f}" if row[2] else "0",
                    f"{row[3]:,.0f}" if row[3] else "0",
                    f"{row[4]:,.0f}" if row[4] else "0"
                )
                
            self.console.print(table)
        else:
            self.console.print("[yellow]データがありません[/yellow]")

    def cmd_summary_account(self, period: str, number: Optional[int] = None, date_str: Optional[str] = None):
        """月次/年次のアカウント毎取引内容サマリ
        
        Args:
            period: month, year
            number: 直近の期間数
            date_str: 起点となる日付 (YYYY-MM-DD形式)
        """
        err,results = self.db_manager.cmd_summary_account(period, number, date_str)
        if err is not None:
            self.console.print(f"[red]エラー: {err}[/red]")
            return
        period_name = {"day":"日付","month":"年月","year":"年"}.get(period, "期間")
        
        if results:
            table = Table(title=f"アカウント別 {period_name}別 取引サマリ")
            table.add_column(period_name, style="cyan", no_wrap=True)
            table.add_column("口座名", style="magenta", no_wrap=True)
            table.add_column("支出", justify="right", style="red")
            table.add_column("収入", justify="right", style="green")
            table.add_column("合計", justify="right", style="yellow")
            table.add_column("振替", justify="right", style="blue")
            table.add_column("残高", justify="right", style="cyan")
            
            for row in results:
                table.add_row(
                    str(row[0]),
                    str(row[1]),
                    f"{row[2]:,.0f}" if row[2] else "0",
                    f"{row[3]:,.0f}" if row[3] else "0",
                    f"{row[4]:,.0f}" if row[4] else "0",
                    f"{row[5]:,.0f}" if row[5] else "0",
                    f"{row[6]:,.0f}" if row[6] else "0"
                )
                
            self.console.print(table)
        else:
            self.console.print("[yellow]データがありません[/yellow]")


    def cmd_sum_logs(self, log_id:int ):
        """ 指定したcsvfile IDで登録された取引のサマリ合計の表示

        Args:
            log_id (int): ログID

        """
        err,results = self.db_manager.cmd_sum_logs(log_id)
        if err is not None:
            self.console.print(f"[red]エラー: {err}[/red]")
            return
        
        if results:
            table = Table(title=f"log_id={log_id} の取引サマリ")
            table.add_column("件数", justify="right", style="cyan")
            table.add_column("支出", justify="right", style="red")
            table.add_column("収入", justify="right", style="green")
            table.add_column("合計", justify="right", style="yellow")
            table.add_column("振替", justify="right", style="blue")
            
            for row in results:
                table.add_row(
                    f"{row[0]:,.0f}" if row[0] else "0",
                    f"{row[1]:,.0f}" if row[1] else "0",
                    f"{row[2]:,.0f}" if row[2] else "0",
                    f"{row[3]:,.0f}" if row[3] else "0",
                    f"{row[4]:,.0f}" if row[4] else "0"
                )
                
            self.console.print(table)
        else:
            self.console.print("[yellow]データがありません[/yellow]")

            
    def cmd_summary_category(self, period: str, number: Optional[int] = None, date_str: Optional[str] = None):
        """月次/年次のアカウント-カテゴリ毎取引内容サマリ
        
        Args:
            period: month, year
            number: 直近の期間数
            date_str: 起点となる日付 (YYYY-MM-DD形式)
        """
        err,results = self.db_manager.cmd_summary_category(period, number, date_str)
        if err is not None:
            self.console.print(f"[red]エラー: {err}[/red]")
            return
        period_name = {"day":"日付","month":"年月","year":"年"}.get(period, "期間")

        if results:
            table = Table(title=f"アカウント-カテゴリ別 {period_name}別 取引サマリ")
            table.add_column(period_name, style="cyan", no_wrap=True)
            table.add_column("口座名", style="magenta", no_wrap=True)
            table.add_column("カテゴリ", style="blue", no_wrap=True)
            table.add_column("支出", justify="right", style="red")
            table.add_column("収入", justify="right", style="green")
            table.add_column("合計", justify="right", style="yellow")
            table.add_column("振替", justify="right", style="blue")
            table.add_column("残高", justify="right", style="cyan")

            for row in results:
                table.add_row(
                    str(row[0]),
                    str(row[1]),
                    str(row[2]) if row[2] else "（未分類）",
                    f"{row[3]:,.0f}" if row[3] else "0",
                    f"{row[4]:,.0f}" if row[4] else "0",
                    f"{row[5]:,.0f}" if row[5] else "0",
                    f"{row[6]:,.0f}" if row[6] else "0",
                    f"{row[7]:,.0f}" if row[7] else "0"
                )
                
            self.console.print(table)
        else:
            self.console.print("[yellow]データがありません[/yellow]")

            
    def cmd_balance(self, date_str: str):
        """指定日での残高の確認
        
        Args:
            date_str: 日付 (YYYY-MM-DD形式)
        """
        err,results = self.db_manager.cmd_balance(date_str)
        target_date = self.db_manager.strptime(date_str)
        if err is not None or target_date is None:
            self.console.print(f"[red]エラー: {err}[/red]")
            return

        if results:
            table = Table(title=f"{target_date} 時点の残高")
            table.add_column("口座名", style="cyan", no_wrap=True)
            table.add_column("支出", justify="right", style="red")
            table.add_column("収入", justify="right", style="green")
            table.add_column("残高", justify="right", style="green")
                
            for row in results:
                table.add_row(
                    str(row[0]),
                    f"{row[1]:,.0f}" if row[1] else "0",
                    f"{row[2]:,.0f}" if row[2] else "0",
                    f"{row[3]:,.0f}" if row[3] else "0"
                )
                    
            self.console.print(table)
        else:
            self.console.print("[yellow]データがありません[/yellow]")
            
    def cmd_register(self, filename: str, agent_name: str, orginal_file: Optional[str] = None):
        """ロード用のcsvファイルの登録
        
        Args:
            filename: ファイル名
            agent_name: エージェント名
        """
        try:
            # agentsテーブルでagent_nameを確認
            mesgs,agent_id = self.db_manager.register_csvfile(filename, agent_name, orginal_file)
            if agent_id is None:
                for mesg in mesgs:
                    self.console.print(f"[red]エラー: {mesg}[/red]")
                return
            for mesg in mesgs:
                self.console.print(f"{mesg}")

            self.console.print(f"[green]CSVファイル '{filename}' を登録しました (ID: {agent_id})[/green]")
            
        except Exception as e:
            self.console.print(f"[red]レジスタエラー: {e}[/red]")

    def cmd_del_agent(self, agent_id: str):
        """エージェントテーブルのデータ削除

        Args:
            agent_id (str): _description_
        """
        try:
            agent_id_int = int(agent_id)
            mesg, res = self.db_manager.del_agent(agent_id_int)
            if res is None:
                self.console.print(f"[red]エラー: {mesg}[/red]")
                return
            self.console.print(f"{mesg}")

            self.console.print(f"[green]エージェント'{agent_id}' を削除しました ({res})[/green]")
            
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")

    def cmd_del_csvfile(self, csvfile_id: str):
        """エージェントテーブルのデータ削除

        Args:
            agent_id (str): _description_
        """
        try:
            csvfile_id_int = int(csvfile_id)
            mesg, res = self.db_manager.del_csvfile(csvfile_id_int)
            if res is None:
                self.console.print(f"[red]エラー: {mesg}[/red]")
                return
            self.console.print(f"{mesg}")
            self.console.print(f"[green]csvfile '{csvfile_id}' を削除しました ({res})[/green]")
            
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")
    
    def cmd_ins_agent(self, name: str, prompt_file: str):
        """エージェントの追加
        
        Args:
            name: エージェント名
            prompt_file: プロンプトファイルのパス
        """
        try:
            mesg, res = self.db_manager.insert_agent(name, prompt_file)
            self.console.print(f"{mesg}")
            
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")
    
    def cmd_ins_account(self, name: str, account_type: str):
        """アカウントの追加
        
        Args:
            name: アカウント名
            account_type: アカウントタイプ
        """
        try:
            mesg, res = self.db_manager.insert_account(name, account_type)
            self.console.print(f"{mesg}")
            
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")
    
    def cmd_del_account(self, account_id: str):
        """アカウントの削除
        
        Args:
            account_id: アカウントID
        """
        try:
            account_id_int = int(account_id)
            mesg, res = self.db_manager.del_account(account_id_int)
            self.console.print(f"{mesg}")
            
        except ValueError:
            self.console.print(f"[red]account_idは数値で指定してください: {account_id}[/red]")
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")
            
    def cmd_load_csv(self, csvfile_id: str):
        """csvファイルのデータ読み込み実行
        
        Args:
            csvfile_id: csvfilesテーブルのID
        """
        try:
            csvfile_id_int = int(csvfile_id)
            
            # csvfile情報を取得（agentsテーブルと結合して名前を取得）
            err,result = self.db_manager.cmd_csvfiles(csvfile_id_int)
            if err is not None:
                self.console.print(f"[red]エラー：csvfile_id '{csvfile_id}' が見つかりません。{err}[/red]")
                return
                
            file_path, agent_name, loaded_date = result[0]
            
            if loaded_date:
                self.console.print(f"[yellow]警告: このCSVファイルは既にロード済みです (loaded_date: {loaded_date})[/yellow]")
                
            # db_lib.pyのload_csv_file関数を呼び出し
            self.console.print(f"[cyan]CSVファイルをロード中...[/cyan]")
            self.console.print(f"  ファイル: {file_path} / エージェント: {agent_name}")
            
            # db_loaderインスタンスを作成してロード実行
            result = self.db_manager.load_csv_file(csvfile_id_int)
            
            if result.get("success"):
                self.console.print(f"[green]CSVファイルのロードが完了しました[/green]")
                self.console.print(f"  トランザクション数: {result.get('transactions_inserted', 0)}")
                self.console.print(f"  タグ数: {result.get('tags_inserted', 0)}")
                self.console.print(f"  ログID: {result.get('log_id', 'N/A')}")
            else:
                self.console.print(f"[red]CSVファイルのロードに失敗しました[/red]")
                if result.get("error"):
                    self.console.print(f"  エラー: {result.get('error')}")
                
        except ValueError:
            self.console.print(f"[red]csvfile_idは数値で指定してください: {csvfile_id}[/red]")
        except Exception as e:
            self.console.print(f"[red]ロードエラー: {e}[/red]")
            
    def cmd_rollback_csv(self, csvfile_id: str):
        """指定したcsvfile_idでロードしたデータのロールバック
        
        Args:
            csvfile_id: csvfilesテーブルのID
        """
        try:
            csvfile_id_int = int(csvfile_id)

            mesgs, num_logs = self.db_manager.rollback_csv_files(csvfile_id_int)
            if num_logs is None:
                for mesg in mesgs:
                    self.console.print(f"[red]エラー: {mesg}[/red]")
                return
            for mesg in mesgs:
                self.console.print(f"{mesg}")

            self.console.print(f"[green]ロールバックしました (ID: {csvfile_id})[/green]")

        except ValueError as e:
            self.console.print(f"[red]csvfile_idは数値で指定してください: {csvfile_id}[/red]")
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")

    def cmd_journalize(self, bank_name: str, csvfile_path: str):
        """指定したCSVファイルでロードしたデータの仕訳実行

        Args:
            bank_name: 銀行名
            csvfile_path: CSVファイルのパス
        """
        try:
            if bank_name not in self.jornalizers:
                self.jornalizers[bank_name] = TransactionJournalizer(self.config, bank_name)
                
            tj = self.jornalizers[bank_name]

            output_csv, log_file = tj.process_file(csvfile_path)

            mesg, num_logs = self.db_manager.register_agent(bank_name, str(tj.bank_prompt_file))
            if num_logs is None:
                self.console.print(f"[red]エラー: {mesg}[/red]")
                return
            self.console.print(f"{mesg}")

            mesg, num_logs = self.db_manager.register_csvfile(output_csv, bank_name,csvfile_path)
            if num_logs is None:
                self.console.print(f"[red]エラー: {mesg}[/red]")
                return
            self.console.print(f"{mesg}")

        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")

    def cmd_archive_csv(self, csvfile_ids_str: str):
        """CSVファイルをアーカイブする
        
        Args:
            csvfile_ids: CSVファイルIDのリスト（カンマ区切りやハイフン範囲指定可）
        """
        try:
            csvfile_ids = self.parse_csvfile_ids(csvfile_ids_str)
            mesgs, archive_id = self.db_manager.archive_csv(csvfile_ids)
            
            for mesg in mesgs:
                self.console.print(mesg)
                
            if archive_id is None:
                self.console.print(f"[red]アーカイブに失敗しました[/red]")
            
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")

    def cmd_extract(self, archive_id: str):
        """アーカイブからCSVファイルを復元する
        
        Args:
            archive_id: アーカイブID
        """
        try:
            archive_id_int = int(archive_id)
            mesgs, extracted_count = self.db_manager.extract(archive_id_int)
            
            for mesg in mesgs:
                self.console.print(mesg)
                
            if extracted_count is None:
                self.console.print(f"[red]復元に失敗しました[/red]")
                
        except ValueError:
            self.console.print(f"[red]archive_idは数値で指定してください: {archive_id}[/red]")
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")

    def cmd_doSQL(self, sqlfile: str, args: Tuple ):
        """SQL文を実行
        Args:
            sql: 実行するSQL文
        """
        try:
            if not sqlfile or not os.path.exists(sqlfile):
                self.console.print(f"[red]エラー: SQLファイル '{sqlfile}' が見つかりません[/red]")
                return

            with open(sqlfile, "r") as f:
                sql = f.readlines()

            if sql is None or len(sql) == 0:
                self.console.print(f"[red]エラー: SQL文が空です[/red]")
                return
            
            if len(sql) > 1 and sql[0].startswith('---'):
                columns = sql[0].strip().strip('-').strip().split(',')
                sql = ''.join(sql[1:]).strip()
            else:
                columns = None
                sql = ''.join(sql).strip()

            mesg,results = self.db_manager.execute_query(sql, args)

            if mesg is not None:
                self.console.print(f"{mesg}")
                return

            if results:
                def transform_value(val):
                    if isinstance(val, float) or isinstance(val, int):
                        return f"{val:,.0f}"
                    return str(val) if val is not None else ""
                table = Table(title="SQL実行結果")
                # カラムヘッダーを追加
                if columns is not None:
                    for col in columns:
                        table.add_column(col, style="cyan", no_wrap=False)
                for row in results:
                    table.add_row(*[transform_value(row[i]) for i in range(len(row))])

                self.console.print(table)

        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")

    

    def save_history(self):
        """履歴を保存"""
        try:
            readline.write_history_file(self.history_file)
        except:
            pass
    
    def execute_command(self, command: str) -> bool:
        """単一のコマンドを実行
        
        Args:
            command: 実行するコマンド文字列
            
        Returns:
            bool: コマンドが正常に実行された場合True
        """
        try:
            if not command:
                return False
                
            # コマンドをパース
            parts = command.strip().split()
            if not parts:
                return False
                
            cmd = parts[0].lower()
            
            # 終了コマンド（非対話モードではスキップ）
            if cmd in ["exit", "quit"]:
                return False
                
            # ヘルプ
            elif cmd == "help":
                self._show_help()
                
            # tables コマンド
            elif cmd == "tables":
                self.cmd_tables()
                
            # count コマンド
            elif cmd == "count":
                if len(parts) < 2:
                    self.console.print("[red]使用法: count <table_name>|all[/red]")
                    return False
                else:
                    self.cmd_count(parts[1])
                    
            # P (print) コマンド
            elif cmd.lower() == "p":
                if len(parts) < 2:
                    self.console.print("[red]使用法: P <table_name> [limit][/red]")
                    return False
                else:
                    limit = int(parts[2]) if len(parts) > 2 else None
                    self.cmd_print_table(parts[1], limit)
                    
            # sum コマンド
            elif cmd == "sum":
                if len(parts) < 2:
                    self.console.print("[red]使用法: sum day|month|year [number] [date][/red]")
                    return False
                else:
                    number = int(parts[2]) if len(parts) > 2 else None
                    date_str = parts[3] if len(parts) > 3 else None
                    self.cmd_summary(parts[1], number, date_str)

            # sum_account コマンド
            elif cmd == "sum_account":
                if len(parts) < 2:
                    self.console.print("[red]使用法: sum_account month|year [number] [date] [/red]",markup=False)
                    return False
                else:
                    number = int(parts[2]) if len(parts) > 2 else None
                    date_str = parts[3] if len(parts) > 3 else None
                    self.cmd_summary_account(parts[1], number, date_str)
                    
            # sum_category コマンド
            elif cmd == "sum_category":
                if len(parts) < 2:
                    self.console.print("[red]使用法: sum_category month|year [number] [date] [/red]",markup=False)
                    return False
                else:
                    number = int(parts[2]) if len(parts) > 2 else None
                    date_str = parts[3] if len(parts) > 3 else None
                    self.cmd_summary_category(parts[1], number, date_str)

            # sum_log コマンド
            elif cmd == "sum_log":
                if len(parts) < 2:
                    self.console.print("[red]使用法: sum_log <log_id>[/red]")
                    return False
                else:
                    self.cmd_sum_logs(int(parts[1]))

            # balance コマンド
            elif cmd == "balance":
                if len(parts) < 2:
                    self.console.print("[red]使用法: balance YYYY-MM-DD[/red]")
                    return False
                else:
                    self.cmd_balance(parts[1])
                    
            # register コマンド
            elif cmd == "register":
                if len(parts) < 3:
                    self.console.print("[red]使用法: register <filename> <agent>[/red]")
                    return False
                else:
                    self.cmd_register(parts[1], parts[2])
                    
            # load_csv コマンド
            elif cmd == "load_csv":
                if len(parts) < 2:
                    self.console.print("[red]使用法: load_csv <csvfile_id>[/red]")
                    return False
                else:
                    self.cmd_load_csv(parts[1])
                    
            # rollback_csv コマンド
            elif cmd == "rollback_csv":
                if len(parts) < 2:
                    self.console.print("[red]使用法: rollback_csv <csvfile_id>[/red]")
                    return False
                else:
                    self.cmd_rollback_csv(parts[1])

            # journalize コマンド
            elif cmd == "journalize":
                if len(parts) < 3:
                    self.console.print("[red]使用法: journalize <bank_name> <csvfile_file>[/red]")
                    return False
                else:
                    self.cmd_journalize(parts[1], parts[2])

            # del_agent コマンド
            elif cmd == "del_agent":
                if len(parts) < 2:
                    self.console.print("[red]使用法: del_agent <agent_id>[/red]")
                    return False
                else:
                    self.cmd_del_agent(parts[1])

            # del_csvfile コマンド
            elif cmd == "del_csvfile":
                if len(parts) < 2:
                    self.console.print("[red]使用法: del_csvfile <csvfil_id>[/red]")
                    return False
                else:
                    self.cmd_del_csvfile(parts[1])
            
            # ins_agent コマンド
            elif cmd == "ins_agent":
                if len(parts) < 3:
                    self.console.print("[red]使用法: ins_agent <name> <prompt_file>[/red]")
                    return False
                else:
                    self.cmd_ins_agent(parts[1], parts[2])
            
            # ins_account コマンド
            elif cmd == "ins_account":
                if len(parts) < 3:
                    self.console.print("[red]使用法: ins_account <name> <account_type>[/red]")
                    return False
                else:
                    self.cmd_ins_account(parts[1], parts[2])
            
            # del_account コマンド
            elif cmd == "del_account":
                if len(parts) < 2:
                    self.console.print("[red]使用法: del_account <account_id>[/red]")
                    return False
                else:
                    self.cmd_del_account(parts[1])

            # archive_csv コマンド
            elif cmd == "archive_csv":
                if len(parts) < 2:
                    self.console.print("[red]使用法: archive_csv <csvfile_ids>[/red]")
                    self.console.print("[yellow]  例: archive_csv 1,3-5,7[/yellow]")
                    return False
                else:
                    self.cmd_archive_csv(parts[1])

            # extract コマンド
            elif cmd == "extract":
                if len(parts) < 2:
                    self.console.print("[red]使用法: extract <archive_id>[/red]")
                    return False
                else:
                    self.cmd_extract(parts[1])

            elif cmd == "dosql":
                if len(parts) < 2:
                    self.console.print("[red]使用法: dosql <sqlfile> [args ...][/red]")
                    return False
                else:
                    sqlfile = self.sql_file_dir + parts[1]
                    args = tuple(parts[2:]) if len(parts) > 2 else ()
                    self.cmd_doSQL(sqlfile, args)        
                    
            else:
                self.console.print(f"[red]不明なコマンド: {cmd}[/red]")
                self.console.print("[yellow]'help' でコマンド一覧を表示[/yellow]")
                return False
            
            return True
                    
        except Exception as e:
            self.console.print(f"[red]エラー: {e}[/red]")
            return False

    def _show_help(self):
        """ヘルプメッセージを表示"""
        help_text1 = """
[bold]使用可能なコマンド:[/bold]
"""
        help_text2 = """
  tables                                   - テーブル名のリスト表示
  count <table>|all                        - テーブルの件数表示
  P <table> [limit]                        - テーブル内容表示
  sum <period> [num]                       - 取引サマリ (period: day/month/year)
  sum_account <period> [num [YYYY-MM-DD]]  - アカウント別サマリ
  sum_category <period> [num [YYYY-MM-DD]] - カテゴリ別サマリ
  balance YYYY-MM-DD                       - 指定日の残高確認
  register <file> <agent> [original_file]  - CSVファイル登録
  load_csv <id>                            - CSVロード実行
  sum_log <log_id>                         - 指定したcsvfile_idで登録された取引のサマリ合計表示
  rollback_csv <id>                        - CSVロールバック
  archive_csv <ids>                        - CSVファイルをアーカイブ (例: 1,3-5,7)
  extract <archive_id>                     - アーカイブからCSVファイルを復元
  ins_agent <name> <prompt_file>           - エージェントの追加
  del_agent <agent_id>                     - エージェントテーブルのデータ削除
  ins_account <name> <account_type>        - アカウントの追加
  del_account <account_id>                 - アカウントの削除
  del_csvfile <csvfile_id>                 - csvfileテーブルのデータ削除
  journalize <bank_name> <orgfile>         - orgfileの仕訳実行
  help                                     - ヘルプ表示
  exit/quit/Ctrl-D                         - 終了
"""

        help_text3 = """
[bold]キーボードショートカット:[/bold]
  ↑ (矢印上)                 - コマンド履歴を前へ
  ↓ (矢印下)                 - コマンド履歴を次へ  
  Ctrl-D                    - アプリケーションを終了
        """
        self.console.print(help_text1)
        self.console.print(help_text2,markup=False)
        self.console.print(help_text3)

    def run_command_mode(self, command: str):
        """コマンドモードで単一コマンドを実行して終了
        
        Args:
            command: 実行するコマンド
        """
        # データベース接続
        res = self.db_manager.connect()
        if res is not None:
            self.console.print(f"[red]データベース接続エラー: {res}[/red]")
            sys.exit(1)
            
        # コマンド実行
        success = self.execute_command(command)
        
        # 終了処理
        self.db_manager.disconnect()
        sys.exit(0 if success else 1)

    def run(self):
        """メインループ（インタラクティブモード）"""
        # データベース接続
        res = self.db_manager.connect()
        if res is not None:
            self.console.print(f"[red]データベース接続エラー: {res}[/red]")
            return
            
        # ウェルカムメッセージ
        self.console.print(Panel.fit(
            "[bold cyan]家計簿データベース CLIインターフェース[/bold cyan]\n"
            "コマンドを入力してください (終了: exit/quit/Ctrl-D)\n"
            "矢印キー↑↓でコマンド履歴を参照できます",
            border_style="cyan"
        ))
        
        # コマンドヘルプを表示
        self._show_help()
        
        # メインループ
        while True:
            try:
                # プロンプト表示と入力取得
                command = input("has-cli > ")
                
                # 終了コマンドのチェック
                if command.strip().lower() in ["exit", "quit"]:
                    self.console.print("[cyan]終了します[/cyan]")
                    break
                
                # コマンド実行
                self.execute_command(command)
                    
            except KeyboardInterrupt:
                self.console.print("\n[cyan]中断されました[/cyan]")
                continue
            except EOFError:
                # Ctrl-D が押された場合
                self.console.print("\n[cyan]終了します (Ctrl-D)[/cyan]")
                break
            except Exception as e:
                self.console.print(f"[red]エラー: {e}[/red]")
                
        # 終了処理
        self.save_history()
        self.db_manager.disconnect()


def main():
    """メイン関数"""
    # コマンドライン引数のパーサーを作成
    parser = argparse.ArgumentParser(
        description='家計簿データベース CLIインターフェース',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # インタラクティブモード
  python has-cli.py
  
  # コマンドモード
  python has-cli.py -c "tables"
  python has-cli.py -c "count all"
  python has-cli.py -c "sum month 3"
  python has-cli.py -c "balance 2025-01-01"
        """
    )
    parser.add_argument(
        '-c', '--command',
        type=str,
        help='実行するコマンドを指定 (非対話モード)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='./config.ini',
        help='設定ファイルのパス (デフォルト: ./config.ini)'
    )
    parser.add_argument(
        '--initdb',action='store_true',
        help='データベースの初期化 '
    )
    
    # 引数を解析
    args = parser.parse_args()
    
    # CLIインスタンスを作成
    cli = HasCLI(config_path_str=args.config)

    if args.initdb:
        # データベースの初期化
        if os.path.exists(cli.db_path):
            cli.console.print(f"[red]エラー: データベースファイルが既に存在します: {cli.db_path}[/red]")
            sys.exit(1)
        init_database(db_path_arg=cli.db_path, ddl_path_arg=cli.ddl_dir)
        cli.console.print(f"[green]データベースを初期化しました: {cli.db_path}[/green]")
        sys.exit(0)

    # コマンドモードか対話モードかを判定
    if args.command:
        # コマンドモード: 指定されたコマンドを実行して終了
        cli.run_command_mode(args.command)
    else:
        # 対話モード: 通常の対話型インターフェースを起動
        cli.run()


if __name__ == "__main__":
    main()
