"""test_cache.py — Phase 6 DoD: 同じ入力と版でキャッシュが使われ二重課金しないことを固定する"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from history_radio.llm.cache import LlmResult, cached_llm_call
from history_radio.store.db import create_sqlite_engine, session_factory
from history_radio.store.orm import Base, LlmRunRow


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    eng: Engine = create_sqlite_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    with session_factory(eng)() as s:
        yield s
    eng.dispose()


class CountingCaller:
    """呼び出し回数を数えるフェイクLLM。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *, model_id: str, prompt: str) -> LlmResult:
        self.calls += 1
        return LlmResult(
            output_text=f"応答({self.calls}回目): {prompt[:10]}",
            prompt_tokens=100,
            completion_tokens=50,
        )


def test_same_input_and_version_uses_cache_without_second_call(session: Session) -> None:
    """Phase 6 DoD: 同じ入力と版では2回目の実LLM呼び出しが発生しない。"""
    caller = CountingCaller()
    out1, hit1 = cached_llm_call(
        session,
        model_id="vendor/model:free",
        prompt_version="v1",
        prompt="要約して: 鉄道開業",
        caller=caller,
    )
    out2, hit2 = cached_llm_call(
        session,
        model_id="vendor/model:free",
        prompt_version="v1",
        prompt="要約して: 鉄道開業",
        caller=caller,
    )
    assert caller.calls == 1  # 二重課金呼び出しをしない
    assert (hit1, hit2) == (False, True)
    assert out1 == out2


def test_different_prompt_version_re_executes(session: Session) -> None:
    """プロンプト版が変われば同じ入力でも再実行される（版=出力契約の変更）。"""
    caller = CountingCaller()
    cached_llm_call(
        session, model_id="m/a:free", prompt_version="v1", prompt="同じ入力", caller=caller
    )
    cached_llm_call(
        session, model_id="m/a:free", prompt_version="v2", prompt="同じ入力", caller=caller
    )
    assert caller.calls == 2


def test_different_model_re_executes(session: Session) -> None:
    caller = CountingCaller()
    cached_llm_call(
        session, model_id="m/a:free", prompt_version="v1", prompt="同じ入力", caller=caller
    )
    cached_llm_call(
        session, model_id="m/b:free", prompt_version="v1", prompt="同じ入力", caller=caller
    )
    assert caller.calls == 2


def test_run_record_stores_hashes_and_usage(session: Session) -> None:
    """§8.1: プロンプト版・モデルID・入出力ハッシュ・使用量が保存される。"""
    cached_llm_call(
        session,
        model_id="vendor/model:free",
        prompt_version="v1",
        prompt="記録確認",
        caller=CountingCaller(),
    )
    row = session.execute(select(LlmRunRow)).scalar_one()
    assert row.model_id == "vendor/model:free"
    assert row.prompt_version == "v1"
    assert row.input_hash.startswith("sha256:")
    assert row.output_hash.startswith("sha256:")
    assert row.prompt_tokens == 100
    assert row.completion_tokens == 50
