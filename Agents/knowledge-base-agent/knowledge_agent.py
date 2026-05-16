"""
Personal Knowledge Base Agent
==============================
Supports Claude (API/Bedrock), Ollama (local), and benchmarking across providers.

Architecture: Retrieval-first RAG with hybrid search (vector + BM25)
  User question → hybrid retrieval → inject context → single LLM call → answer

Usage:
  python knowledge_agent.py --provider claude
  python knowledge_agent.py --provider ollama --model gemma4
  python knowledge_agent.py --benchmark --ollama-models qwen3,gemma4
"""

import os
import re
import sys
import json
import math
import time
import hashlib
import argparse
import platform
from pathlib import Path
from datetime import datetime
from collections import Counter

import chromadb
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

console = Console()

# ============================================================================
# COST TRACKING
# ============================================================================

PRICING = {
    "input": 3.00 / 1_000_000,
    "output": 15.00 / 1_000_000,
    "cache_read": 0.30 / 1_000_000,
    "cache_write": 3.75 / 1_000_000,
}


class CostTracker:
    def __init__(self):
        self.session_input = 0
        self.session_output = 0
        self.session_cache_read = 0
        self.session_cache_write = 0
        self.session_cost = 0.0
        self.query_count = 0
        self.last_query_cost = 0.0
        self.last_query_input = 0
        self.last_query_output = 0
        self.last_query_cache_read = 0
        self.last_query_cache_write = 0

    def start_query(self):
        self.last_query_cost = 0.0
        self.last_query_input = 0
        self.last_query_output = 0
        self.last_query_cache_read = 0
        self.last_query_cache_write = 0

    def add_response(self, usage):
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        cache_read = 0
        cache_write = 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", None)
        cache_read_attr = getattr(usage, "cache_read_input_tokens", None)
        if cache_creation:
            cache_write = cache_creation
        if cache_read_attr:
            cache_read = cache_read_attr

        cost = (
            input_tokens * PRICING["input"]
            + output_tokens * PRICING["output"]
            + cache_read * PRICING["cache_read"]
            + cache_write * PRICING["cache_write"]
        )

        self.last_query_input += input_tokens
        self.last_query_output += output_tokens
        self.last_query_cache_read += cache_read
        self.last_query_cache_write += cache_write
        self.last_query_cost += cost

        self.session_input += input_tokens
        self.session_output += output_tokens
        self.session_cache_read += cache_read
        self.session_cache_write += cache_write
        self.session_cost += cost

    def end_query(self):
        self.query_count += 1

    def format_query_cost(self) -> str:
        parts = []
        if self.last_query_input:
            parts.append(f"in:{self.last_query_input:,}")
        if self.last_query_output:
            parts.append(f"out:{self.last_query_output:,}")
        if self.last_query_cache_read:
            parts.append(f"cache_r:{self.last_query_cache_read:,}")
        if self.last_query_cache_write:
            parts.append(f"cache_w:{self.last_query_cache_write:,}")
        tokens_str = " | ".join(parts) if parts else "no token data"
        return f"[dim]Tokens: {tokens_str} — Cost: ${self.last_query_cost:.4f}[/dim]"

    def format_session_summary(self) -> Table:
        table = Table(title="Session Cost Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Queries", str(self.query_count))
        table.add_row("Input tokens", f"{self.session_input:,}")
        table.add_row("Output tokens", f"{self.session_output:,}")
        table.add_row("Cache read tokens", f"{self.session_cache_read:,}")
        table.add_row("Cache write tokens", f"{self.session_cache_write:,}")
        table.add_row("Total session cost", f"${self.session_cost:.4f}")
        if self.query_count > 0:
            table.add_row("Avg cost/query", f"${self.session_cost / self.query_count:.4f}")
        return table


cost_tracker = CostTracker()

# ============================================================================
# VECTOR STORE (Persistent Memory)
# ============================================================================

DB_PATH = os.path.join(os.path.dirname(__file__), "kb_data")
chroma_client = chromadb.PersistentClient(path=DB_PATH)
collection = chroma_client.get_or_create_collection(
    name="knowledge_base",
    metadata={"hnsw:space": "cosine"},
)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap
    return chunks


def generate_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


# ============================================================================
# HYBRID RETRIEVAL: Vector (ChromaDB) + BM25 keyword search
# ============================================================================

MAX_RESULT_CHARS = 2000
MAX_CONTEXT_CHARS = 8000


def tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_freqs = {}
        self.doc_lengths = []
        self.avg_dl = 0
        self.doc_tokens = []
        self.n_docs = 0

    def build(self, documents: list[str]):
        self.n_docs = len(documents)
        self.doc_tokens = [tokenize(doc) for doc in documents]
        self.doc_lengths = [len(t) for t in self.doc_tokens]
        self.avg_dl = sum(self.doc_lengths) / self.n_docs if self.n_docs else 1

        self.doc_freqs = {}
        for tokens in self.doc_tokens:
            seen = set(tokens)
            for token in seen:
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

    def score(self, query: str, top_n: int = 5) -> list[tuple[int, float]]:
        query_tokens = tokenize(query)
        scores = []
        for i, doc_tokens in enumerate(self.doc_tokens):
            tf_map = Counter(doc_tokens)
            score = 0.0
            dl = self.doc_lengths[i]
            for qt in query_tokens:
                if qt not in self.doc_freqs:
                    continue
                df = self.doc_freqs[qt]
                idf = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1)
                tf = tf_map.get(qt, 0)
                tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl))
                score += idf * tf_norm
            scores.append((i, score))
        scores.sort(key=lambda x: -x[1])
        return scores[:top_n]


bm25_index = BM25Index()
_bm25_docs = []
_bm25_ids = []
_bm25_metas = []


def rebuild_bm25_index():
    global _bm25_docs, _bm25_ids, _bm25_metas
    total = collection.count()
    if total == 0:
        _bm25_docs, _bm25_ids, _bm25_metas = [], [], []
        return
    all_data = collection.get(include=["documents", "metadatas"])
    _bm25_docs = all_data["documents"]
    _bm25_ids = all_data["ids"]
    _bm25_metas = all_data["metadatas"]
    bm25_index.build(_bm25_docs)


def retrieve_context(query: str, n_results: int = 5, vector_weight: float = 0.5) -> str:
    total = collection.count()
    if total == 0:
        return ""

    n = min(n_results * 2, total)
    vector_results = collection.query(query_texts=[query], n_results=n)

    vector_scores = {}
    for i in range(len(vector_results["ids"][0])):
        doc_id = vector_results["ids"][0][i]
        distance = vector_results["distances"][0][i]
        vector_scores[doc_id] = 1.0 / (1.0 + distance)

    if not _bm25_docs:
        rebuild_bm25_index()

    bm25_scores = {}
    if _bm25_docs:
        bm25_results = bm25_index.score(query, top_n=n)
        max_bm25 = bm25_results[0][1] if bm25_results and bm25_results[0][1] > 0 else 1.0
        for idx, score in bm25_results:
            if score > 0:
                bm25_scores[_bm25_ids[idx]] = score / max_bm25

    all_ids = set(vector_scores.keys()) | set(bm25_scores.keys())
    combined = []
    for doc_id in all_ids:
        vs = vector_scores.get(doc_id, 0)
        bs = bm25_scores.get(doc_id, 0)
        final = vector_weight * vs + (1 - vector_weight) * bs
        combined.append((doc_id, final))

    combined.sort(key=lambda x: -x[1])

    id_to_doc = {}
    id_to_meta = {}
    for i in range(len(vector_results["ids"][0])):
        did = vector_results["ids"][0][i]
        id_to_doc[did] = vector_results["documents"][0][i]
        id_to_meta[did] = vector_results["metadatas"][0][i]
    if _bm25_docs:
        for i, did in enumerate(_bm25_ids):
            if did not in id_to_doc:
                id_to_doc[did] = _bm25_docs[i]
                id_to_meta[did] = _bm25_metas[i]

    context_parts = []
    total_chars = 0
    for doc_id, score in combined[:n_results]:
        content = id_to_doc.get(doc_id, "")
        meta = id_to_meta.get(doc_id, {})
        title = meta.get("title", "Unknown")

        if len(content) > MAX_RESULT_CHARS:
            content = content[:MAX_RESULT_CHARS] + "..."

        if total_chars + len(content) > MAX_CONTEXT_CHARS:
            break

        context_parts.append(f"[Source: {title} | score: {score:.3f}]\n{content}")
        total_chars += len(content)

    return "\n\n---\n\n".join(context_parts)


# ============================================================================
# TOOL DEFINITIONS — only for write operations (add/delete/ingest/list)
# ============================================================================

CLAUDE_TOOLS = [
    {
        "name": "add_document",
        "description": (
            "Add a document to the knowledge base. Use this when the user wants "
            "to save, store, or remember information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "A short title for the document"},
                "content": {"type": "string", "description": "The full text content to store"},
                "tags": {"type": "string", "description": "Comma-separated tags (e.g., 'python,tutorial')"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "list_documents",
        "description": "List all documents in the knowledge base with titles and tags.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_document",
        "description": "Delete a document from the knowledge base by title.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The title of the document to delete"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "ingest_file",
        "description": "Read a file from disk and add it to the knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to ingest"},
                "tags": {"type": "string", "description": "Comma-separated tags"},
            },
            "required": ["file_path"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in CLAUDE_TOOLS
]


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================


def tool_add_document(title: str, content: str, tags: str = "") -> str:
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    chunks = chunk_text(content)
    ids, documents, metadatas = [], [], []

    for i, chunk in enumerate(chunks):
        ids.append(generate_id(f"{title}_{i}"))
        documents.append(chunk)
        metadatas.append({
            "title": title,
            "tags": json.dumps(tag_list),
            "chunk_index": i,
            "total_chunks": len(chunks),
            "added_date": datetime.now().isoformat(),
        })

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    rebuild_bm25_index()
    return json.dumps({"status": "success", "title": title, "chunks_stored": len(chunks), "tags": tag_list})


def tool_list_documents() -> str:
    total = collection.count()
    if total == 0:
        return json.dumps({"documents": [], "message": "Knowledge base is empty."})

    all_data = collection.get(include=["metadatas"])
    docs = {}
    for meta in all_data["metadatas"]:
        title = meta.get("title", "Unknown")
        if title not in docs:
            docs[title] = {
                "title": title,
                "tags": json.loads(meta.get("tags", "[]")),
                "chunks": meta.get("total_chunks", 1),
                "added": meta.get("added_date", "Unknown"),
            }
    return json.dumps({"documents": list(docs.values()), "total_chunks": total})


def tool_delete_document(title: str) -> str:
    all_data = collection.get(include=["metadatas"])
    ids_to_delete = [all_data["ids"][i] for i, m in enumerate(all_data["metadatas"]) if m.get("title") == title]

    if not ids_to_delete:
        return json.dumps({"status": "not_found", "message": f"No document titled '{title}' found."})

    collection.delete(ids=ids_to_delete)
    rebuild_bm25_index()
    return json.dumps({"status": "deleted", "title": title, "chunks_removed": len(ids_to_delete)})


def _extract_pdf_text(path: Path) -> str:
    try:
        import PyPDF2
        text_parts = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    return ""


def tool_ingest_file(file_path: str, tags: str = "") -> str:
    path = Path(file_path).expanduser()
    if not path.exists():
        return json.dumps({"status": "error", "message": f"File not found: {file_path}"})

    if path.suffix.lower() == ".pdf":
        content = _extract_pdf_text(path)
        if not content.strip():
            return json.dumps({
                "status": "error",
                "message": "Could not extract text from PDF. Install PyPDF2 or pdfplumber: pip install PyPDF2 pdfplumber",
            })
    else:
        content = path.read_text(encoding="utf-8", errors="replace")

    title = path.stem.replace("_", " ").replace("-", " ").title()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else [path.suffix.lstrip(".")]
    return tool_add_document(title=title, content=content, tags=",".join(tag_list))


TOOL_DISPATCH = {
    "add_document": tool_add_document,
    "list_documents": tool_list_documents,
    "delete_document": tool_delete_document,
    "ingest_file": tool_ingest_file,
}


def execute_tool(name: str, arguments: dict) -> str:
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn(**arguments)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are a Personal Knowledge Base Agent.

When CONTEXT is provided with the user's question, you MUST:
1. Base your answer ONLY on the provided context.
2. Quote relevant parts and cite the [Source: title] for each fact.
3. If context is empty or irrelevant, say "No relevant information found in the knowledge base."
4. Use markdown formatting. Be detailed but concise.

When the user wants to store information, use add_document.
When the user provides a file path, use ingest_file.
When the user asks to list or delete documents, use the appropriate tool.
NEVER give generic greetings. Always answer the question directly."""

# ============================================================================
# LLM PROVIDERS
# ============================================================================

BEDROCK_APP_PROFILE_ARN = "arn:aws:bedrock:eu-west-1:905121132271:application-inference-profile/g0nbe6qp4i3t"

BEDROCK_MODEL_MAP = {
    "claude-sonnet-4-6": BEDROCK_APP_PROFILE_ARN,
    "claude-haiku-4-5": BEDROCK_APP_PROFILE_ARN,
    "claude-opus-4-7": BEDROCK_APP_PROFILE_ARN,
    "claude-sonnet-4-5": BEDROCK_APP_PROFILE_ARN,
    "claude-3-5-sonnet": BEDROCK_APP_PROFILE_ARN,
    "claude-3-haiku": BEDROCK_APP_PROFILE_ARN,
}


class ClaudeProvider:
    def __init__(self, model="claude-sonnet-4-6", use_bedrock=True, aws_profile=None, aws_region=None):
        import anthropic
        self.model = model
        self._is_bedrock = False

        if use_bedrock or os.environ.get("CLAUDE_USE_BEDROCK", "").lower() in ("1", "true"):
            import boto3

            profile = aws_profile or os.environ.get("AWS_PROFILE", "claude-code-sso-profile")
            region = aws_region or os.environ.get("AWS_REGION", "eu-west-1")

            session = boto3.Session(profile_name=profile, region_name=region)
            credentials = session.get_credentials().get_frozen_credentials()

            self.client = anthropic.AnthropicBedrock(
                aws_access_key=credentials.access_key,
                aws_secret_key=credentials.secret_key,
                aws_session_token=credentials.token,
                aws_region=region,
            )
            self._is_bedrock = True
            self._provider_type = f"Bedrock/{region}/{profile}"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            self.client = anthropic.Anthropic()
            self._provider_type = "API"
        else:
            raise ValueError(
                "No auth found. Set ANTHROPIC_API_KEY for direct API, "
                "or use --bedrock with AWS SSO profile."
            )

    def _get_model_id(self):
        if self._is_bedrock:
            if self.model.startswith("arn:"):
                return self.model
            return BEDROCK_MODEL_MAP.get(self.model, self.model)
        return self.model

    def chat(self, messages: list, max_iterations: int = 5) -> str:
        model_id = self._get_model_id()

        for _ in range(max_iterations):
            kwargs = {
                "model": model_id,
                "max_tokens": 2048,
                "tools": CLAUDE_TOOLS,
                "messages": messages,
                "system": [
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }

            response = self.client.messages.create(**kwargs)
            cost_tracker.add_response(response.usage)

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                return "\n".join(b.text for b in response.content if hasattr(b, "text"))

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    console.print(f"  [dim]Using tool: {block.name}({json.dumps(block.input)[:80]}...)[/dim]")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})

        return "Agent reached maximum iterations."

    @property
    def display_name(self):
        return f"Claude ({self.model}) via {self._provider_type}"


class OllamaProvider:
    def __init__(self, model="qwen3"):
        import ollama as _ollama
        self.ollama = _ollama
        self.model = model

    def chat(self, messages: list, max_iterations: int = 5) -> str:
        ollama_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in messages:
            if msg["role"] == "user":
                if isinstance(msg["content"], str):
                    ollama_messages.append(msg)
                elif isinstance(msg["content"], list):
                    for item in msg["content"]:
                        if item.get("type") == "tool_result":
                            ollama_messages.append({"role": "tool", "content": item["content"]})
            elif msg["role"] == "assistant":
                if isinstance(msg["content"], str):
                    ollama_messages.append(msg)

        for _ in range(max_iterations):
            response = self.ollama.chat(
                model=self.model,
                messages=ollama_messages,
                tools=OLLAMA_TOOLS,
            )

            msg = response["message"]
            ollama_messages.append(msg)

            if not msg.get("tool_calls"):
                answer = msg.get("content", "")
                messages.append({"role": "assistant", "content": answer})
                return answer

            for tool_call in msg["tool_calls"]:
                fn_name = tool_call["function"]["name"]
                fn_args = tool_call["function"]["arguments"]
                console.print(f"  [dim]Using tool: {fn_name}({json.dumps(fn_args)[:80]}...)[/dim]")
                result = execute_tool(fn_name, fn_args)
                ollama_messages.append({"role": "tool", "content": result})

        messages.append({"role": "assistant", "content": "Agent reached maximum iterations."})
        return "Agent reached maximum iterations."

    @property
    def display_name(self):
        return f"Ollama ({self.model})"


# ============================================================================
# HARDWARE METRICS
# ============================================================================

def collect_hw_metrics() -> dict:
    import psutil

    hw = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_freq_mhz": None,
        "ram_total_gb": round(psutil.virtual_memory().total / (1024 ** 3), 1),
        "ram_available_gb": round(psutil.virtual_memory().available / (1024 ** 3), 1),
        "gpu": None,
    }

    freq = psutil.cpu_freq()
    if freq:
        hw["cpu_freq_mhz"] = round(freq.current)

    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(", ")
            hw["gpu"] = {
                "name": parts[0],
                "vram_total_mb": int(parts[1]),
                "vram_free_mb": int(parts[2]),
            }
    except Exception:
        pass

    return hw


def format_hw_table(hw: dict) -> Table:
    table = Table(title="Hardware Configuration")
    table.add_column("Component", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Platform", hw.get("platform", "Unknown"))
    table.add_row("Processor", hw.get("processor", "Unknown"))
    table.add_row("CPU Cores", f"{hw.get('cpu_count_physical', '?')} physical / {hw.get('cpu_count_logical', '?')} logical")
    if hw.get("cpu_freq_mhz"):
        table.add_row("CPU Frequency", f"{hw['cpu_freq_mhz']} MHz")
    table.add_row("RAM", f"{hw.get('ram_total_gb', '?')} GB total / {hw.get('ram_available_gb', '?')} GB available")
    gpu = hw.get("gpu")
    if gpu:
        table.add_row("GPU", f"{gpu['name']} ({gpu['vram_total_mb']} MB, {gpu['vram_free_mb']} MB free)")
    else:
        table.add_row("GPU", "Not detected / CPU inference")
    return table


def predict_performance(hw: dict, benchmark_results: dict) -> list[Table]:
    tables = []

    gpu = hw.get("gpu")
    ram_gb = hw.get("ram_total_gb", 0)
    cpu_cores = hw.get("cpu_count_physical", 0)
    has_gpu = gpu is not None
    vram_mb = gpu.get("vram_total_mb", 0) if gpu else 0

    current_desc = f"CPU: {cpu_cores} cores, RAM: {ram_gb}GB"
    if has_gpu:
        current_desc += f", GPU: {gpu['name']} ({vram_mb}MB VRAM)"
    else:
        current_desc += ", GPU: None (CPU-only inference)"

    # Speedup factors relative to CPU-only baseline
    # Based on published Ollama benchmarks across hardware configs
    hw_tiers = [
        {
            "name": "Entry GPU Laptop",
            "spec": "RTX 3060 Laptop (6GB) / 16GB RAM / 6-core",
            "factor": 0.15,
            "cost_approx": "$800-1000",
        },
        {
            "name": "Mid-range GPU Desktop",
            "spec": "RTX 4060 Ti (16GB) / 32GB RAM / 8-core",
            "factor": 0.08,
            "cost_approx": "$1200-1500",
        },
        {
            "name": "High-end GPU Desktop",
            "spec": "RTX 4090 (24GB) / 64GB RAM / 12-core",
            "factor": 0.04,
            "cost_approx": "$2500-3500",
        },
        {
            "name": "Apple M4 Max MacBook",
            "spec": "M4 Max (48GB unified) / 48GB RAM / 16-core",
            "factor": 0.05,
            "cost_approx": "$3500-4000",
        },
        {
            "name": "Dual GPU Workstation",
            "spec": "2x RTX 4090 (48GB total) / 128GB RAM / 16-core",
            "factor": 0.025,
            "cost_approx": "$6000-8000",
        },
    ]

    # If already has a GPU, adjust the baseline
    if has_gpu:
        if vram_mb >= 20000:
            base_factor = 0.06
        elif vram_mb >= 12000:
            base_factor = 0.10
        elif vram_mb >= 6000:
            base_factor = 0.18
        else:
            base_factor = 0.25
    else:
        base_factor = 1.0

    ollama_models = {}
    for name, results in benchmark_results.items():
        if "Ollama" not in name:
            continue
        avg_latency = sum(r["latency_sec"] for r in results) / len(results) if results else 0
        if avg_latency > 0:
            ollama_models[name] = avg_latency

    claude_providers = {}
    for name, results in benchmark_results.items():
        if "Claude" not in name:
            continue
        avg_lat = sum(r["latency_sec"] for r in results) / len(results) if results else 0
        total_cost = sum(r["cost_usd"] for r in results) if results else 0
        claude_providers[name] = {"latency": avg_lat, "cost": total_cost}

    if ollama_models:
        tier_table = Table(title=f"Hardware Upgrade Projections\n[dim]Current: {current_desc}[/dim]")
        tier_table.add_column("Hardware Tier", style="cyan", min_width=25)
        tier_table.add_column("Spec", style="dim")
        tier_table.add_column("Est. Cost", style="yellow", justify="right")

        for model_name in ollama_models:
            tier_table.add_column(model_name, style="green", justify="right")

        for cname in claude_providers:
            tier_table.add_column(cname, style="blue", justify="right")

        current_vals = [f"{lat:.1f}s" for lat in ollama_models.values()]
        for ci in claude_providers.values():
            current_vals.append(f"{ci['latency']:.1f}s")
        tier_table.add_row(
            "[bold]Current System[/bold]",
            current_desc[:50],
            "-",
            *current_vals,
        )

        for tier in hw_tiers:
            ratio = tier["factor"] / base_factor
            projected = []
            for lat in ollama_models.values():
                est = lat * ratio
                speedup = lat / est if est > 0 else 0
                projected.append(f"{est:.1f}s ({speedup:.0f}x)")

            for ci in claude_providers.values():
                projected.append(f"{ci['latency']:.1f}s (1x)")

            tier_table.add_row(
                tier["name"],
                tier["spec"],
                tier["cost_approx"],
                *projected,
            )

        tables.append(tier_table)

    # Break-even analysis across usage scales
    if ollama_models and claude_providers:
        n_questions = len(next(iter(benchmark_results.values())))
        usage_scales = [
            ("Individual", 1, 50),
            ("Small Team (5)", 5, 50),
            ("Department (20)", 20, 100),
            ("Production API", 1, 1000),
        ]

        for cname, cinfo in claude_providers.items():
            if cinfo["cost"] <= 0:
                continue
            avg_cost_per_q = cinfo["cost"] / n_questions

            be_table = Table(title=f"Break-even: Local HW vs {cname} (${avg_cost_per_q:.4f}/query)")
            be_table.add_column("Hardware Tier", style="cyan")
            be_table.add_column("HW Cost", style="yellow", justify="right")
            be_table.add_column("Est. Latency", style="green", justify="right")

            for label, users, qpd in usage_scales:
                be_table.add_column(label, justify="right")

            for tier in hw_tiers:
                hw_cost_low = int(tier["cost_approx"].split("-")[0].replace("$", "").replace(",", ""))
                ratio = tier["factor"] / base_factor
                representative_lat = list(ollama_models.values())[0] * ratio

                scale_vals = []
                for label, users, qpd in usage_scales:
                    daily_queries = users * qpd
                    daily_cloud_cost = daily_queries * avg_cost_per_q
                    days = hw_cost_low / daily_cloud_cost if daily_cloud_cost > 0 else 0

                    if days < 30:
                        scale_vals.append(f"[green]{days:.0f} days[/green]")
                    elif days < 365:
                        months = days / 30
                        color = "green" if months < 6 else "yellow"
                        scale_vals.append(f"[{color}]{months:.0f} months[/{color}]")
                    else:
                        years = days / 365
                        color = "yellow" if years < 3 else "red"
                        scale_vals.append(f"[{color}]{years:.1f} years[/{color}]")

                be_table.add_row(
                    tier["name"],
                    tier["cost_approx"],
                    f"{representative_lat:.1f}s",
                    *scale_vals,
                )

            tables.append(be_table)

    # Local vs Cloud tradeoff summary
    tradeoff = Table(title="Local vs Cloud — Full Tradeoff Analysis")
    tradeoff.add_column("Factor", style="cyan", min_width=20)
    tradeoff.add_column("Local (Ollama)", style="green")
    tradeoff.add_column("Cloud (Claude API)", style="blue")

    tradeoff.add_row(
        "Cost per query",
        "$0.00 (free after HW)",
        f"${list(claude_providers.values())[0]['cost'] / len(next(iter(benchmark_results.values()))):.4f}/query" if claude_providers else "varies",
    )

    if ollama_models:
        best_local = min(ollama_models.values())
        best_cloud = min(ci["latency"] for ci in claude_providers.values()) if claude_providers else 0
        tradeoff.add_row("Latency (this HW)", f"{best_local:.1f}s (CPU-only)", f"{best_cloud:.1f}s")
        tradeoff.add_row("Latency (with GPU)", f"~{best_local * 0.04:.1f}s (RTX 4090 est.)", f"{best_cloud:.1f}s (unchanged)")

    tradeoff.add_row("Data privacy", "All data stays on-premise", "Data sent to cloud provider")
    tradeoff.add_row("Internet required", "No — fully offline capable", "Yes — always")
    tradeoff.add_row("Rate limits", "None — limited only by HW", "API rate limits apply")
    tradeoff.add_row("Model customization", "Fine-tune, GGUF quants, LoRA", "No customization")
    tradeoff.add_row("Concurrent users", "Limited by HW (GPU VRAM)", "Scales with API plan")
    tradeoff.add_row("Model updates", "Manual pull new versions", "Automatic, always latest")
    tradeoff.add_row("Quality (general)", "Good (7B-14B models)", "Excellent (frontier models)")
    tradeoff.add_row("Quality (domain-specific)", "Can match cloud with fine-tuning", "Generic, no domain tuning")
    tradeoff.add_row("Upfront cost", "HW purchase required", "None — pay as you go")

    if claude_providers:
        n_q = len(next(iter(benchmark_results.values())))
        monthly_costs = []
        for cname, cinfo in claude_providers.items():
            cpq = cinfo["cost"] / n_q if n_q > 0 else 0
            monthly_50 = cpq * 50 * 30
            monthly_costs.append(f"{cname}: ${monthly_50:.2f}")
        tradeoff.add_row(
            "Monthly cost (50 q/day)",
            "$0 + electricity",
            " | ".join(monthly_costs),
        )
        monthly_team = []
        for cname, cinfo in claude_providers.items():
            cpq = cinfo["cost"] / n_q if n_q > 0 else 0
            monthly_5x100 = cpq * 500 * 30
            monthly_team.append(f"{cname}: ${monthly_5x100:.2f}")
        tradeoff.add_row(
            "Monthly cost (5 users × 100 q/day)",
            "$0 + electricity",
            " | ".join(monthly_team),
        )

    tables.append(tradeoff)

    # Recommendation
    rec_table = Table(title="Recommendation by Use Case")
    rec_table.add_column("Use Case", style="cyan")
    rec_table.add_column("Recommended", style="green")
    rec_table.add_column("Reason", style="dim")

    rec_table.add_row("Personal learning/hobby", "Cloud (Haiku)", "Low volume, no HW investment needed")
    rec_table.add_row("Solo professional", "Cloud or Local + GPU", "Depends on query volume and privacy needs")
    rec_table.add_row("Sensitive/proprietary docs", "Local + GPU", "Data never leaves your machine")
    rec_table.add_row("Team (5+ users)", "Local + GPU", "Break-even in months, unlimited queries")
    rec_table.add_row("Offline/air-gapped", "Local", "Only option — no internet dependency")
    rec_table.add_row("Highest quality answers", "Cloud (Sonnet)", "Frontier model quality unmatched by local 7B-14B")
    rec_table.add_row("Production API backend", "Local + GPU or Cloud", "Local saves cost at scale, Cloud for burst")

    tables.append(rec_table)

    return tables


# ============================================================================
# BENCHMARK ENGINE
# ============================================================================

BENCHMARK_QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "benchmark_questions.json")


def load_benchmark_questions() -> list[dict]:
    if os.path.exists(BENCHMARK_QUESTIONS_FILE):
        with open(BENCHMARK_QUESTIONS_FILE, "r") as f:
            return json.load(f)
    return []


def prompt_benchmark_questions() -> list[dict]:
    questions = load_benchmark_questions()
    if questions:
        console.print(f"[dim]Loaded {len(questions)} questions from {BENCHMARK_QUESTIONS_FILE}[/dim]")
        return questions

    console.print(f"[yellow]No benchmark questions found.[/yellow]")
    console.print(f"[yellow]Add questions interactively, or create {BENCHMARK_QUESTIONS_FILE}[/yellow]")
    console.print(f'[dim]File format: [{{"question": "...", "expected_keywords": ["kw1", "kw2"]}}][/dim]\n')

    questions = []
    while True:
        q = console.input("[cyan]Question (empty to finish):[/cyan] ").strip()
        if not q:
            break
        kw = console.input("[cyan]Expected keywords in answer (comma-separated, or empty):[/cyan] ").strip()
        keywords = [k.strip() for k in kw.split(",") if k.strip()] if kw else []
        questions.append({"question": q, "expected_keywords": keywords})
        console.print(f"  [green]Added ({len(questions)} total)[/green]")

    if questions:
        with open(BENCHMARK_QUESTIONS_FILE, "w") as f:
            json.dump(questions, f, indent=2)
        console.print(f"[green]Saved {len(questions)} questions to {BENCHMARK_QUESTIONS_FILE}[/green]")

    return questions


def score_answer(answer: str, expected_keywords: list[str]) -> dict:
    if not expected_keywords:
        return {"keyword_hits": 0, "keyword_total": 0, "keyword_score": 1.0}

    lower_answer = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in lower_answer)
    return {
        "keyword_hits": hits,
        "keyword_total": len(expected_keywords),
        "keyword_score": hits / len(expected_keywords) if expected_keywords else 1.0,
    }


def run_single_provider_benchmark(provider, questions: list[dict]) -> list[dict]:
    results = []
    for qi, q in enumerate(questions):
        question = q["question"]
        expected = q.get("expected_keywords", [])

        console.print(f"  [dim]Q{qi+1}: {question}[/dim]")

        context = retrieve_context(question)
        if context:
            augmented = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
        else:
            augmented = question

        messages = [{"role": "user", "content": augmented}]

        tracker = CostTracker()
        original_tracker = globals()["cost_tracker"]
        globals()["cost_tracker"] = tracker
        tracker.start_query()

        start = time.time()
        try:
            answer = provider.chat(messages)
            error = None
        except Exception as e:
            answer = ""
            error = str(e)
        elapsed = time.time() - start

        tracker.end_query()
        globals()["cost_tracker"] = original_tracker

        quality = score_answer(answer, expected)

        results.append({
            "question": question,
            "answer": answer,
            "error": error,
            "latency_sec": round(elapsed, 2),
            "input_tokens": tracker.last_query_input,
            "output_tokens": tracker.last_query_output,
            "cache_read_tokens": tracker.last_query_cache_read,
            "cache_write_tokens": tracker.last_query_cache_write,
            "cost_usd": round(tracker.last_query_cost, 6),
            "answer_length": len(answer),
            "keyword_score": quality["keyword_score"],
            "keyword_hits": quality["keyword_hits"],
            "keyword_total": quality["keyword_total"],
        })

    return results


def run_benchmark(providers: dict, questions: list[dict] = None):
    if questions is None:
        questions = prompt_benchmark_questions()

    if not questions:
        console.print("[red]No questions to benchmark. Aborting.[/red]")
        return

    # Collect hardware info
    hw = {}
    try:
        hw = collect_hw_metrics()
        console.print(format_hw_table(hw))
        console.print()
    except ImportError:
        console.print("[yellow]Install psutil for hardware metrics: pip install psutil[/yellow]\n")
    except Exception as e:
        console.print(f"[yellow]Could not collect HW metrics: {e}[/yellow]\n")

    console.print(Panel.fit(
        f"[bold cyan]Benchmark Mode[/bold cyan]\n"
        f"[dim]Questions: {len(questions)} | Providers: {', '.join(providers.keys())}[/dim]",
        border_style="yellow",
    ))

    all_results = {}

    for name, provider in providers.items():
        console.print(f"\n[bold yellow]Running {name}...[/bold yellow]")
        results = run_single_provider_benchmark(provider, questions)
        all_results[name] = results
        console.print(f"  [green]Done — {len(results)} questions answered[/green]")

    # Per-question comparison
    console.print("\n")
    for qi, q in enumerate(questions):
        console.print(f"[bold]Q{qi+1}: {q['question']}[/bold]")
        if q.get("expected_keywords"):
            console.print(f"[dim]Expected keywords: {', '.join(q['expected_keywords'])}[/dim]")

        table = Table(show_header=True)
        table.add_column("Provider", style="cyan", min_width=20)
        table.add_column("Latency", style="yellow", justify="right")
        table.add_column("Tokens (in/out)", justify="right")
        table.add_column("Cost", style="green", justify="right")
        table.add_column("Answer Len", justify="right")
        table.add_column("Keyword Score", justify="right")

        for name in providers:
            r = all_results[name][qi]
            if r["error"]:
                table.add_row(name, "-", "-", "-", "-", f"[red]ERROR: {r['error'][:40]}[/red]")
            else:
                table.add_row(
                    name,
                    f"{r['latency_sec']}s",
                    f"{r['input_tokens']:,}/{r['output_tokens']:,}",
                    f"${r['cost_usd']:.4f}",
                    str(r["answer_length"]),
                    f"{r['keyword_score']:.0%}" if r["keyword_total"] > 0 else "n/a",
                )

        console.print(table)

        for name in providers:
            r = all_results[name][qi]
            if r["answer"] and not r["error"]:
                preview = r["answer"][:300].replace("\n", " ")
                if len(r["answer"]) > 300:
                    preview += "..."
                console.print(f"  [dim]{name}:[/dim] {preview}")
        console.print()

    # Summary table
    console.print("[bold]═══ OVERALL SUMMARY ═══[/bold]\n")
    summary = Table(title="Provider Comparison Summary")
    summary.add_column("Metric", style="cyan")
    for name in providers:
        summary.add_column(name, style="green")

    provider_names = list(providers.keys())
    metrics = {name: {
        "total_cost": sum(r["cost_usd"] for r in all_results[name]),
        "avg_latency": sum(r["latency_sec"] for r in all_results[name]) / len(all_results[name]),
        "avg_answer_len": sum(r["answer_length"] for r in all_results[name]) / len(all_results[name]),
        "total_input": sum(r["input_tokens"] for r in all_results[name]),
        "total_output": sum(r["output_tokens"] for r in all_results[name]),
        "errors": sum(1 for r in all_results[name] if r["error"]),
        "keyword_scores": [r["keyword_score"] for r in all_results[name] if r["keyword_total"] > 0],
    } for name in provider_names}

    for name in provider_names:
        kw = metrics[name]["keyword_scores"]
        metrics[name]["avg_keyword_score"] = sum(kw) / len(kw) if kw else 0

    summary.add_row("Total cost", *[f"${metrics[n]['total_cost']:.4f}" for n in provider_names])
    summary.add_row("Avg latency", *[f"{metrics[n]['avg_latency']:.1f}s" for n in provider_names])
    summary.add_row("Avg answer length", *[f"{metrics[n]['avg_answer_len']:.0f} chars" for n in provider_names])
    summary.add_row("Total input tokens", *[f"{metrics[n]['total_input']:,}" for n in provider_names])
    summary.add_row("Total output tokens", *[f"{metrics[n]['total_output']:,}" for n in provider_names])
    summary.add_row("Avg keyword accuracy", *[f"{metrics[n]['avg_keyword_score']:.0%}" for n in provider_names])
    summary.add_row("Errors", *[str(metrics[n]["errors"]) for n in provider_names])

    for name in provider_names:
        ks = metrics[name]["avg_keyword_score"]
        if ks > 0:
            metrics[name]["cost_per_quality"] = metrics[name]["total_cost"] / ks
        else:
            metrics[name]["cost_per_quality"] = 0

    summary.add_row("Cost per quality point", *[
        f"${metrics[n]['cost_per_quality']:.4f}" if metrics[n]["cost_per_quality"] > 0 else "n/a"
        for n in provider_names
    ])

    console.print(summary)

    # HW performance projections
    if hw:
        proj_tables = predict_performance(hw, all_results)
        for t in proj_tables:
            console.print()
            console.print(t)

    # Save report
    report_path = os.path.join(os.path.dirname(__file__), "benchmark_report.json")
    report = {
        "timestamp": datetime.now().isoformat(),
        "hardware": hw,
        "questions": len(questions),
        "providers": {name: {
            "display_name": providers[name].display_name,
            "metrics": {k: v for k, v in metrics[name].items() if k != "keyword_scores"},
            "results": all_results[name],
        } for name in provider_names},
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    console.print(f"\n[dim]Full report saved to {report_path}[/dim]")


# ============================================================================
# INTERACTIVE CLI
# ============================================================================

MAX_HISTORY_TURNS = 10


def build_query_message(user_input: str) -> str:
    context = retrieve_context(user_input)
    if context:
        console.print(f"  [dim]Retrieved {context.count('[Source:')} chunks via hybrid search[/dim]")
        return f"CONTEXT:\n{context}\n\nQUESTION: {user_input}"
    return user_input


def trim_conversation(history: list):
    while len(history) > MAX_HISTORY_TURNS * 2:
        history.pop(0)
        history.pop(0)


def print_welcome(provider):
    console.print(Panel.fit(
        f"[bold cyan]Personal Knowledge Base Agent[/bold cyan]\n"
        f"[dim]Provider: {provider.display_name}[/dim]\n\n"
        "Store, search, and query your personal knowledge.\n\n"
        "[dim]Commands:[/dim]\n"
        "  [green]Just type[/green]       — Ask questions (auto-retrieves from KB)\n"
        "  [green]/add[/green]            — Add a note interactively\n"
        "  [green]/ingest path[/green]    — Ingest a file\n"
        "  [green]/list[/green]           — List all stored documents\n"
        "  [green]/stats[/green]          — Show knowledge base stats\n"
        "  [green]/clear[/green]          — Clear conversation (keeps knowledge)\n"
        "  [green]/cost[/green]           — Show session cost breakdown\n"
        "  [green]/benchmark[/green]      — Run provider comparison benchmark\n"
        "  [green]/provider name[/green]  — Switch provider:\n"
        "                        claude, claude-haiku, claude-opus\n"
        "                        ollama:qwen3, ollama:gemma4\n"
        "  [green]/quit[/green]           — Exit",
        border_style="cyan",
    ))


def show_stats(provider):
    total = collection.count()
    all_data = collection.get(include=["metadatas"])
    titles = set()
    tags = set()
    for meta in all_data.get("metadatas", []):
        titles.add(meta.get("title", "Unknown"))
        for tag in json.loads(meta.get("tags", "[]")):
            tags.add(tag)

    table = Table(title="Knowledge Base Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Provider", provider.display_name)
    table.add_row("Total chunks", str(total))
    table.add_row("Documents", str(len(titles)))
    table.add_row("Unique tags", ", ".join(sorted(tags)) if tags else "None")
    table.add_row("Session queries", str(cost_tracker.query_count))
    table.add_row("Session cost", f"${cost_tracker.session_cost:.4f}")
    table.add_row("Search mode", "Hybrid (vector + BM25)")
    console.print(table)


CLAUDE_SHORTCUTS = {
    "claude": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "claude-haiku": "claude-haiku-4-5",
    "claude-opus": "claude-opus-4-7",
}


def switch_provider(name: str):
    name = name.strip().lower()

    if name in CLAUDE_SHORTCUTS or name.startswith("claude-"):
        model = CLAUDE_SHORTCUTS.get(name, name)
        try:
            return ClaudeProvider(model=model)
        except Exception as e:
            console.print(f"[red]Claude error: {e}[/red]")
            console.print("[yellow]Set ANTHROPIC_API_KEY environment variable[/yellow]")
            return None
    elif name.startswith("ollama"):
        model = name.split(":", 1)[1] if ":" in name else "qwen3"
        try:
            import ollama as _ollama
            _ollama.show(model)
            return OllamaProvider(model=model)
        except Exception:
            console.print(f"[red]Model '{model}' not found. Run: ollama pull {model}[/red]")
            return None
    else:
        console.print(f"[red]Unknown provider: {name}[/red]")
        console.print("[yellow]Options: claude, claude-haiku, claude-opus, ollama:model[/yellow]")
        return None


def build_benchmark_providers(aws_profile=None, aws_region=None, ollama_models=None):
    providers = {}

    for model, label in [("claude-sonnet-4-6", "Claude Sonnet"), ("claude-haiku-4-5", "Claude Haiku")]:
        try:
            providers[label] = ClaudeProvider(
                model=model, use_bedrock=True,
                aws_profile=aws_profile, aws_region=aws_region,
            )
        except Exception as e:
            console.print(f"[yellow]{label} unavailable: {e}[/yellow]")

    for model_name in (ollama_models or []):
        try:
            import ollama as _ollama
            _ollama.show(model_name)
            providers[f"Ollama ({model_name})"] = OllamaProvider(model=model_name)
        except Exception:
            console.print(f"[yellow]Ollama '{model_name}' unavailable[/yellow]")

    return providers


def main():
    parser = argparse.ArgumentParser(description="Personal Knowledge Base Agent")
    parser.add_argument("--provider", choices=["claude", "ollama"], default=None,
                        help="LLM provider: claude or ollama")
    parser.add_argument("--model", default=None,
                        help="Model name (e.g., claude-sonnet-4-6, claude-haiku-4-5, qwen3)")
    parser.add_argument("--aws-profile", default=None,
                        help="AWS SSO profile name (default: claude-code-sso-profile)")
    parser.add_argument("--aws-region", default=None,
                        help="AWS region for Bedrock (default: eu-west-1)")
    parser.add_argument("--no-bedrock", action="store_true",
                        help="Use direct Anthropic API instead of Bedrock")
    parser.add_argument("--benchmark", action="store_true",
                        help="Run benchmark comparing all available providers")
    parser.add_argument("--ollama-models", default=None,
                        help="Comma-separated Ollama models for benchmark (e.g., qwen3,gemma4)")
    args = parser.parse_args()

    # Build BM25 index on startup
    rebuild_bm25_index()

    if args.benchmark:
        ollama_list = [m.strip() for m in args.ollama_models.split(",")] if args.ollama_models else []
        benchmark_providers = build_benchmark_providers(
            aws_profile=args.aws_profile,
            aws_region=args.aws_region,
            ollama_models=ollama_list,
        )

        if not benchmark_providers:
            console.print("[red]No providers available for benchmark.[/red]")
            return
        if len(benchmark_providers) < 2:
            console.print("[yellow]Only 1 provider available — running single-provider benchmark.[/yellow]")

        run_benchmark(benchmark_providers)
        return

    provider = None

    if args.provider == "claude":
        try:
            model = args.model or "claude-sonnet-4-6"
            provider = ClaudeProvider(
                model=model,
                use_bedrock=not args.no_bedrock,
                aws_profile=args.aws_profile,
                aws_region=args.aws_region,
            )
        except Exception as e:
            console.print(f"[red]Claude init failed: {e}[/red]")
            console.print("[yellow]Run: aws sso login --profile claude-code-sso-profile[/yellow]")
            return
    elif args.provider == "ollama":
        model = args.model or "qwen3"
        try:
            import ollama as _ollama
            _ollama.show(model)
            provider = OllamaProvider(model=model)
        except Exception:
            console.print(f"[red]Ollama model '{model}' not found. Run: ollama pull {model}[/red]")
            return
    else:
        try:
            provider = ClaudeProvider(use_bedrock=True)
            console.print(f"[dim]Using Claude via {provider._provider_type}[/dim]")
        except Exception:
            pass
        if not provider and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                provider = ClaudeProvider(use_bedrock=False)
                console.print("[dim]Using Claude via direct API[/dim]")
            except Exception:
                pass
        if not provider:
            try:
                import ollama as _ollama
                _ollama.list()
                provider = OllamaProvider()
                console.print("[dim]Using Ollama (local)[/dim]")
            except Exception:
                console.print("[red]No provider available.[/red]")
                console.print("[yellow]Options:[/yellow]")
                console.print("[yellow]  1. aws sso login --profile claude-code-sso-profile[/yellow]")
                console.print("[yellow]  2. Set ANTHROPIC_API_KEY[/yellow]")
                console.print("[yellow]  3. Install Ollama[/yellow]")
                return

    print_welcome(provider)
    conversation_history = []

    while True:
        try:
            user_input = console.input("\n[bold green]You:[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() == "/quit":
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() == "/clear":
            conversation_history.clear()
            console.print("[dim]Conversation cleared. Knowledge base retained.[/dim]")
            continue

        if user_input.lower() == "/stats":
            show_stats(provider)
            continue

        if user_input.lower() == "/cost":
            console.print(cost_tracker.format_session_summary())
            continue

        if user_input.lower().startswith("/benchmark"):
            extra = user_input[10:].strip()
            inline_questions = None
            if extra:
                inline_questions = [{"question": extra, "expected_keywords": []}]
                console.print(f"[dim]Benchmarking with inline question: {extra}[/dim]")

            ollama_models = []
            models_input = console.input("[cyan]Ollama models to benchmark (comma-separated, or empty):[/cyan] ").strip()
            if models_input:
                ollama_models = [m.strip() for m in models_input.split(",")]
            bp = build_benchmark_providers(ollama_models=ollama_models)
            if bp:
                run_benchmark(bp, questions=inline_questions)
            else:
                console.print("[red]No providers available for benchmark.[/red]")
            continue

        if user_input.lower().startswith("/provider "):
            new_provider = switch_provider(user_input[10:])
            if new_provider:
                provider = new_provider
                conversation_history.clear()
                console.print(f"[green]Switched to {provider.display_name}[/green]")
            continue

        if user_input.lower() == "/list":
            result = tool_list_documents()
            data = json.loads(result)
            if not data.get("documents"):
                console.print("[yellow]Knowledge base is empty.[/yellow]")
            else:
                table = Table(title=f"Documents ({len(data['documents'])} docs, {data['total_chunks']} chunks)")
                table.add_column("Title", style="cyan")
                table.add_column("Tags", style="green")
                table.add_column("Chunks", style="yellow", justify="right")
                for doc in data["documents"]:
                    table.add_row(doc["title"], ", ".join(doc["tags"]) or "-", str(doc["chunks"]))
                console.print(table)
            continue

        if user_input.lower().startswith("/add"):
            title = console.input("  [cyan]Title:[/cyan] ").strip()
            console.print("  [cyan]Content (enter empty line to finish):[/cyan]")
            lines = []
            while True:
                line = console.input("  ")
                if not line:
                    break
                lines.append(line)
            tags_input = console.input("  [cyan]Tags (comma-separated):[/cyan] ").strip()
            content = "\n".join(lines)
            result = tool_add_document(title=title, content=content, tags=tags_input)
            console.print(f"  [green]Stored![/green] {json.loads(result)['chunks_stored']} chunks saved.")
            continue

        if user_input.lower().startswith("/ingest "):
            file_path = user_input[8:].strip().strip('"')
            console.print(f"  [dim]Ingesting {file_path}...[/dim]")
            result = tool_ingest_file(file_path=file_path)
            data = json.loads(result)
            if data.get("status") == "success":
                console.print(f"  [green]Ingested![/green] '{data['title']}' — {data['chunks_stored']} chunks stored.")
            else:
                console.print(f"  [red]{data.get('message', 'Ingest failed')}[/red]")
            continue

        console.print()
        try:
            cost_tracker.start_query()

            augmented = build_query_message(user_input)
            messages = list(conversation_history) + [{"role": "user", "content": augmented}]

            response = provider.chat(messages)
            cost_tracker.end_query()

            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": response})
            trim_conversation(conversation_history)

            console.print(Panel(Markdown(response), border_style="blue", title=provider.display_name))
            if isinstance(provider, ClaudeProvider):
                console.print(cost_tracker.format_query_cost())
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
