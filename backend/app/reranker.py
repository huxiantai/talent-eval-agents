from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from dashscope.rerank import TextReRank

from app.config import Settings, get_settings


class Reranker(Protocol):
    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> list[dict]:
        ...


@dataclass(frozen=True)
class RerankHit:
    index: int
    score: float


class DashScopeReranker:
    def __init__(self, *, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> list[RerankHit]:
        response = TextReRank.call(
            model=self.model,
            query=query,
            documents=list(documents),
            top_n=top_n,
            api_key=self.api_key,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"rerank failed: status={response.status_code} "
                f"code={getattr(response, 'code', None)} message={getattr(response, 'message', None)}"
            )
        return [
            RerankHit(index=item.index, score=float(item.relevance_score))
            for item in response.output.results
        ]


def get_reranker(settings: Settings | None = None) -> DashScopeReranker | None:
    value = settings or get_settings()
    if not value.dashscope_api_key or value.dashscope_api_key == "请用户自行填写":
        return None
    return DashScopeReranker(model=value.rerank_model, api_key=value.dashscope_api_key)
