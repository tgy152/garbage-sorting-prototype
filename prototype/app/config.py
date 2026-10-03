"""集中配置：全部通过 .env / 环境变量注入，便于在方案书里写"可复现的实验环境"。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_mode: str = "mock"
    scene_id: str = "waste_sorting"

    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.3
    llm_timeout: int = 60

    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""

    dify_api_base: str = "http://localhost/v1"
    dify_api_key: str = ""
    dify_dataset_id: str = ""

    # ---------- 视觉识别 ----------
    # VISION_BACKEND 留空时跟随 APP_MODE：mock -> mock，其余 -> multimodal
    vision_backend: str = ""
    vision_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    vision_api_key: str = ""
    vision_model: str = "qwen-vl-max"
    vision_timeout: int = 90
    # 默认地区分类标准（影响类别名称，如上海为"湿垃圾/干垃圾"）
    region: str = "national"

    top_k: int = 4
    chunk_size: int = 500
    chunk_overlap: int = 80
    # 片段地板分：低于此分数的片段直接丢弃
    score_threshold: float = 0.08
    # 拒答门槛：最高分达到此值即放行（用 scripts/score_sweep.py 标定）
    refuse_min_score: float = 0.09
    # 弱相关下限：低于拒答门槛时，需同时命中领域词且不低于本值才放行
    weak_min_score: float = 0.05
    # 相关度门控：rule（默认，离线可用）/ llm（额外调用一次模型判定）/ off
    relevance_gate: str = "rule"

    gradio_server_name: str = "127.0.0.1"
    gradio_server_port: int = 7860
    gradio_share: bool = False
    # 启动后自动用默认浏览器打开页面（双击启动脚本时很方便）
    gradio_inbrowser: bool = True
    # 公网访问时的登录保护（两项都填才生效）
    gradio_auth_user: str = ""
    gradio_auth_password: str = ""

    # ---------- 派生路径 ----------

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def scenes_dir(self) -> Path:
        return PROJECT_ROOT / "scenes"

    @property
    def knowledge_dir(self) -> Path:
        return PROJECT_ROOT / "knowledge"

    @property
    def rules_dir(self) -> Path:
        return PROJECT_ROOT / "rules"

    @property
    def samples_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "samples"

    @property
    def vision_scenarios_path(self) -> Path:
        return PROJECT_ROOT / "data" / "vision_scenarios.yaml"

    @property
    def index_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "index"

    @property
    def export_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "exports"

    @property
    def eval_out_dir(self) -> Path:
        return PROJECT_ROOT / "eval" / "out"

    # ---------- 模式解析 ----------

    @property
    def resolved_llm_backend(self) -> str:
        """mock -> mock；direct -> openai；dify -> dify。"""
        mapping = {"mock": "mock", "direct": "openai", "dify": "dify"}
        mode = (self.app_mode or "mock").strip().lower()
        if mode not in mapping:
            raise ValueError(
                f"APP_MODE 只能是 {sorted(mapping)}，当前为 {self.app_mode!r}"
            )
        return mapping[mode]

    @property
    def resolved_retrieval_backend(self) -> str:
        """mock/direct 用本地索引，dify 模式用 Dify 数据集检索。"""
        return "dify" if (self.app_mode or "").strip().lower() == "dify" else "local"

    @property
    def resolved_vision_backend(self) -> str:
        """显式配置优先；否则 mock 模式用预置场景，其余用多模态模型。"""
        if self.vision_backend.strip():
            return self.vision_backend.strip().lower()
        return "mock" if (self.app_mode or "").strip().lower() == "mock" else "multimodal"

    @property
    def embedding_enabled(self) -> bool:
        return bool(self.embedding_base_url and self.embedding_api_key and self.embedding_model)

    @property
    def gradio_auth(self) -> tuple[str, str] | None:
        """配置了用户名与密码时返回认证元组，否则返回 None。"""
        if self.gradio_auth_user and self.gradio_auth_password:
            return (self.gradio_auth_user, self.gradio_auth_password)
        return None

    @property
    def auth_enabled(self) -> bool:
        return self.gradio_auth is not None

    def ensure_dirs(self) -> None:
        for path in (self.index_dir, self.export_dir, self.eval_out_dir):
            path.mkdir(parents=True, exist_ok=True)

    def public_summary(self) -> dict[str, object]:
        """给界面/附录用的配置快照，自动隐藏密钥。"""
        return {
            "APP_MODE": self.app_mode,
            "SCENE_ID": self.scene_id,
            "LLM 后端": self.resolved_llm_backend,
            "LLM 模型": self.llm_model if self.resolved_llm_backend != "mock" else "（mock，不调用）",
            "检索后端": self.resolved_retrieval_backend,
            "视觉后端": self.resolved_vision_backend,
            "地区标准": self.region,
            "向量化": "已启用 " + self.embedding_model if self.embedding_enabled else "未启用（TF-IDF 兜底）",
            "TOP_K": self.top_k,
            "CHUNK_SIZE": self.chunk_size,
            "CHUNK_OVERLAP": self.chunk_overlap,
            "SCORE_THRESHOLD(地板分)": self.score_threshold,
            "REFUSE_MIN_SCORE": self.refuse_min_score,
            "WEAK_MIN_SCORE": self.weak_min_score,
            "RELEVANCE_GATE": self.relevance_gate,
            "LLM_API_KEY": "已配置" if self.llm_api_key else "未配置",
            "DIFY_API_KEY": "已配置" if self.dify_api_key else "未配置",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
