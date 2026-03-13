from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
import importlib
import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib import error, parse, request

import networkx as nx

from graph.knowledge_graph import KnowledgeGraph
from models.schemas import ModuleNode


class StructuredLLMClient(Protocol):
    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]: ...


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: list[str], *, model: str) -> list[list[float]]: ...


@dataclass(slots=True)
class ModelTierConfig:
    fast_provider: str = "gemini"
    fast_model: str = "gemini-1.5-flash"
    heavy_provider: str = "ollama"
    heavy_model: str = "llama3.1:8b-instruct"
    embedding_provider: str = "gemini"
    embedding_model: str = "text-embedding-004"
    bulk_budget_tokens: int = 120_000
    synthesis_budget_tokens: int = 80_000
    module_prompt_token_cap: int = 16_000
    evidence_chunk_lines: int = 30
    evidence_chunk_overlap: int = 5
    evidence_file_limit: int = 14

    @classmethod
    def from_env(cls, env: dict[str, str]) -> ModelTierConfig:
        return cls(
            fast_provider=_normalize_provider(env.get("SEMANTICIST_FAST_PROVIDER", cls.fast_provider)),
            fast_model=env.get("SEMANTICIST_FAST_MODEL", cls.fast_model),
            heavy_provider=_normalize_provider(env.get("SEMANTICIST_HEAVY_PROVIDER", cls.heavy_provider)),
            heavy_model=env.get("SEMANTICIST_HEAVY_MODEL", cls.heavy_model),
            embedding_provider=_normalize_provider(env.get("SEMANTICIST_EMBEDDING_PROVIDER", cls.embedding_provider)),
            embedding_model=env.get("SEMANTICIST_EMBEDDING_MODEL", cls.embedding_model),
            bulk_budget_tokens=_coerce_env_int(env.get("SEMANTICIST_BULK_BUDGET_TOKENS"), cls.bulk_budget_tokens),
            synthesis_budget_tokens=_coerce_env_int(env.get("SEMANTICIST_SYNTHESIS_BUDGET_TOKENS"), cls.synthesis_budget_tokens),
            module_prompt_token_cap=_coerce_env_int(env.get("SEMANTICIST_MODULE_PROMPT_TOKEN_CAP"), cls.module_prompt_token_cap),
            evidence_chunk_lines=_coerce_env_int(env.get("SEMANTICIST_EVIDENCE_CHUNK_LINES"), cls.evidence_chunk_lines),
            evidence_chunk_overlap=_coerce_env_int(env.get("SEMANTICIST_EVIDENCE_CHUNK_OVERLAP"), cls.evidence_chunk_overlap),
            evidence_file_limit=_coerce_env_int(env.get("SEMANTICIST_EVIDENCE_FILE_LIMIT"), cls.evidence_file_limit),
        )


@dataclass(slots=True)
class UsageRecord:
    provider: str
    model: str
    prompt_tokens: int
    response_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.response_tokens


@dataclass(slots=True)
class PurposeStatementResult:
    module_path: str
    purpose_statement: str
    documentation_drift: bool
    provider_used: str
    model_used: str
    prompt_tokens: int
    response_tokens: int
    reasoning: str | None = None


@dataclass(slots=True)
class DomainCluster:
    cluster_id: int
    domain_label: str
    purpose_statements: list[str]
    member_indices: list[int]


@dataclass(slots=True)
class DayOneAnswer:
    question: str
    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class EvidencePacket:
    path: str
    line_start: int
    line_end: int
    excerpt: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "excerpt": self.excerpt,
        }


class HTTPJsonClient:
    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: int = 90,
    ) -> dict[str, Any]:
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        body = json.dumps(payload).encode("utf-8")
        request_object = request.Request(url, data=body, headers=request_headers, method="POST")

        try:
            with request.urlopen(request_object, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - depends on remote service
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} calling {url}: {details}") from exc
        except error.URLError as exc:  # pragma: no cover - depends on remote service
            raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


class GeminiStructuredLLMClient(HTTPJsonClient):
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def generate_json(self, *, model: str, prompt: str, temperature: float = 0.0) -> dict[str, Any]:
        model_name = _normalize_gemini_model_name(model)
        endpoint = f"{self.base_url}/{model_name}:generateContent?key={parse.quote(self.api_key)}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        response = self._post_json(endpoint, payload)
        text = _extract_gemini_text(response)
        return _parse_json_text(text)


class OllamaStructuredLLMClient(HTTPJsonClient):
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def generate_json(self, *, model: str, prompt: str, temperature: float = 0.0) -> dict[str, Any]:
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": f"{prompt}\n\nReturn valid JSON only.",
            "format": "json",
            "stream": False,
            "options": {"temperature": temperature},
        }
        response = self._post_json(endpoint, payload)
        return _parse_json_text(str(response.get("response", "")))


class GeminiEmbeddingClient(HTTPJsonClient):
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def embed_texts(self, texts: list[str], *, model: str) -> list[list[float]]:
        model_name = _normalize_gemini_model_name(model)
        embeddings: list[list[float]] = []
        for text in texts:
            endpoint = f"{self.base_url}/{model_name}:embedContent?key={parse.quote(self.api_key)}"
            payload = {
                "model": model_name,
                "content": {"parts": [{"text": text}]},
            }
            response = self._post_json(endpoint, payload)
            values = response.get("embedding", {}).get("values")
            if not isinstance(values, list):
                raise RuntimeError("Gemini embedding response did not include embedding values.")
            embeddings.append([float(value) for value in values])
        return embeddings


class OllamaEmbeddingClient(HTTPJsonClient):
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def embed_texts(self, texts: list[str], *, model: str) -> list[list[float]]:
        endpoint = f"{self.base_url}/api/embed"
        payload = {"model": model, "input": texts}
        response = self._post_json(endpoint, payload)
        values = response.get("embeddings")
        if not isinstance(values, list):
            single = response.get("embedding")
            if isinstance(single, list):
                return [[float(value) for value in single]]
            raise RuntimeError("Ollama embedding response did not include embeddings.")
        return [[float(value) for value in embedding] for embedding in values]


class ContextWindowBudget:
    def __init__(self, config: ModelTierConfig | None = None) -> None:
        self.config = config or ModelTierConfig()
        self.usage_history: list[UsageRecord] = []

    def estimate_tokens(self, text: str, *, model: str | None = None) -> int:
        if not text:
            return 0

        tiktoken_module = self._load_tiktoken()
        if tiktoken_module is None:
            return max(1, len(text) // 4)

        encoding = tiktoken_module.get_encoding(self._encoding_name_for_model(model or self.config.fast_model))
        return len(encoding.encode(text))

    def record_usage(self, *, provider: str, model: str, prompt: str, response: str) -> UsageRecord:
        record = UsageRecord(
            provider=provider,
            model=model,
            prompt_tokens=self.estimate_tokens(prompt, model=model),
            response_tokens=self.estimate_tokens(response, model=model),
        )
        self.usage_history.append(record)
        return record

    def cumulative_tokens(self, *, provider: str | None = None, model: str | None = None) -> int:
        total = 0
        for record in self.usage_history:
            if provider is not None and record.provider != provider:
                continue
            if model is not None and record.model != model:
                continue
            total += record.total_tokens
        return total

    def task_descriptor(self, task_type: str) -> tuple[str, str]:
        if task_type in {"bulk_summary", "cluster_label"}:
            return self.config.fast_provider, self.config.fast_model
        if task_type in {"final_synthesis", "day_one_questions"}:
            return self.config.heavy_provider, self.config.heavy_model
        if task_type == "embedding":
            return self.config.embedding_provider, self.config.embedding_model
        return self.config.fast_provider, self.config.fast_model

    def remaining_budget(self, task_type: str) -> int:
        provider, model = self.task_descriptor(task_type)
        budget_limit = self.config.synthesis_budget_tokens if task_type in {"final_synthesis", "day_one_questions"} else self.config.bulk_budget_tokens
        return budget_limit - self.cumulative_tokens(provider=provider, model=model)

    def trim_to_token_limit(self, text: str, *, model: str, token_limit: int) -> str:
        if self.estimate_tokens(text, model=model) <= token_limit:
            return text

        trimmed_lines: list[str] = []
        for line in text.splitlines():
            candidate = "\n".join(trimmed_lines + [line])
            if self.estimate_tokens(candidate, model=model) > token_limit:
                break
            trimmed_lines.append(line)

        return "\n".join(trimmed_lines)

    def _load_tiktoken(self):
        try:
            return importlib.import_module("tiktoken")
        except ImportError:
            return None

    def _encoding_name_for_model(self, model: str) -> str:
        if model.startswith(("gpt-4", "gpt-4o", "gpt-5", "text-embedding")):
            return "cl100k_base"
        if "claude" in model or "gemini" in model or ":" in model:
            return "cl100k_base"
        return "cl100k_base"


class SemanticistAgent:
    FDE_DAY_ONE_QUESTIONS = [
        "What business capability does this codebase primarily support?",
        "Which modules and workflows should a new engineer read first to understand the system's critical path?",
        "Where are the highest-risk change surfaces, and why?",
        "How does data enter, move through, and exit the system?",
        "What domain architecture map best explains how responsibilities are split across the codebase?",
    ]

    def __init__(
        self,
        repository_path: str | Path,
        *,
        llm_client: StructuredLLMClient | None = None,
        embedding_client: EmbeddingClient | None = None,
        budget: ContextWindowBudget | None = None,
        model_config: ModelTierConfig | None = None,
        env_path: str | Path | None = None,
    ) -> None:
        self.repository_path = Path(repository_path).resolve()
        self.environment = self._load_environment(env_path)
        resolved_config = model_config or ModelTierConfig.from_env(self.environment)
        self.budget = budget or ContextWindowBudget(resolved_config)
        self.model_config = self.budget.config
        self._llm_override = llm_client
        self._embedding_override = embedding_client
        self._llm_clients: dict[str, StructuredLLMClient] = {}
        self._embedding_clients: dict[str, EmbeddingClient] = {}

    def generate_purpose_statement(self, module_node: ModuleNode) -> PurposeStatementResult:
        module_path = self._resolve_module_path(module_node)
        module_source = module_path.read_text(encoding="utf-8")
        existing_docstring = self._extract_module_docstring(module_source)
        module_code = self._strip_module_docstring(module_source)
        provider, model = self.budget.task_descriptor("bulk_summary")
        trimmed_code = self.budget.trim_to_token_limit(
            module_code,
            model=model,
            token_limit=self.model_config.module_prompt_token_cap,
        )
        prompt = self._purpose_statement_prompt(module_node, trimmed_code, existing_docstring)
        payload = self._llm_client_for(provider).generate_json(model=model, prompt=prompt, temperature=0.1)
        response_text = json.dumps(payload)
        usage = self.budget.record_usage(provider=provider, model=model, prompt=prompt, response=response_text)

        purpose_statement = str(payload.get("purpose_statement", "")).strip()
        if not purpose_statement:
            raise RuntimeError(f"{provider}:{model} did not return a purpose_statement for {module_node.path}.")

        return PurposeStatementResult(
            module_path=module_node.path,
            purpose_statement=purpose_statement,
            documentation_drift=bool(payload.get("documentation_drift", False)),
            provider_used=provider,
            model_used=model,
            prompt_tokens=usage.prompt_tokens,
            response_tokens=usage.response_tokens,
            reasoning=str(payload.get("reasoning", "")).strip() or None,
        )

    def cluster_into_domains(
        self,
        purpose_statements: list[str],
        *,
        min_k: int = 5,
        max_k: int = 8,
    ) -> dict[str, Any]:
        cleaned_statements = [statement.strip() for statement in purpose_statements if statement.strip()]
        if not cleaned_statements:
            return {"k": 0, "clusters": [], "assignments": [], "domain_map": {}}

        embedding_provider, embedding_model = self.budget.task_descriptor("embedding")
        embeddings = self._embedding_client_for(embedding_provider).embed_texts(cleaned_statements, model=embedding_model)
        cluster_count = self._select_cluster_count(embeddings, min_k=min_k, max_k=max_k)

        if cluster_count <= 1:
            assignments = [0 for _ in cleaned_statements]
        else:
            kmeans_class = self._load_kmeans()
            if kmeans_class is None:
                raise RuntimeError("scikit-learn is required to run k-means clustering for SemanticistAgent.")
            kmeans = kmeans_class(n_clusters=cluster_count, random_state=42, n_init=10)
            assignments = list(kmeans.fit_predict(embeddings).tolist())

        cluster_members: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for index, cluster_id in enumerate(assignments):
            cluster_members[int(cluster_id)].append((index, cleaned_statements[index]))

        clusters: list[DomainCluster] = []
        domain_map: dict[str, list[str]] = {}
        for cluster_id in sorted(cluster_members):
            members = cluster_members[cluster_id]
            member_indices = [index for index, _ in members]
            member_statements = [statement for _, statement in members]
            domain_label = self._label_cluster(member_statements)
            clusters.append(
                DomainCluster(
                    cluster_id=cluster_id,
                    domain_label=domain_label,
                    purpose_statements=member_statements,
                    member_indices=member_indices,
                )
            )
            domain_map[domain_label] = member_statements

        return {
            "k": cluster_count,
            "clusters": [
                {
                    "cluster_id": cluster.cluster_id,
                    "domain_label": cluster.domain_label,
                    "purpose_statements": cluster.purpose_statements,
                    "member_indices": cluster.member_indices,
                }
                for cluster in clusters
            ],
            "assignments": assignments,
            "domain_map": domain_map,
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
        }

    def answer_day_one_questions(self, surveyor_output: Any, hydrologist_output: Any) -> dict[str, Any]:
        provider, model = self.budget.task_descriptor("day_one_questions")
        surveyor_graph = self._coerce_to_graph(surveyor_output)
        hydrologist_graph = self._coerce_to_graph(hydrologist_output)
        evidence_bundle = self._build_evidence_bundle(surveyor_graph, hydrologist_graph)
        prompt = self._day_one_prompt(surveyor_graph, hydrologist_graph, evidence_bundle)
        payload = self._llm_client_for(provider).generate_json(model=model, prompt=prompt, temperature=0.1)
        response_text = json.dumps(payload)
        usage = self.budget.record_usage(provider=provider, model=model, prompt=prompt, response=response_text)
        answers = self._normalize_day_one_answers(payload, evidence_bundle)

        return {
            "provider_used": provider,
            "model_used": model,
            "prompt_tokens": usage.prompt_tokens,
            "response_tokens": usage.response_tokens,
            "answers": answers,
            "evidence_bundle": evidence_bundle,
        }

    def _load_environment(self, env_path: str | Path | None) -> dict[str, str]:
        combined = dict(os.environ)
        default_env_path = Path(env_path).resolve() if env_path is not None else self.repository_path / ".env"
        if default_env_path.exists():
            for key, value in _read_env_file(default_env_path).items():
                combined.setdefault(key, value)
        return combined

    def _llm_client_for(self, provider: str) -> StructuredLLMClient:
        if self._llm_override is not None:
            return self._llm_override
        if provider in self._llm_clients:
            return self._llm_clients[provider]

        if provider == "gemini":
            api_key = self.environment.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is required in .env for Gemini-backed SemanticistAgent tasks.")
            client = GeminiStructuredLLMClient(api_key=api_key, base_url=self.environment.get("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"))
        elif provider == "ollama":
            client = OllamaStructuredLLMClient(base_url=self.environment.get("OLLAMA_BASE_URL", "http://localhost:11434"))
        else:
            raise RuntimeError(f"Unsupported LLM provider: {provider}")

        self._llm_clients[provider] = client
        return client

    def _embedding_client_for(self, provider: str) -> EmbeddingClient:
        if self._embedding_override is not None:
            return self._embedding_override
        if provider in self._embedding_clients:
            return self._embedding_clients[provider]

        if provider == "gemini":
            api_key = self.environment.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is required in .env for Gemini embeddings.")
            client = GeminiEmbeddingClient(api_key=api_key, base_url=self.environment.get("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"))
        elif provider == "ollama":
            client = OllamaEmbeddingClient(base_url=self.environment.get("OLLAMA_BASE_URL", "http://localhost:11434"))
        else:
            raise RuntimeError(f"Unsupported embedding provider: {provider}")

        self._embedding_clients[provider] = client
        return client

    def _resolve_module_path(self, module_node: ModuleNode) -> Path:
        module_path = Path(module_node.path)
        if module_path.is_absolute():
            return module_path
        return (self.repository_path / module_path).resolve()

    def _extract_module_docstring(self, module_source: str) -> str | None:
        try:
            module = ast.parse(module_source)
        except SyntaxError:
            return None
        return ast.get_docstring(module, clean=False)

    def _strip_module_docstring(self, module_source: str) -> str:
        try:
            module = ast.parse(module_source)
        except SyntaxError:
            return module_source

        if not module.body:
            return module_source

        first_statement = module.body[0]
        is_docstring = (
            isinstance(first_statement, ast.Expr)
            and isinstance(first_statement.value, ast.Constant)
            and isinstance(first_statement.value.value, str)
        )
        if not is_docstring:
            return module_source

        lines = module_source.splitlines()
        start_line = first_statement.lineno - 1
        end_line = first_statement.end_lineno or first_statement.lineno
        return "\n".join(lines[:start_line] + lines[end_line:])

    def _load_kmeans(self):
        try:
            return importlib.import_module("sklearn.cluster").KMeans
        except ImportError:
            return None

    def _load_silhouette_score(self):
        try:
            return importlib.import_module("sklearn.metrics").silhouette_score
        except ImportError:
            return None

    def _select_cluster_count(self, embeddings: list[list[float]], *, min_k: int, max_k: int) -> int:
        sample_count = len(embeddings)
        if sample_count <= 1:
            return sample_count
        if sample_count <= min_k:
            return sample_count

        candidate_upper = min(max_k, sample_count - 1)
        candidate_lower = min(min_k, candidate_upper)
        candidates = list(range(candidate_lower, candidate_upper + 1))
        if len(candidates) == 1:
            return candidates[0]

        kmeans_class = self._load_kmeans()
        silhouette_score = self._load_silhouette_score()
        if kmeans_class is None or silhouette_score is None:
            return candidates[0]

        best_k = candidates[0]
        best_score = -1.0
        for cluster_count in candidates:
            kmeans = kmeans_class(n_clusters=cluster_count, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)
            score = float(silhouette_score(embeddings, labels))
            if score > best_score:
                best_k = cluster_count
                best_score = score
        return best_k

    def _label_cluster(self, cluster_statements: list[str]) -> str:
        provider, model = self.budget.task_descriptor("cluster_label")
        prompt = self._cluster_label_prompt(cluster_statements)
        payload = self._llm_client_for(provider).generate_json(model=model, prompt=prompt, temperature=0.0)
        self.budget.record_usage(provider=provider, model=model, prompt=prompt, response=json.dumps(payload))
        label = str(payload.get("domain_label", "")).strip().lower()
        if not label:
            raise RuntimeError(f"{provider}:{model} did not return a domain label.")
        return label

    def _coerce_to_graph(self, output: Any) -> nx.DiGraph:
        if isinstance(output, KnowledgeGraph):
            return output.graph
        if isinstance(output, nx.DiGraph):
            return output
        if isinstance(output, dict) and "nodes" in output:
            return nx.node_link_graph(output, edges="links")
        raise TypeError("Expected KnowledgeGraph, networkx.DiGraph, or node-link graph payload.")

    def _build_evidence_bundle(self, surveyor_graph: nx.DiGraph, hydrologist_graph: nx.DiGraph) -> dict[str, Any]:
        candidate_files = self._candidate_evidence_files(surveyor_graph, hydrologist_graph)[: self.model_config.evidence_file_limit]
        remaining_budget = max(4_000, self.budget.remaining_budget("day_one_questions"))
        evidence_packets: list[EvidencePacket] = []
        consumed_tokens = 0

        for relative_path in candidate_files:
            absolute_path = self.repository_path / relative_path
            if not absolute_path.exists() or not absolute_path.is_file():
                continue

            for packet in self._make_evidence_packets(relative_path, absolute_path):
                token_cost = self.budget.estimate_tokens(packet.excerpt)
                if evidence_packets and consumed_tokens + token_cost > remaining_budget:
                    break
                evidence_packets.append(packet)
                consumed_tokens += token_cost

        return {
            "files": [packet.as_dict() for packet in evidence_packets],
            "surveyor_summary": self._summarize_surveyor_graph(surveyor_graph),
            "hydrologist_summary": self._summarize_hydrologist_graph(hydrologist_graph),
        }

    def _candidate_evidence_files(self, surveyor_graph: nx.DiGraph, hydrologist_graph: nx.DiGraph) -> list[str]:
        files: list[str] = []
        seen: set[str] = set()

        graph_metadata = surveyor_graph.graph if isinstance(surveyor_graph.graph, dict) else {}
        for hub in graph_metadata.get("architectural_hubs", [])[:6]:
            path = hub.get("path") if isinstance(hub, dict) else None
            if isinstance(path, str) and path not in seen:
                seen.add(path)
                files.append(path)

        for file_entry in graph_metadata.get("high_velocity_core", {}).get("files", [])[:6]:
            path = file_entry.get("path") if isinstance(file_entry, dict) else None
            if isinstance(path, str) and path not in seen:
                seen.add(path)
                files.append(path)

        for _, attributes in surveyor_graph.nodes(data=True):
            if attributes.get("node_type") != "module":
                continue
            path = attributes.get("path")
            if isinstance(path, str) and path not in seen:
                seen.add(path)
                files.append(path)

        for node_id, attributes in hydrologist_graph.nodes(data=True):
            if attributes.get("node_type") == "transformation" and self._looks_like_repo_file(node_id) and node_id not in seen:
                seen.add(node_id)
                files.append(node_id)
            source_file = attributes.get("source_file")
            if isinstance(source_file, str) and source_file not in seen:
                seen.add(source_file)
                files.append(source_file)

        return files

    def _make_evidence_packets(self, relative_path: str, absolute_path: Path) -> list[EvidencePacket]:
        lines = absolute_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return []

        chunk_size = max(10, self.model_config.evidence_chunk_lines)
        step = max(1, chunk_size - self.model_config.evidence_chunk_overlap)
        packets: list[EvidencePacket] = []
        for start_index in range(0, len(lines), step):
            end_index = min(len(lines), start_index + chunk_size)
            selected_lines = lines[start_index:end_index]
            if not any(line.strip() for line in selected_lines):
                continue
            excerpt = "\n".join(
                f"{line_number}: {line}"
                for line_number, line in enumerate(selected_lines, start=start_index + 1)
            )
            packets.append(
                EvidencePacket(
                    path=relative_path,
                    line_start=start_index + 1,
                    line_end=end_index,
                    excerpt=excerpt,
                )
            )
            if end_index == len(lines):
                break
        return packets

    def _summarize_surveyor_graph(self, surveyor_graph: nx.DiGraph) -> dict[str, Any]:
        module_nodes = [node_id for node_id, attrs in surveyor_graph.nodes(data=True) if attrs.get("node_type") == "module"]
        function_nodes = [node_id for node_id, attrs in surveyor_graph.nodes(data=True) if attrs.get("node_type") == "function"]
        return {
            "module_count": len(module_nodes),
            "function_count": len(function_nodes),
            "architectural_hubs": surveyor_graph.graph.get("architectural_hubs", [])[:5],
            "high_velocity_core": surveyor_graph.graph.get("high_velocity_core", {}),
            "strongly_connected_components": surveyor_graph.graph.get("strongly_connected_components", []),
        }

    def _summarize_hydrologist_graph(self, hydrologist_graph: nx.DiGraph) -> dict[str, Any]:
        datasets = [node_id for node_id, attrs in hydrologist_graph.nodes(data=True) if attrs.get("node_type") == "dataset"]
        transformations = [node_id for node_id, attrs in hydrologist_graph.nodes(data=True) if attrs.get("node_type") == "transformation"]
        source_nodes = [
            node_id
            for node_id, attrs in hydrologist_graph.nodes(data=True)
            if attrs.get("node_type") == "dataset" and hydrologist_graph.in_degree(node_id) == 0
        ]
        sink_nodes = [
            node_id
            for node_id, attrs in hydrologist_graph.nodes(data=True)
            if attrs.get("node_type") == "dataset" and hydrologist_graph.out_degree(node_id) == 0
        ]
        return {
            "dataset_count": len(datasets),
            "transformation_count": len(transformations),
            "source_nodes": sorted(source_nodes)[:10],
            "sink_nodes": sorted(sink_nodes)[:10],
        }

    def _normalize_day_one_answers(self, payload: dict[str, Any], evidence_bundle: dict[str, Any]) -> list[dict[str, Any]]:
        valid_citations = {
            (file_entry["path"], int(file_entry["line_start"]), int(file_entry["line_end"]))
            for file_entry in evidence_bundle.get("files", [])
        }
        answers = payload.get("answers")
        if not isinstance(answers, list) or len(answers) != len(self.FDE_DAY_ONE_QUESTIONS):
            raise RuntimeError("Day-one synthesis response did not return the expected five answers.")

        normalized_answers: list[dict[str, Any]] = []
        for expected_question, answer_payload in zip(self.FDE_DAY_ONE_QUESTIONS, answers):
            if not isinstance(answer_payload, dict):
                raise RuntimeError("Day-one synthesis returned a malformed answer entry.")

            citations: list[dict[str, Any]] = []
            for citation in answer_payload.get("citations", []):
                if not isinstance(citation, dict):
                    continue
                path = citation.get("path")
                line_start = citation.get("line_start")
                line_end = citation.get("line_end")
                if not isinstance(path, str):
                    continue
                try:
                    candidate = (path, int(line_start), int(line_end))
                except (TypeError, ValueError):
                    continue
                if candidate in valid_citations:
                    citations.append({"path": candidate[0], "line_start": candidate[1], "line_end": candidate[2]})

            if not citations:
                raise RuntimeError(f"Day-one answer for '{expected_question}' did not include valid evidence citations.")

            normalized_answers.append(
                {
                    "question": expected_question,
                    "answer": str(answer_payload.get("answer", "")).strip(),
                    "citations": citations,
                }
            )

        return normalized_answers

    def _purpose_statement_prompt(self, module_node: ModuleNode, module_code: str, existing_docstring: str | None) -> str:
        docstring_section = existing_docstring.strip() if existing_docstring else "<no module docstring present>"
        return (
            "You are a software architecture analyst. Read the module code and return JSON with keys purpose_statement, documentation_drift, and reasoning.\n"
            "Rules:\n"
            "- purpose_statement must be 2-3 sentences.\n"
            "- explain the business function of the module, not implementation details.\n"
            "- compare the purpose statement to the existing docstring summary.\n"
            "- set documentation_drift=true only when the code's purpose materially contradicts the docstring.\n"
            "- reasoning must be one short sentence.\n\n"
            f"Module path: {module_node.path}\n"
            f"Existing docstring summary:\n{docstring_section}\n\n"
            f"Module code without docstring:\n{module_code}"
        )

    def _cluster_label_prompt(self, cluster_statements: list[str]) -> str:
        joined = "\n".join(f"- {statement}" for statement in cluster_statements)
        return (
            "You are labeling a software domain cluster. Return JSON with one key: domain_label.\n"
            "Rules:\n"
            "- label must be 1-2 words.\n"
            "- prefer business/domain labels like ingestion, orchestration, serving, finance, quality.\n"
            "- do not use library names or implementation details.\n\n"
            f"Purpose statements:\n{joined}"
        )

    def _day_one_prompt(self, surveyor_graph: nx.DiGraph, hydrologist_graph: nx.DiGraph, evidence_bundle: dict[str, Any]) -> str:
        return (
            "You are onboarding a forward-deployed engineer to a brownfield system. Answer the five day-one questions in JSON with a top-level key answers.\n"
            "Each answer must have question, answer, and citations.\n"
            "Citations must be a list of objects with path, line_start, and line_end.\n"
            "You may only cite exact path/line_start/line_end combinations that appear in the evidence bundle.\n"
            "Every material claim must have at least one citation.\n"
            "Do not invent files or ranges.\n\n"
            f"Questions:\n{json.dumps(self.FDE_DAY_ONE_QUESTIONS, indent=2)}\n\n"
            f"Surveyor summary:\n{json.dumps(self._summarize_surveyor_graph(surveyor_graph), indent=2)}\n\n"
            f"Hydrologist summary:\n{json.dumps(self._summarize_hydrologist_graph(hydrologist_graph), indent=2)}\n\n"
            f"Evidence bundle:\n{json.dumps(evidence_bundle, indent=2)}"
        )

    def _looks_like_repo_file(self, node_id: str) -> bool:
        return "/" in node_id and not node_id.startswith(("airflow:", "s3://", "gs://", "dbfs:/", "dynamic://"))


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _coerce_env_int(raw_value: str | None, default: int) -> int:
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _normalize_provider(provider: str) -> str:
    return provider.strip().lower()


def _normalize_gemini_model_name(model: str) -> str:
    return model if model.startswith("models/") else f"models/{model}"


def _extract_gemini_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in response.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        raise RuntimeError("Gemini response did not include any text parts.")
    return "\n".join(parts)


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].lstrip()

    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        payload = json.loads(cleaned[start:end + 1])
        if isinstance(payload, dict):
            return payload

    raise RuntimeError(f"Model response was not valid JSON: {text[:400]}")


__all__ = [
    "ContextWindowBudget",
    "DayOneAnswer",
    "DomainCluster",
    "EmbeddingClient",
    "EvidencePacket",
    "GeminiEmbeddingClient",
    "GeminiStructuredLLMClient",
    "ModelTierConfig",
    "OllamaEmbeddingClient",
    "OllamaStructuredLLMClient",
    "PurposeStatementResult",
    "SemanticistAgent",
    "StructuredLLMClient",
    "UsageRecord",
]
