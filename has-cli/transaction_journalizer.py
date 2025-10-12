#!/usr/bin/env python3
"""
Transaction Journalizer Class
============================

AI Agent class for processing bank and credit card transaction data files,
using LLM to journalize and categorize transactions.
"""

import csv
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, TypedDict,Generator
from pydantic import SecretStr
from dotenv import load_dotenv

import pandas as pd
try:
    from langchain_openai import ChatOpenAI  # type: ignore

except ImportError:
    print("langchain_openai could not be imported. Falling back to langchain.chat_models.")
    from langchain.chat_models import ChatOpenAI  # type: ignore
try:
    from langchain_anthropic import ChatAnthropic  # type: ignore
except ImportError:
    print("langchain_anthropic could not be imported. Falling back to langchain.chat_models.")
    from langchain.chat_models import ChatAnthropic  # type: ignore
try:
    from langchain_core.messages import HumanMessage, SystemMessage # type: ignore
except ImportError:
    from langchain.schema import HumanMessage, SystemMessage # type: ignore
try:
    from langchain_core.prompts import PromptTemplate # type: ignore
except ImportError:
    from langchain.prompts import PromptTemplate # type: ignore

# Define state schema for langgraph
class StateSchema(TypedDict):
    file_path: str
    bank_name: str
    timestamp: str
    #raw_data: Optional[str]
    #parsed_data: Optional[List[Dict[str, Any]]]
    chunked_data: Optional[List[str]]
    journalized_data: Optional[List[Dict[str, Any]]]
    output_file: Optional[str]

try:
    from langgraph.graph import StateGraph, END # type: ignore
    USE_LANGGRAPH = True
except ImportError:
    USE_LANGGRAPH = False
    # Fallback to simple class-based approach
    class SimpleGraph:
        def __init__(self):
            self.nodes = {}
            self.edges = []
            self.entry = None
        
        def add_node(self, name, func):
            self.nodes[name] = func
        
        def add_edge(self, from_node, to_node):
            self.edges.append((from_node, to_node))
        
        def set_entry_point(self, node):
            self.entry = node
        
        def compile(self):
            return self
        
        def invoke(self, state):
            current = self.entry
            while current and current != "END":
                if current in self.nodes:
                    state = self.nodes[current](state)
                # Simple linear execution for demo
                next_node = None
                for edge in self.edges:
                    if edge[0] == current:
                        next_node = edge[1]
                        break
                current = next_node
            return state
    
    END = "END"

try:
    import fitz  # pymupdf # type: ignore
except ImportError:
    fitz = None

# Constants
#PROMPTS_DIR = Path("prompts")
#OUTPUT_DIR = Path("out")
#LOG_DIR = OUTPUT_DIR

# Ensure directories exist
#PROMPTS_DIR.mkdir(exist_ok=True)
#OUTPUT_DIR.mkdir(exist_ok=True)


import langsmith # pyright: ignore[reportMissingImports]
from langchain_core.tracers.context import tracing_v2_enabled # pyright: ignore[reportMissingImports]

# Load environment variables from .env file
load_dotenv()

# Initialize Langsmith client with environment variable
langsmith_api_key = os.getenv('LANGSMITH_API_KEY')
langsmith_api_url = os.getenv('LANGSMITH_API_URL', 'https://api.smith.langchain.com')

if langsmith_api_key:
    langsmith_client = langsmith.Client(
        api_key=langsmith_api_key,
        api_url=langsmith_api_url
    )
else:
    langsmith_client = None
    print("Warning: LANGSMITH_API_KEY not found in environment variables. Langsmith tracing will be disabled.")




class TransactionJournalizer:
    """Main AI Agent for transaction journalizing"""
    
    def __init__(self, config, bank_name: str):
        self.bank_name = bank_name
        self.init_timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        file_config = config['file_config'] if 'file_config' in config else {}
        llm_config = config['llm'] if 'llm' in config else {}
        processing_config = config['processing'] if 'processing' in config else {}

        self.llm = self._initialize_llm(llm_config)

        log_format = file_config.get('log_format', "./output/journalize_{time}.log")
        self.logger = self._setup_logger(log_format)
        
        # Load prompts
        system_prompt_file = file_config.get('system_prompt', './system.txt')
        self.prompts_format = file_config.get('prompts_format', "./tr_{name}.txt")
        self.out_csv_format = file_config.get('out_csv_format', "./tr_{name}_{time}.csv")
        self.system_prompt = self._load_system_prompt(system_prompt_file)
        self.bank_prompt_file = Path(self.prompts_format.format(name=self.bank_name))
        self.bank_prompt = None  # Will be loaded lazily when processing file

        # processing parameters
        self.chunk_size = int(processing_config.get('chunk_size', 10))
        
        # Setup langgraph workflow
        self.workflow = self._create_workflow()


    def _initialize_llm(self, llm_config: Dict[str, str] ):
        """Initialize LLM based on configuration"""
        provider = llm_config.get('provider', 'openai')
        
        if provider.lower() == 'openai':
            api_key = llm_config.get('openai_api_key')
            model = llm_config.get('openai_model', 'gpt-4')
            if ChatOpenAI is None:
                raise ImportError("ChatOpenAI could not be imported. Please check your langchain installation.")
            if api_key is None:
                raise ImportError("ChatOpenAI API key is missing.")
            return ChatOpenAI(
                api_key=SecretStr(api_key),
                model=model,
                temperature=0.1
            )
        elif provider.lower() == 'anthropic':
            api_key = llm_config.get('anthropic_api_key')
            model = llm_config.get('anthropic_model', 'claude-3-sonnet-20240229')
            if ChatAnthropic is None:
                raise ImportError("ChatAnthropic could not be imported. Please check your langchain installation.")
            if api_key is None:
                raise ImportError("ChatAnthropic API key is missing.")
            return ChatAnthropic(
                api_key=SecretStr(api_key),
                model_name=model,
                temperature=0.1,
                timeout=30,
                stop=None,
                max_retries=3
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


    def _setup_logger(self, log_format: str) -> logging.Logger:
        """Setup logging configuration"""
        log_file = log_format.format(time=self.init_timestamp)
        
        logger = logging.getLogger(f"journalizer_{self.bank_name}")
        logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger


    def _load_system_prompt(self, system_prompt_file_str: str) -> str:
        """Load system prompt from file"""
        system_prompt_file = Path(system_prompt_file_str)
        if system_prompt_file.exists():
            with open(system_prompt_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        else:
            raise FileNotFoundError(f"System prompt file not found: {system_prompt_file}")
    

    def _load_or_create_bank_prompt_with_context(self, file_path: str, raw_data: str) -> str:
        """Load bank-specific prompt or create new one with transaction file context"""
        
        if self.bank_prompt_file.exists():
            with open(self.bank_prompt_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        else:
            self.logger.info(f"Bank prompt for {self.bank_name} not found. Creating new prompt with context...")
            return self._create_new_bank_prompt_with_context(file_path, raw_data)


    def _create_new_bank_prompt_with_context(self, file_path: str, raw_data: str) -> str:
        """Create new bank-specific prompt using LLM with enhanced context"""
        self.logger.info(f"Generating new bank prompt for {self.bank_name} with transaction file context")
        
        # Collect existing prompt files as reference examples
        existing_prompts = self._collect_existing_prompts()
        
        # Analyze transaction file format
        file_analysis = self._analyze_transaction_file_format(file_path, raw_data)
        
        # Create enhanced prompt creation template
        prompt_creation_template = """
あなたは家計簿の仕訳を行うAIエージェントです。
新しい取引先「{bank_name}」の取引データを処理するための高精度なプロンプトを作成してください。

## 参考情報

### 既存のプロンプトファイル例
以下は既存の他の取引先用プロンプトファイルです。構造や記述方法を参考にしてください：

{existing_prompts_examples}

### 実際の取引データファイル分析
ファイルパス: {file_path}
ファイル形式: {file_format}
文字エンコーディング: {encoding_info}

取引データサンプル:
```
{data_sample}
```

データ構造分析:
{data_structure_analysis}

## 作成要件

以下の情報を含む実用的で具体的なプロンプトを日本語で作成してください：

1. **{bank_name}の取引データ特徴**
   - ファイル形式、エンコーディング、日付形式など
   - 実際のデータ構造に基づいた特徴

2. **データ解析方法**
   - ヘッダー行の処理方法
   - カラム構造の解釈方法
   - 金額や日付の処理方法

3. **カテゴリ分類指針**
   - 取引内容に基づいた適切なカテゴリ分類
   - 特定の取引先や摘要文字列とカテゴリの対応

4. **特別な取引パターン**
   - ATM、振込、引落し等の特別な処理が必要な取引
   - 振替取引の識別方法

5. **account設定**
   - 適切な口座名の設定方法

6. **注意事項**
   - データ処理時の注意点

出力は「## {bank_name}取引データ処理プロンプト」で始まり、上記の構造に従ってマークダウン形式で記述してください。
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt_creation_template.format(
                bank_name=self.bank_name,
                existing_prompts_examples=existing_prompts,
                file_path=file_path,
                file_format=file_analysis["file_format"],
                encoding_info=file_analysis["encoding_info"],
                data_sample=file_analysis["data_sample"],
                data_structure_analysis=file_analysis["structure_analysis"]
            ))
        ]
        

        if langsmith_client:
            with tracing_v2_enabled(client=langsmith_client, project_name="journalize_agent1"):
                response = self.llm.invoke(messages)
        else:
            response = self.llm.invoke(messages)
        new_prompt = response.content
        
        # Save the new prompt
        with open(self.bank_prompt_file, 'w', encoding='utf-8') as f:
            f.write(str(new_prompt))
        
        self.logger.info(f"Enhanced bank prompt created for {self.bank_name}")
        return str(new_prompt)

    def _collect_existing_prompts(self) -> str:
        """Collect existing prompt files as reference examples"""
        existing_prompts = []
        glob_files = Path(self.prompts_format.format(name="*"))

        try:
            for prompt_file in glob_files.parent.glob(glob_files.name):
                if prompt_file.name != Path(self.bank_prompt_file).name:  # Exclude current bank
                    try:
                        with open(prompt_file, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                            existing_prompts.append(f"### {prompt_file.name}\n```\n{content}\n```\n")
                    except Exception as e:
                        self.logger.warning(f"Could not read prompt file {prompt_file}: {e}")
        except Exception as e:
            self.logger.warning(f"Could not collect existing prompts: {e}")
        
        if existing_prompts:
            return "\n".join(existing_prompts)
        else:
            return "（既存のプロンプトファイルが見つかりませんでした）"

    def _analyze_transaction_file_format(self, file_path: str, raw_data: str) -> Dict[str, str]:
        """Analyze transaction file format and structure"""
        file_path_obj = Path(file_path)
        
        # File format analysis
        file_format = file_path_obj.suffix.upper()
        
        # Encoding detection attempt
        encoding_info = "UTF-8"
        try:
            raw_data.encode('utf-8')
            encoding_info = "UTF-8"
        except UnicodeEncodeError:
            encoding_info = "Shift_JIS（推測）"
        
        # Data sample (first few lines)
        lines = raw_data.strip().split('\n')
        data_sample = '\n'.join(lines[:10])  # First 10 lines
        
        # Structure analysis
        structure_analysis = []
        
        if len(lines) > 0:
            # Header analysis
            if file_format == '.CSV':
                first_line = lines[0]
                columns = [col.strip() for col in first_line.split(',')]
                structure_analysis.append(f"カラム数: {len(columns)}")
                structure_analysis.append(f"推定ヘッダー: {', '.join(columns[:5])}")  # First 5 columns
                
                # Data type analysis
                if len(lines) > 1:
                    second_line = lines[1]
                    data_cols = [col.strip() for col in second_line.split(',')]
                    structure_analysis.append(f"データ例: {', '.join(data_cols[:5])}")
            
            structure_analysis.append(f"総行数: {len(lines)}")
            
            # Look for common patterns
            patterns = {
                "日付": ["日付", "取引日", "年月日", "DATE"],
                "金額": ["金額", "支払", "預入", "AMOUNT", "円"],
                "摘要": ["摘要", "内容", "取引内容", "DESC"],
                "残高": ["残高", "BALANCE"]
            }
            
            found_patterns = []
            for pattern_name, keywords in patterns.items():
                for keyword in keywords:
                    if any(keyword in line for line in lines[:5]):
                        found_patterns.append(pattern_name)
                        break
            
            if found_patterns:
                structure_analysis.append(f"検出されたパターン: {', '.join(found_patterns)}")
        
        return {
            "file_format": file_format,
            "encoding_info": encoding_info,
            "data_sample": data_sample,
            "structure_analysis": '; '.join(structure_analysis)
        }

    def _create_new_bank_prompt(self) -> str:
        """Create new bank-specific prompt using LLM (fallback method)"""
        self.logger.info(f"Generating new bank prompt for {self.bank_name}")
        
        prompt_creation_template = """
あなたは家計簿の仕訳を行うAIエージェントです。
新しい取引先「{bank_name}」の取引データを処理するためのプロンプトを作成してください。

以下の情報を含むプロンプトを作成してください：
1. {bank_name}の取引データの一般的な特徴
2. 取引データの解析方法
3. カテゴリ分類の指針
4. 注意すべき特別な取引パターン

プロンプトは日本語で作成し、実用的で具体的な内容にしてください。
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt_creation_template.format(bank_name=self.bank_name))
        ]
        
        if langsmith_client:
            with tracing_v2_enabled(client=langsmith_client, project_name="journalize_agent2"):
                response = self.llm.invoke(messages)
        else:
            response = self.llm.invoke(messages)
        new_prompt = response.content
        
        # Save the new prompt
        with open(self.bank_prompt_file, 'w', encoding='utf-8') as f:
            f.write(str(new_prompt))
        
        self.logger.info(f"New bank prompt created for {self.bank_name}")
        return str(new_prompt)
    
    def _create_workflow(self):
        """Create langgraph workflow for multi-agent processing"""
        
        def parse_transaction_data(state: Dict[str, Any]) -> Dict[str, Any]:
            """Parse raw transaction data"""
            self.logger.info("Parsing transaction data...")
            
            file_path = state["file_path"]
            chunked_data = self._read_transaction_file(file_path)
            
            # Load bank prompt with transaction file context if not already loaded
            raw_data = "".join(chunked_data)
            if self.bank_prompt is None:
                self.bank_prompt = self._load_or_create_bank_prompt_with_context(file_path, raw_data)
            
            #state["raw_data"] = raw_data
            #state["parsed_data"] = self._parse_raw_data(raw_data)
            state["chunked_data"] = chunked_data
            
            return state
        
        def journalize_transactions(state: Dict[str, Any]) -> Dict[str, Any]:
            """Journalize and categorize transactions"""
            self.logger.info("Journalizing transactions...")
            
            #parsed_data = state["parsed_data"]
            journalized_data = []
            
            #for chunk in self._chunk_data(parsed_data):
            for chunk in state["chunked_data"]:
                parse_chunk = self._parse_raw_data(chunk) 
                result = self._journalize_chunk(parse_chunk)
                journalized_data.extend(result)
            
            state["journalized_data"] = journalized_data
            return state
        
        def generate_output(state: Dict[str, Any]) -> Dict[str, Any]:
            """Generate final CSV output"""
            self.logger.info("Generating output CSV...")
            
            journalized_data = state["journalized_data"]
            output_file = self._generate_csv_output(journalized_data, state["timestamp"], state["file_path"])
            
            state["output_file"] = output_file
            return state
        
        # Create graph
        if USE_LANGGRAPH:
            workflow = StateGraph(StateSchema)
        else:
            workflow = SimpleGraph()
        
        # Add nodes
        workflow.add_node("parse", parse_transaction_data) # type: ignore
        workflow.add_node("journalize", journalize_transactions) # type: ignore
        workflow.add_node("output", generate_output) # type: ignore
        
        # Add edges
        workflow.add_edge("parse", "journalize")
        workflow.add_edge("journalize", "output")
        workflow.add_edge("output", END)
        
        # Set entry point
        workflow.set_entry_point("parse")
        
        return workflow.compile()
    
    def _read_transaction_file(self, file_path: str) -> List[str]:
        """Read transaction file (PDF or CSV)"""
        file_path_obj = Path(file_path)
        
        if file_path_obj.suffix.lower() == '.pdf':
            return self._read_pdf_file(file_path_obj)
        elif file_path_obj.suffix.lower() == '.csv':
            return self._read_csv_file(file_path_obj)
        else:
            raise ValueError(f"Unsupported file type: {file_path_obj.suffix}")

    def _read_pdf_file(self, file_path: Path) -> List[str]:
        """Read PDF file and extract text using pymupdf"""
        if fitz is None:
            raise ImportError("pymupdf is required for PDF processing. Please install with: pip install pymupdf")
            
        try:
            # Open PDF document
            pdf_document = fitz.open(str(file_path))
            text_list = []
            
            for page_num in range(pdf_document.page_count):
                #text += f"------------- Page {page_num + 1} -------------\n"
                page = pdf_document[page_num]
                
                # Try to extract tables first (more accurate for bank statements)
                try:
                    tables = page.find_tables() # type: ignore
                    if tables:
                        table_num = 0
                        for table in tables:
                            text = f"---------- Page {page_num + 1} --- Table {table_num + 1} -------------\n"
                            # Extract table data
                            table_data = table.extract()
                            for row in table_data:
                                if row and any(cell for cell in row if cell and cell.strip()):
                                    # Join non-empty cells with comma
                                    #clean_row = [str(cell).strip().replace("\n","") for cell in row if cell and str(cell).strip()]
                                    clean_row = [str(cell).strip().replace("\n","") for cell in row ]
                                    if clean_row:
                                        text += "|".join(clean_row) + "\n"
                            text_list.append(text.strip())
                            table_num += 1
                except Exception as table_error:
                    self.logger.warning(f"Table extraction failed on page {page_num + 1}: {table_error}")
                
                # Extract regular text (fallback or supplement)
                #page_text = page.get_text()
                #if page_text.strip():
                #    text += page_text + "\n"
            pdf_document.close()
            return text_list
            
        except Exception as e:
            self.logger.error(f"Error reading PDF file {file_path}: {e}")
            raise

    def _read_csv_file(self, file_path: Path) -> List[str]:
        """Read CSV file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                string_data = file.read()
                return [e for e in self._chunk_data(string_data.splitlines()) ]
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, 'r', encoding='shift_jis') as file:
                string_data = file.read()
                return [e for e in self._chunk_data(string_data.splitlines()) ]

    def _parse_raw_data(self, raw_data: str) -> List[Dict[str, Any]]:
        """Parse raw data into structured format"""
        # This is a simplified parsing - in practice, you'd need specific parsing logic
        # for each bank's format
        lines = raw_data.strip().split('\n')
        parsed_data = []
        
        for line in lines:
            if line.strip():
                parsed_data.append({"raw_line": line.strip()})
        
        return parsed_data

    def _chunk_data(self, data: List[str], chunk_arg: Optional[int] = None) -> Generator[str, None, None]:
        """Chunk data for processing"""
        chunk_size = self.chunk_size if chunk_arg is None else chunk_arg
        for i in range(0, len(data), chunk_size):
            yield "".join(data[i:i + chunk_size])
    
    def _journalize_chunk(self, chunk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Journalize a chunk of transactions"""
        
        # Prepare data for LLM
        chunk_text = "\n".join([item["raw_line"] for item in chunk])
        
        # Create prompt
        prompt = f"""
{self.system_prompt}

{self.bank_prompt}

以下の取引データを分析し、JSON形式で仕訳してください：

{chunk_text}

出力形式：
{{
  "transactions": [
    {{
      "date": "YYYY-MM-DD HH:MM:SS",
      "account": "口座名",
      "type": "income/expense/transfer",
      "category": "カテゴリ名",
      "transfer": "振替先口座名またはNone",
      "amount": 金額（数値）,
      "item_name": "取引先名",
      "tags": "タグ（カンマ区切り）",
      "desc": "説明",
      "memo": "メモ"
    }}
  ]
}}
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt)
        ]
        
        if langsmith_client:
            with tracing_v2_enabled(client=langsmith_client, project_name="journalize_agent3"):
                response = self.llm.invoke(messages)
        else:
            response = self.llm.invoke(messages)
        
        try:
            # Extract JSON from markdown code blocks if present
            content = str(response.content).strip()
            if content.startswith('```json'):
                # Find the JSON content between ```json and ```
                start = content.find('```json') + 7
                end = content.find('```', start)
                if end != -1:
                    content = content[start:end].strip()
            elif content.startswith('```'):
                # Handle generic code blocks
                start = content.find('```') + 3
                end = content.find('```', start)
                if end != -1:
                    content = content[start:end].strip()
                    
            result = json.loads(content)
            return result.get("transactions", [])
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            self.logger.error(f"Response content: {response.content}")
            return []

    def _generate_csv_output(self, journalized_data: List[Dict[str, Any]], timestamp: str, filename: str) -> str:
        """Generate CSV output file"""
        f_name = Path(filename).stem
        output_file = self.out_csv_format.format(name=self.bank_name, time=timestamp, stem=f_name)
        
        # CSV headers matching the database schema
        headers = [
            "date", "account", "type", "category", "transfer", 
            "amount", "item_name", "tags", "desc", "memo"
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for transaction in journalized_data:
                # Ensure all required fields are present
                row = {header: transaction.get(header, '') for header in headers}
                writer.writerow(row)
        
        self.logger.info(f"CSV output generated: {output_file}")
        return str(output_file)
    
    def process_file(self, file_path: str) -> Tuple[str, str]:
        """Process transaction file and return output paths"""
        self.logger.info(f"Processing file: {file_path}")
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Initial state
        initial_state: StateSchema = {
            "file_path": file_path,
            "bank_name": self.bank_name,
            "timestamp": timestamp,
            "chunked_data": None,
            "journalized_data": None,
            "output_file": None
        }
        
        # Run workflow
        if langsmith_client:
            with tracing_v2_enabled(client=langsmith_client, project_name="journalize_agent_workflow"):
                final_state = self.workflow.invoke(initial_state)
        else:
            final_state = self.workflow.invoke(initial_state)
        
        # Get output paths
        output_csv = final_state["output_file"]
        log_file = next(handler.baseFilename for handler in self.logger.handlers 
                       if isinstance(handler, logging.FileHandler))
        
        if output_csv is None:
            raise RuntimeError("Processing failed, no output CSV generated.")
        self.logger.info(f"Processing completed. Output CSV: {output_csv}")
        return output_csv, log_file
