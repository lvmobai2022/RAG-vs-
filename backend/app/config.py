import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# 避免 huggingface / pip 等工具把模型缓存写到系统盘（C盘），统一放到项目所在盘的缓存目录。
os.environ.setdefault("HF_HOME", os.path.abspath("./data/hf_cache"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# 交叉编码器下载时若系统/用户环境误设了不可用的 HF_ENDPOINT，会导致加载失败；默认清掉坏镜像。
_bad_endpoint = os.environ.get("HF_ENDPOINT", "").rstrip("/")
if _bad_endpoint in {"https://hf-mirror.com", "http://hf-mirror.com"}:
    os.environ.pop("HF_ENDPOINT", None)
# 如果直连 huggingface.co 不稳定，可以在 .env 或系统环境变量里设置可用镜像。
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")  # 关闭 chromadb 的匿名遥测，避免报错刷屏


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    rag_top_k: int = 5
    rag_top_k_upgraded: int = 8  # D 组用更大 Top-K，提升要点覆盖
    degraded_top_k: int = 5
    degraded_noise_ratio: float = 0.6
    rag_chunk_chars: int = 800
    rag_chunk_chars_upgraded: int = 1400  # D 组喂更长摘要，减少漏点

    # D 组重排：默认向量余弦（本评测下正确性更优）；可改 cross-encoder / auto
    rerank_enabled: bool = True
    rerank_backend: str = "embedding"  # embedding | cross-encoder | auto
    rerank_model: str = "BAAI/bge-reranker-base"
    rerank_candidates: int = 24  # 送入重排的候选数

    # 拒答阈门（可解释规则，不追求医学级最优阈值）
    refusal_min_sources: int = 3
    refusal_max_best_distance: float = 11.0  # 最佳命中距离大于此值视为相似度过低
    refusal_max_avg_distance: float = 12.5  # Top-K 平均距离大于此值视为整体不相关

    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    chroma_persist_dir: str = "./data/chroma"

    database_url: str = "sqlite:///./data/app.db"


settings = Settings()
