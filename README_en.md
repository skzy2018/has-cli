# HAS-CLI - Household Accounting System CLI Application

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Overview

HAS-CLI (Household Accounting System CLI) is a household accounting management application operated through a command-line interface. It provides automatic journalization of bank transaction data, database storage, and various reporting features.

## Motivation

There are countless household accounting tools in the world. Advanced tools can now semi-automatically aggregate and manage individual assets through online service integration with various credit cards and bank accounts. However, tools that can integrate with "transaction details" from all various systems are technically challenging due to dependencies on the integrated systems and environments. Moreover, integration inevitably requires managing individual users' ID information, which often causes hesitation from both service providers and users from a security perspective.

This tool focuses on journalizing "transaction details" exported from other systems so they can be registered as your household accounting data, rather than focusing on integration with other systems.

Users download transaction details from their credit cards and bank accounts. After setting up AI prompts for journalization, when these files are loaded, the AI performs the journalization. The journalized data can then be registered in the household accounting database and aggregated in tabular format.

### Main Features

- 🤖 **AI Auto-Journalization** - Automatic categorization of transactions using LLM (GPT-4/Claude)

   As mentioned above, uses AI (LLM) to journalize transaction data for the household accounting database. The journalization method can be customized with prompts.
   
- 📊 **Tabular Output** - Daily/monthly/yearly summaries, balance checks, category-based aggregation

   Simple aggregation commands are provided. You can also load SQL files and output them in tabular format (doSQL command).
   
- ⌨️ **Interactive CLI** - With tab completion and command history features

   Execution is performed through CLI.

## Requirements
  Since it uses AI (LLM), please prepare API keys for queries.

- Python 3.10 or higher
- SQLite3
- OpenAI API key or Anthropic API key

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/has-cli.git
cd has-cli
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Prepare Configuration Files

```bash
# Copy configuration file
cp config.ini.sample config.ini
```

### 4. Initialize Database

```bash
python has-cli/has-cli.py --initdb
```

## Configuration

### config.ini Settings

```ini
[llm]
# LLM provider: openai or anthropic
provider = openai

# Model specification
openai_model = gpt-4o
anthropic_model = claude-3-sonnet-20240229

[file_config]
# Prompt file paths
system_prompt = ./prompts/system.txt
prompts_format = ./prompts/tj_{name}.txt

# Output file formats
out_csv_format = ./csv/tj_{name}_{time}_{stem}.csv
log_format = ./log/journalize_{time}.log

[database]
# Database file location
database = ./data/db/database.sqlite
# Database DDL statements (no need to edit)
ddl_dir = ./data/ddl

# SQL files for doSQL command execution
sql_file = ./data/sql/{name}.sql
# Default currency value
account_default_currency = 'JPY'

[processing]
# Number of transactions to process at once
chunk_size = 10
```

## Usage

### Starting the Application

```bash
# Interactive mode
python has-cli/has-cli.py

# Command mode (single command execution)
python has-cli/has-cli.py -c "tables"
python has-cli/has-cli.py -c "sum month 3"

# Specify custom configuration file
python has-cli/has-cli.py --config ./custom_config.ini
```

### Basic Workflow

1. **Journalize Transaction Data**

   Apply AI auto-journalization to CSV/PDF files of transaction data obtained individually from each account.

   Example:
   - Account transaction data (transactions.csv) ... Can read CSV or PDF
   - Account name (smbc) ... This becomes the agent name
   ```
   has-cli > journalize smbc transactions.csv
   ```
   Upon successful auto-journalization, a journalized CSV file is generated using out_csv_format as the format and registered in the csvfiles table in the database.

2. **Register Journalized Data**

   Already journalized CSV files can be registered in the database using the register command.

   Example:
   - Journalized CSV file (tr_smbc_20250106_transactions.csv)
   - Agent name (smbc)
   ```
   has-cli > register csv/tr_smbc_20250106_transactions.csv smbc
   ```
   For details on the journalized CSV file format, refer to the system prompt (prompts/system.txt).

3. **Load into Database**

   Execute the load_csv command with the ID registered in csvfiles as an argument to load the CSV file.
   ```
   has-cli > load_csv 1
   ```

4. **Check Reports**

   You can reference transaction data registered in the database with various commands.
   ```
   has-cli > sum month 3
   has-cli > balance 2025-01-06
   ```

## Command List

### Data Management Commands

| Command | Description | Example |
|---------|-------------|---------|
| `tables` | Display table list | `tables` |
| `count <table>` | Display table row count | `count transactions` |
| `P <table> [limit]` | Display table contents | `P accounts 10` |

### Transaction Data Processing

| Command | Description | Example |
|---------|-------------|---------|
| `journalize <bank> <file>` | Execute transaction data journalization | `journalize smbc data.csv` |
| `register <file> <agent> [original file]` | Register journalized CSV | `register output.csv smbc` |
| `load_csv <id>` | Register CSV data to DB | `load_csv 1` |
| `rollback_csv <id>` | Rollback registered data | `rollback_csv 1` |
| `archive_csv <ids>` | Archive CSV files | `archive_csv 1,3-5,7` |
| `extract <archive_id>` | Restore CSV files from archive | `extract 1` |

### Reports and Aggregation

| Command | Description | Example |
|---------|-------------|---------|
| `sum <period> [num] [date]` | Period-based transaction summary | `sum month 3 2025-01-01` |
| `sum_account <period> [num] [date]` | Account-based summary | `sum_account year 2` |
| `sum_category <period> [num] [date]` | Category-based summary | `sum_category month 6` |
| `sum_log <log_id>` | Specific load aggregation | `sum_log 5` |
| `balance <date>` | Check balance on specified date | `balance 2025-01-06` |

### Management Commands

| Command | Description | Example |
|---------|-------------|---------|
| `del_agent <id>` | Delete agent | `del_agent 1` |
| `del_csvfile <id>` | Delete CSV file information | `del_csvfile 1` |
| `help` | Display help | `help` |
| `exit` / `quit` | Exit application | `exit` |

### Keyboard Shortcuts

- `↑` / `↓` : Browse command history
- `Tab` : Auto-completion for commands and arguments
- `Ctrl+D` : Exit application

## Database Structure

### Main Tables

| Table Name | Description |
|------------|-------------|
| `accounts` | Account information (bank accounts, credit cards, etc.) |
| `agents` | Journalization agent information (prompt management per bank) |
| `categories` | Transaction category master |
| `transactions` | Transaction data (expenses are negative, income is positive) |
| `transfers` | Transfer transaction management |
| `tags` | Tag master |
| `transaction_tags` | Transaction-tag associations |
| `csvfiles` | Imported CSV file information (includes archive_id) |
| `data_logs` | Data load history |
| `archives` | Archive file management |

### Transaction Table Structure

```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,      -- Account ID
    category_id INTEGER NOT NULL,     -- Category ID
    amount REAL NOT NULL,              -- Amount (expense: negative, income: positive)
    item_name TEXT,                    -- Item name
    description TEXT,                  -- Description
    transaction_date DATETIME NOT NULL,-- Transaction date
    memo TEXT,                         -- Memo
    ...
);
```

## AI Journalization Feature

### How It Works

1. **Load Transaction Data** - Extract transaction data from CSV/PDF files
2. **Format Analysis** - AI analyzes the format of transaction data
3. **Journalization Processing** - Classify each transaction into appropriate categories
4. **CSV Output** - Output journalized data in CSV format

### Bank-Specific Prompts

Prompts corresponding to each bank's transaction format are automatically generated and saved in `prompts/tr_{bank_name}.txt`. This enables journalization optimized for bank-specific formats.

### Supported File Formats

- CSV format (`.csv`)
- PDF format (`.pdf`) - Bank transaction statement PDFs

## CSV File Archive Feature

### Overview

You can save disk space by compressing used CSV files into archives. Archived files can be restored when needed.

### How Archive Works

- Compresses specified CSV files into ZIP format
- Archives both the main CSV file and the original file (recorded in the `org_name` column)
- Original files are automatically deleted after archiving
- Archive information is managed in the `archives` table in the database
- Tracks archive status by recording `archive_id` in the `csvfiles` table

### Usage Examples

#### Archiving CSV Files

```bash
# Archive single file
has-cli > archive_csv 1

# Archive multiple files (comma-separated)
has-cli > archive_csv 1,3,5

# Archive with range specification
has-cli > archive_csv 1-5

# Combined specification
has-cli > archive_csv 1,3-5,7,10-12
```

#### Restoring from Archive

```bash
# Restore files from archive ID 1
has-cli > extract 1
```

### Important Notes

- Already archived CSV files cannot be archived again
- Archive files are stored in the `data/arch/` directory
- When restoring, archive files are automatically deleted
- Files already loaded into the database can also be archived (transaction data remains in the database)

### Customizing Archive Filename

You can configure the archive filename format in `config.ini`:

```ini
[database]
# Archive filename format
# Available variables: {id} (archive ID), {time} (timestamp)
archive_file_format = {id}_{time}.zip
```

## Project Structure

```
has-cli/
├── has-cli/
│   ├── has-cli.py              # Main CLI application
│   ├── db_lib.py               # Database operation library
│   ├── transaction_journalizer.py  # AI journalization processing
│   └── init_db.py              # Database initialization script
├── data/
│   ├── arch/                   # Archive file storage
│   ├── db/                     # SQLite database
│   ├── ddl/                    # Table definition SQL
│   ├── csv/                    # Journalized CSV file output destination
│   ├── prompts/                # AI prompt files
│   └── sql/                    # SQL files for doSQL command execution
├── log/                        # Log file output destination
├── config.ini                  # Application settings
├── .env                        # Environment variables (API keys, etc.)
└── requirements.txt            # Python dependencies
```

## Troubleshooting

### When Journalization Is Not Working Correctly

1. Check LLM model settings in `config.ini`
2. Check system prompt in `prompts/system.txt`

## License

This project is released under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributing

For major changes, please open an issue first to discuss what you would like to change.

### Contributing Steps

1. Fork this repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Create a Pull Request

### Development Environment Setup

```bash
# Create virtual environment
python -m venv env
source env/bin/activate  # Windows: env\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
```

## Support

- 🐛 Bug Reports: Please create an [Issue](https://github.com/skzy2018/has-cli/issues)
- 💡 Feature Requests: Please propose in [Discussion](https://github.com/skzy2018/has-cli/discussions)
- 📧 Contact: skzy2018

## Author

- **TSekizima** - [GitHub](https://github.com/skzy2018)
