"""编排层：把「检索 → 拼提示词 → 调用模型 → 生成引用」串成一次问答。

对应方案书"系统架构设计"里的算法层 / 应用层之间的服务层。
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from app.config import Settings
from app.llm.base import build_backend
from app.rag.chunker import list_documents
from app.rag.dify_store import DifyRetriever
from app.rag.local_store import EmbeddingClient, LocalIndex
from app.scenes import Scene, load_scene
from app.schemas import Answer, Citation, Retrieved

SNIPPET_LIMIT = 160


class SceneService:
    """一个场景一个实例；界面里切换场景时重建即可。"""

    def __init__(self, settings: Settings, scene_id: str | None = None) -> None:
        self.settings = settings
        self.scene: Scene = load_scene(
            settings.scenes_dir, settings.knowledge_dir, scene_id or settings.scene_id
        )
        self.backend = build_backend(settings)

        self.embedding_client: EmbeddingClient | None = None
        if settings.embedding_enabled:
            self.embedding_client = EmbeddingClient(
                base_url=settings.embedding_base_url,
                api_key=settings.embedding_api_key,
                model=settings.embedding_model,
                timeout=settings.llm_timeout,
            )

        self.index: LocalIndex | None = None
        self.dify: DifyRetriever | None = None
        if settings.resolved_retrieval_backend == "dify":
            self.dify = DifyRetriever(
                api_base=settings.dify_api_base,
                api_key=settings.dify_api_key,
                dataset_id=settings.dify_dataset_id,
                timeout=settings.llm_timeout,
            )
        else:
            self._load_or_build_index()

    # ---------- 索引 ----------

    @property
    def index_path(self) -> Path:
        return self.settings.index_dir / f"{self.scene.scene_id}.json"

    def _load_or_build_index(self) -> None:
        index = LocalIndex.load(self.scene.scene_id, self.index_path)
        if index is None or (index.is_empty and list_documents(self.scene.kb_dir)):
            index = LocalIndex(self.scene.scene_id, self.index_path)
            index.build(
                self.scene.kb_dir,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
                self.embedding_client,
            )
        self.index = index

    def rebuild_index(self) -> dict[str, object]:
        index = LocalIndex(self.scene.scene_id, self.index_path)
        meta = index.build(
            self.scene.kb_dir,
            self.settings.chunk_size,
            self.settings.chunk_overlap,
            self.embedding_client,
        )
        self.index = index
        return meta

    def import_documents(self, paths: list[str]) -> list[str]:
        """把上传的文件复制进本场景知识库目录，返回落盘文件名。"""
        self.scene.kb_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for raw in paths or []:
            source = Path(raw)
            if not source.is_file():
                continue
            target = self.scene.kb_dir / source.name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            saved.append(target.name)
        return saved

    # ---------- 检索 ----------

    def retrieve(self, query: str) -> list[Retrieved]:
        """先用「地板分」过滤掉明显无关的片段。"""
        if self.dify is not None:
            return self.dify.search(query, self.settings.top_k, self.settings.score_threshold)
        assert self.index is not None
        return self.index.search(
            query,
            self.settings.top_k,
            self.settings.score_threshold,
            self.embedding_client,
        )

    # ---------- 相关度门控（降幻觉的关键设计）----------

    def _matched_domain_keywords(self, question: str) -> list[str]:
        return [word for word in self.scene.domain_keywords if word in question]

    def _rule_gate(self, question: str, hits: list[Retrieved]) -> tuple[bool, str]:
        """双阈值规则：

        1. 最高分 ≥ refuse_min_score  → 放行（分数足够强，无需再看领域词）
        2. 否则必须命中领域词表       → 放行
        3. 两者都不满足               → 拒答

        之所以需要第 2 条：TF-IDF / 向量检索在字面相近但语义无关的问题上
        （例如「推荐附近的火锅店」vs「火灾处置」）也会给出中等分数，
        单靠阈值无法稳定拦截，必须叠加领域一致性校验。
        """
        if not hits:
            return False, "未检索到任何片段"

        top_score = hits[0].score
        if top_score >= self.settings.refuse_min_score:
            return True, f"最高相关度 {top_score:.2f} ≥ 门槛 {self.settings.refuse_min_score:.2f}"

        matched = self._matched_domain_keywords(question)
        if matched and top_score >= self.settings.weak_min_score:
            return True, (
                f"最高相关度 {top_score:.2f} 未达门槛，但 ≥ 弱相关下限 "
                f"{self.settings.weak_min_score:.2f} 且命中领域词：{'、'.join(matched[:5])}"
            )

        return False, (
            f"最高相关度仅 {top_score:.2f}（低于门槛 {self.settings.refuse_min_score:.2f}）"
            + (
                f"，虽命中领域词 {'、'.join(matched[:3])} 但相关度过低"
                if matched
                else "，且未命中场景领域词"
            )
        )

    def _llm_gate(self, question: str, hits: list[Retrieved]) -> tuple[bool, str]:
        """可选的 LLM 判定门控；模型不可用时自动退回规则门控。"""
        if self.backend.name == "mock":
            return self._rule_gate(question, hits)
        preview = "\n".join(f"- {hit.chunk.text[:200]}" for hit in hits[:3])
        judge_prompt = (
            "你是检索质量判定器。判断下面的问题是否属于给定场景，"
            "以及检索片段能否支撑回答。只输出「是」或「否」，不要解释。"
        )
        judge_question = (
            f"场景：{self.scene.name}（{self.scene.domain}）\n"
            f"问题：{question}\n"
            f"检索片段：\n{preview}\n"
        )
        try:
            result = self.backend.chat(judge_prompt, judge_question)
        except Exception:  # noqa: BLE001
            return self._rule_gate(question, hits)
        verdict = result.text.strip()
        if verdict.startswith("是"):
            return True, "LLM 判定：相关"
        if verdict.startswith("否"):
            return False, "LLM 判定：不相关"
        return self._rule_gate(question, hits)

    def check_relevance(self, question: str, hits: list[Retrieved]) -> tuple[bool, str]:
        # 1) 非知识型意图拦截：问法本身超出知识库承载范围时直接拒答
        blocked = [p for p in self.scene.out_of_scope_patterns if p in question]
        if blocked:
            return False, f"问题命中非知识型意图模式：{'、'.join(blocked[:3])}"

        # 2) 相关度门控
        gate = (self.settings.relevance_gate or "rule").strip().lower()
        if gate == "off":
            return bool(hits), "门控已关闭"
        if gate == "llm":
            return self._llm_gate(question, hits)
        return self._rule_gate(question, hits)

    @staticmethod
    def _format_context(hits: list[Retrieved]) -> str:
        if not hits:
            return "（无）"
        blocks = []
        for position, hit in enumerate(hits, start=1):
            blocks.append(
                f"[{position}] 来源：{hit.chunk.source}（相关度 {hit.score:.2f}）\n{hit.chunk.text}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _to_citations(hits: list[Retrieved]) -> list[Citation]:
        return [
            Citation(
                doc_title=hit.chunk.doc_title,
                source=hit.chunk.source,
                score=hit.score,
                snippet=hit.chunk.text[:SNIPPET_LIMIT].replace("\n", " "),
            )
            for hit in hits
        ]

    # ---------- 问答 ----------

    def answer(self, question: str, history: list[dict[str, str]] | None = None) -> Answer:
        question = (question or "").strip()
        if not question:
            return Answer(text="请输入你的问题。", backend=self.backend.name)

        started = time.perf_counter()
        retrieval_started = time.perf_counter()
        try:
            hits = self.retrieve(question)
            retrieval_error = None
        except Exception as exc:  # noqa: BLE001 - 检索失败也要给出可读反馈，便于演示排障
            hits, retrieval_error = [], str(exc)
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000

        if retrieval_error:
            return Answer(
                text=(
                    f"⚠️ 检索失败：{retrieval_error}\n\n"
                    "请检查 Dify 服务是否启动、API Key 是否有效，或切换到 `APP_MODE=mock` 先跑通界面。"
                ),
                backend=self.backend.name,
                retrieval_ms=round(retrieval_ms, 1),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )

        citations = self._to_citations(hits)
        relevant, reason = self.check_relevance(question, hits)
        refused = not relevant

        if refused:
            # 命中不足时不交给模型自由发挥，直接拒答：这是"降低幻觉"的设计点
            text = (
                "**结论**：未在知识库中检索到足以支撑该问题的内容。\n\n"
                f"{self.scene.refusal_hint}\n\n"
                f"> 判定依据：{reason}。\n"
                "> 本助手受限于知识库范围，检索不到依据时不会给出推测性回答。"
            )
            latency_ms = (time.perf_counter() - started) * 1000
            return Answer(
                text=text,
                citations=[],
                latency_ms=round(latency_ms, 1),
                backend=self.backend.name,
                retrieval_ms=round(retrieval_ms, 1),
                generation_ms=0.0,
                refused=True,
            )

        retrieved_text = self._format_context(hits)
        prompt = self.scene.prompt_with_context(retrieved_text)
        generation_started = time.perf_counter()
        try:
            result = self.backend.chat(prompt, question, history)
        except Exception as exc:  # noqa: BLE001
            result = None
            generation_error = str(exc)
        else:
            generation_error = ""
        generation_ms = (time.perf_counter() - generation_started) * 1000

        if result is None:
            return Answer(
                text=(
                    f"⚠️ 模型调用失败：{generation_error}\n\n"
                    "已检索到相关内容，可先参考下方引用来源。"
                ),
                citations=citations,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                backend=self.backend.name,
                retrieval_ms=round(retrieval_ms, 1),
                generation_ms=round(generation_ms, 1),
                retrieved_ids=[hit.chunk.chunk_id for hit in hits],
            )

        return Answer(
            text=result.text,
            citations=citations,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            backend=result.backend,
            retrieval_ms=round(retrieval_ms, 1),
            generation_ms=round(generation_ms, 1),
            retrieved_ids=[hit.chunk.chunk_id for hit in hits],
            retrieved_text=retrieved_text,
            usage=result.usage,
            refused=False,
        )

    # ---------- 状态 ----------

    def status(self) -> dict[str, object]:
        llm_ok, llm_message = self.backend.health()
        if self.dify is not None:
            retrieval_ok, retrieval_message = self.dify.available()
        else:
            assert self.index is not None
            retrieval_ok = True
            retrieval_message = (
                f"本地索引 {len(self.index.chunks)} 个片段"
                if self.index.chunks
                else "本地索引为空，请先上传文档并重建"
            )
        return {
            "场景": f"{self.scene.name}（{self.scene.scene_id}）",
            "生成后端": f"{'✅' if llm_ok else '❌'} {self.backend.name}：{llm_message}",
            "检索后端": f"{'✅' if retrieval_ok else '❌'} "
            f"{self.settings.resolved_retrieval_backend}：{retrieval_message}",
            "索引构建时间": str((self.index.meta or {}).get("built_at", "无"))
            if self.index
            else "无",
            "文档数": len(list_documents(self.scene.kb_dir)),
        }

    def export_scene_card(self) -> str:
        """导出场景定义，可直接粘进方案书"创新场景定义说明"。"""
        scene = self.scene
        lines = [
            f"# 场景定义：{scene.name}",
            "",
            f"- 场景 ID：`{scene.scene_id}`",
            f"- 所属领域：{scene.domain}",
            f"- 助手角色：{scene.persona}",
            "",
            "## 目标用户",
            "",
        ]
        lines += [f"- {user}" for user in scene.users] or ["- （待补充）"]
        lines += ["", "## 需求痛点", ""]
        lines += [f"- {pain}" for pain in scene.pain_points] or ["- （待补充）"]
        lines += ["", "## 典型问题", ""]
        lines += [f"- {question}" for question in scene.sample_questions] or ["- （待补充）"]
        lines += ["", "## 系统提示词", "", "```text", scene.system_prompt.strip(), "```", ""]
        lines += ["## 拒答策略", "", f"- {scene.refusal_hint}", ""]
        return "\n".join(lines)
