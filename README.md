# HAS-CLI - 家計簿管理CLIアプリケーション

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## 概要

HAS-CLI（Household Accounting System CLI）は、コマンドラインインターフェースで操作する家計簿管理アプリケーションです。銀行取引データの自動仕訳、データベースへの保存、各種レポート機能を提供します。

## 動機

世に家計簿ツールは星の数ほどあります。そして、高機能なツールでは、各種クレジットカードや銀行口座に対するオンラインサービス連携により個人毎の資産を半自動的に集約して管理することもできるようになりました。しかし、すべての様々なシステムの"収支明細"と連携可能なツールは、連携先のシステム・環境にも依存し、技術的になかなか難しい、というのが実態です。また、連携にはどうしても個人ユーザのID情報を管理する必要があり、セキュリティの観点からサービスの提供側も利用ユーザ側も躊躇する場面が多くあります。

このツールでは、他システムとの連携よりも、他システムから出力された"収支明細"を、自分の家計簿のデータとして登録できるように、仕訳を行う点に焦点を当てます。

ユーザは自分のクレジットカードや銀行口座の取引明細をダウンロードします。仕訳のためのAIプロンプトを設定した上で、そのファイルを読み込ませると、AIを経由して仕訳を行ってくれます。仕訳したデータは家計簿データベースに登録して表形式で集計できるようになります。


### 主な特徴

- 🤖 **AI自動仕訳** - LLM（GPT-4/Claude）を使用した取引の自動カテゴライズ

   前述したように、AI(LLM)を用いて取引データを家計簿DB向けに仕訳します。仕分けの方法はプロンプトでカスタマイズできます。
- 📊 **表形式出力** - 日次・月次・年次サマリ、残高確認、カテゴリ別集計

   簡単な集計コマンドを用意しています。また、sqlファイルを読み込ませればそれを表形式で出力することもできます。(doSQLコマンド)
- ⌨️ **インタラクティブCLI** - タブ補完・コマンド履歴機能付き

   実行は、CLIで行います。


## 必要環境
  AI(LLM)を利用するため、問い合わせのためのAPIキーを用意してください。

- Python 3.10以上
- SQLite3
- OpenAI APIキー または Anthropic APIキー

## インストール

### 1. リポジトリのクローン

```bash
git clone https://github.com/yourusername/has-cli.git
cd has-cli
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. 設定ファイルの準備

```bash
# 設定ファイルのコピー
cp config.ini.sample config.ini
```


### 4. データベースの初期化 

```bash
python has-cli/has-cli.py --initdb
```

## 設定

### config.ini の設定項目

```ini
[llm]
# LLMプロバイダー: openai または anthropic
provider = openai

# モデル指定
openai_model = gpt-4o
anthropic_model = claude-3-sonnet-20240229

[file_config]
# プロンプトファイルのパス
system_prompt = ./prompts/system.txt
prompts_format = ./prompts/tj_{name}.txt

# 出力ファイルフォーマット
out_csv_format = ./csv/tj_{name}_{time}_{stem}.csv
log_format = ./log/journalize_{time}.log

[database]
# データベースのファイル配置
database = ./data/db/database.sqlite
# データベースのDDL文 (特に編集必要なし)
ddl_dir = ./data/ddl

# doSQLコマンドで実行するためのSQLファイルなど 
sql_file = ./data/sql/{name}.sql
# currencyのデフォルト値
account_default_currency = 'JPY'

[processing]
# 一度に処理するトランザクション数
chunk_size = 10
```

## 使用方法

### 起動

```bash
# インタラクティブモード
python has-cli/has-cli.py

# コマンドモード（単一コマンド実行）
python has-cli/has-cli.py -c "tables"
python has-cli/has-cli.py -c "sum month 3"

# カスタム設定ファイルを指定
python has-cli/has-cli.py --config ./custom_config.ini
```

### 基本的なワークフロー

1. **取引データの仕訳**

   個別に取得した各口座の取引データをCSV/PDFファイルをAI自動仕訳にかけます。

   例：
   - 口座の取引データ(transactions.csv) ... CSVかPDFを読み込み可能
   - 口座名(smbc) ... これがagentの名前になります。
   ```
   has-cli > journalize smbc transactions.csv
   ```
   自動仕分けに成功すると、out_csv_formatをフォーマットにしたの仕訳済みCSVファイルが生成され、DBのテーブルcsvfilesに登録されます。

2. **仕訳済みデータの登録**

   すでに仕分け済みのCSVファイルは、registerコマンドでDBに登録します。

   例：
   - 仕訳済みCSVファイル(tr_smbc_20250106_transactions.csv)
   - agent名(smbc)
   ```
   has-cli > register csv/tr_smbc_20250106_transactions.csv smbc
   ```
   仕訳済みCSVファイルのフォーマット詳細は、システムプロンプト(prompts/system.txt)を参照してください。

3. **データベースへのロード**

   csffilesで登録されたIDを引数にload_csvコマンドを実行すると、CSVファイルがロードされます。
   ```
   has-cli > load_csv 1
   ```

4. **レポートの確認**

   各コマンドでDBに登録された取引データを参照できます
   ```
   has-cli > sum month 3
   has-cli > balance 2025-01-06
   ```

## コマンド一覧

### データ管理コマンド

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `tables` | テーブル一覧を表示 | `tables` |
| `count <table>` | テーブルの件数を表示 | `count transactions` |
| `P <table> [limit]` | テーブル内容を表示 | `P accounts 10` |

### 取引データ処理

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `journalize <bank> <file>` | 取引データの仕訳実行 | `journalize smbc data.csv` |
| `register <file> <agent> [original file]` | 仕訳済みCSVの登録 | `register output.csv smbc` |
| `load_csv <id>` | CSVデータのDB登録 | `load_csv 1` |
| `rollback_csv <id>` | 登録データのロールバック | `rollback_csv 1` |

### レポート・集計

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `sum <period> [num] [date]` | 期間別取引サマリ | `sum month 3 2025-01-01` |
| `sum_account <period> [num] [date]` | アカウント別サマリ | `sum_account year 2` |
| `sum_category <period> [num] [date]` | カテゴリ別サマリ | `sum_category month 6` |
| `sum_log <log_id>` | 特定ロードの集計 | `sum_log 5` |
| `balance <date>` | 指定日の残高確認 | `balance 2025-01-06` |

### 管理コマンド

| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `del_agent <id>` | エージェント削除 | `del_agent 1` |
| `del_csvfile <id>` | CSVファイル情報削除 | `del_csvfile 1` |
| `help` | ヘルプ表示 | `help` |
| `exit` / `quit` | アプリケーション終了 | `exit` |

### キーボードショートカット

- `↑` / `↓` : コマンド履歴の参照
- `Tab` : コマンド・引数の自動補完
- `Ctrl+D` : アプリケーションの終了

## データベース構成

### 主要テーブル

| テーブル名 | 説明 |
|-----------|------|
| `accounts` | 口座情報（銀行口座、クレジットカード等） |
| `agents` | 仕訳エージェント情報（銀行毎のプロンプト管理） |
| `categories` | 取引カテゴリマスタ |
| `transactions` | 取引データ（支出は負数、収入は正数） |
| `transfers` | 振替取引管理 |
| `tags` | タグマスタ |
| `transaction_tags` | 取引とタグの関連付け |
| `csvfiles` | インポートしたCSVファイル情報 |
| `data_logs` | データロード履歴 |

### トランザクションテーブル構造

```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,      -- 口座ID
    category_id INTEGER NOT NULL,     -- カテゴリID
    amount REAL NOT NULL,              -- 金額（支出:負、収入:正）
    item_name TEXT,                    -- 項目名
    description TEXT,                  -- 説明
    transaction_date DATETIME NOT NULL,-- 取引日
    memo TEXT,                         -- メモ
    ...
);
```

## AI仕訳機能

### 仕組み

1. **取引データの読み込み** - CSV/PDFファイルから取引データを抽出
2. **フォーマット分析** - AIが取引データの形式を分析
3. **仕訳処理** - 各取引を適切なカテゴリに分類
4. **CSV出力** - 仕訳済みデータをCSV形式で出力

### 銀行別プロンプト

各銀行の取引フォーマットに対応したプロンプトが自動生成され、`prompts/tr_{bank_name}.txt`に保存されます。これにより、銀行固有のフォーマットに最適化された仕訳が可能になります。

### サポートファイル形式

- CSV形式（`.csv`）
- PDF形式（`.pdf`） - 銀行の取引明細PDF

## プロジェクト構造

```
has-cli/
├── has-cli/
│   ├── has-cli.py              # メインCLIアプリケーション
│   ├── db_lib.py               # データベース操作ライブラリ
│   ├── transaction_journalizer.py  # AI仕訳処理
│   └── init_db.py              # データベース初期化スクリプト
├── data/
│   ├── db/                     # SQLiteデータベース
│   └── ddl/                    # テーブル定義SQL
│   └── csv/                    # 仕訳済みCSVファイル出力先
│   └── prompts/                # AIプロンプトファイル
│   └── sql/                    # doSQLコマンドで実行するsqlファイル
├── log/                        # ログファイル出力先
├── config.ini                  # アプリケーション設定
├── .env                        # 環境変数（langsmith APIキー等）
└── requirements.txt            # Python依存パッケージ
```

## トラブルシューティング

### 仕訳が正しく行われない場合

1. `config.ini`のLLMモデル設定を確認
2. `prompts/system.txt`のシステムプロンプトを確認
3. `prompts/*.txt`の各仕訳Agentのプロンプトを確認

## ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。詳細は [LICENSE](LICENSE) ファイルを参照してください。

## 貢献

大きな変更を行う場合は、まずIssueを開いて、変更内容について議論してください。

### 開発環境のセットアップ

```bash
# 仮想環境の作成
python -m venv env
source env/bin/activate  # Windows: env\Scripts\activate

# 開発用依存関係のインストール
pip install -r requirements.txt
```

## サポート

- 🐛 バグ報告: [Issue](https://github.com/skzy2018/has-cli/issues)を作成してください
- 💡 機能リクエスト: [Discussion](https://github.com/skzy2018/has-cli/discussions)で提案してください
- 📧 お問い合わせ:skzy2018

## 作者

- **TSekizima** - [GitHub](https://github.com/skzy2018)
