"""cache.py — LLM実行の記録と同一入力キャッシュ（仕様書§8.1・Phase 6）。

「生成結果、プロンプト版、モデルID、入力ハッシュ、出力ハッシュ、使用量を保存する」
「同じ入力と版ではキャッシュが使われ、二重課金呼び出しをしない」を実装する。

実際のLLM呼び出しは `caller` として注入する（OpenRouterクライアントの配線は
APIキー到着後——それまでもこの記録・キャッシュ層はフェイクcallerでテストできる）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from history_radio.store.orm import LlmRunRow


@dataclass(frozen=True, slots=True)
class LlmResult:
    """caller が返す1回分の生成結果。"""

    output_text: str
    prompt_tokens: int
    completion_tokens: int


class LlmCaller(Protocol):
    """実LLM呼び出しの抽象（テストはフェイク、本番はOpenRouterクライアント）。"""

    def __call__(self, *, model_id: str, prompt: str) -> LlmResult: ...


def input_hash(prompt: str) -> str:
    return "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def cached_llm_call(
    session: Session,
    *,
    model_id: str,
    prompt_version: str,
    prompt: str,
    caller: LlmCaller,
    now: datetime | None = None,
) -> tuple[str, bool]:
    """(出力テキスト, キャッシュヒットしたか) を返す。

    同じ (model_id, prompt_version, 入力ハッシュ) の実行記録があれば caller を
    呼ばずに保存済み出力を返す——プロンプト版が変われば同じ入力でも再実行される
    （版の変更は出力契約の変更 — §8.1「プロンプトテンプレート版」を保存する理由）。
    """
    ihash = input_hash(prompt)
    existing = session.execute(
        select(LlmRunRow).where(
            LlmRunRow.model_id == model_id,
            LlmRunRow.prompt_version == prompt_version,
            LlmRunRow.input_hash == ihash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.output_text, True

    result = caller(model_id=model_id, prompt=prompt)
    created_at = now or datetime.now(timezone.utc)
    session.add(
        LlmRunRow(
            run_id=f"llm-{model_id.replace('/', '-')}-{prompt_version}-{ihash[-16:]}",
            model_id=model_id,
            prompt_version=prompt_version,
            input_hash=ihash,
            output_hash="sha256:" + hashlib.sha256(result.output_text.encode()).hexdigest(),
            output_text=result.output_text,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            created_at=created_at,
        )
    )
    session.commit()
    return result.output_text, False
