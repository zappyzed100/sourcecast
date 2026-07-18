"""runner.py — エピソード生成ジョブを工程単位で実行する（仕様書§14・Phase 11タスク2）。

実際のLLM台本生成・VOICEVOX音声合成・FFmpeg動画生成（Phase 6〜8）はまだこのジョブへ
接続されていない——ここで実際に行うのはエピソードの状態遷移そのもの
（domain/episode_state.pyのtransition()をstore/episodes.update_episode_state()経由で
呼ぶ、本物の永続化を伴う遷移）であり、各段階の重い生成処理は各段階を実際に接続する
後続フェーズの仕事（本関数はプレースホルダーの`step_delay_seconds`待機で「時間のかかる
処理」を表現するだけ——公開直前の自動検査ゲート評価もここでは行わない/捏造しない）。

FastAPIのイベントループとは独立したバックグラウンドスレッドから呼ぶ想定
（`threading.Thread(target=run_episode_generation_job, ...)`）——本関数自体は
同期関数で、`session_maker`から自分専用のセッションを作る（リクエストスコープの
セッションを間借りしない。SQLiteはWAL+単一writer前提 — store/db.py）。

キャンセルは共有メモリのフラグではなくDB列（`jobs.cancel_requested`）で行う
——ブラウザ再読込やサーバー内の別リクエストからでも同じ行を見て判定できる
（プロセス内の状態を持ち回らない設計 — Phase 11タスク2 DoD「再読込後も正しい状態へ
復帰する」を裏で支える）。
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from history_radio.domain.episode_state import (
    FAILURE_STATES,
    EpisodeState,
    remaining_forward_states,
)
from history_radio.store.episodes import get_episode, update_episode_state
from history_radio.store.jobs import (
    append_job_log,
    is_cancel_requested,
    mark_cancelled,
    mark_failed,
    mark_running,
    mark_succeeded,
    update_progress,
)

DEFAULT_STEP_DELAY_SECONDS = 1.0


def _resolve_default_step_delay_seconds() -> float:
    """`HISTORY_RADIO_JOB_STEP_DELAY_SECONDS`環境変数（未指定時は`DEFAULT_STEP_DELAY_SECONDS`）。

    `HISTORY_RADIO_DB_PATH`（api/db.py）と同じ「環境変数で上書き可能・呼び出しのたびに
    再解決」方式——API層のテストが本物のHTTPエンドポイント経由でジョブを起動しても、
    実待機（既定1秒×最大7工程）でテストを遅くしたりtmp_pathの片付け後に
    バックグラウンドスレッドが残り続けたりしないよう、0を注入できるようにする
    （services/pipeline/tests/api/test_main.pyのclient fixtureが設定する）。
    """
    raw = os.environ.get("HISTORY_RADIO_JOB_STEP_DELAY_SECONDS")
    return float(raw) if raw else DEFAULT_STEP_DELAY_SECONDS


def run_episode_generation_job(
    session_maker: sessionmaker[Session],
    *,
    job_id: str,
    episode_id: str,
    step_delay_seconds: float | None = None,
    on_before_step: Callable[[EpisodeState], None] | None = None,
) -> None:
    """`job_id`を実行する。必ずジョブを終端状態（succeeded/failed/cancelled）で終える
    ——予期しない例外もfailedへ変換して記録し、runningのまま取り残さない。

    `step_delay_seconds`を省略すると`_resolve_default_step_delay_seconds()`を都度
    再解決する（呼び出し元が明示的に0等を渡した場合はそちらを優先する——
    services/pipeline/tests/jobs/test_runner.pyのように決定的なテストで使う）。

    `on_before_step`はテスト専用フック（各状態へ遷移する直前に呼ばれる）——
    テストが決定的にジョブを一時停止させ、キャンセル要求のタイミングを制御するために使う
    （テストではsleepの代わりにthreading.Eventで同期する）。
    """
    delay = (
        step_delay_seconds
        if step_delay_seconds is not None
        else _resolve_default_step_delay_seconds()
    )
    session = session_maker()
    try:
        if is_cancel_requested(session, job_id):
            mark_cancelled(session, job_id)
            append_job_log(session, job_id, level="info", message="開始前にキャンセルされた")
            return

        episode = get_episode(session, episode_id)
        if episode.state in FAILURE_STATES:
            raise RuntimeError(
                f"エピソードは終端の失敗状態（{episode.state}）にあるため生成ジョブを実行できない"
            )

        mark_running(session, job_id)
        append_job_log(
            session, job_id, level="info", message=f"開始（現在の状態: {episode.state}）"
        )

        steps = remaining_forward_states(episode.state)
        total = len(steps) or 1
        for done, target_state in enumerate(steps):
            if is_cancel_requested(session, job_id):
                mark_cancelled(session, job_id)
                append_job_log(
                    session,
                    job_id,
                    level="info",
                    message=f"キャンセルされた（{episode.state}到達時点で中断）",
                )
                return

            if on_before_step is not None:
                on_before_step(target_state)

            # フック（テストの一時停止点）から戻った直後にも再確認する——一時停止中に
            # キャンセルが要求された場合、この段への遷移そのものを行わずに止める。
            if is_cancel_requested(session, job_id):
                mark_cancelled(session, job_id)
                append_job_log(
                    session,
                    job_id,
                    level="info",
                    message=f"キャンセルされた（{episode.state}到達時点で中断・{target_state}へは未遷移）",
                )
                return

            time.sleep(delay)

            episode = update_episode_state(
                session,
                episode_id=episode_id,
                expected_revision=episode.revision,
                new_state=target_state,
            )
            append_job_log(session, job_id, level="info", message=f"状態 {target_state} へ遷移")
            update_progress(session, job_id, progress=(done + 1) / total)

        mark_succeeded(session, job_id)
        append_job_log(
            session,
            job_id,
            level="info",
            message="publish_readyまで到達（自動検査ゲート評価は未接続——承認前に別途必要）",
        )
    except Exception as exc:
        session.rollback()
        mark_failed(session, job_id, error=str(exc))
        append_job_log(session, job_id, level="error", message=f"失敗: {exc}")
    finally:
        session.close()


__all__ = ["DEFAULT_STEP_DELAY_SECONDS", "run_episode_generation_job"]
