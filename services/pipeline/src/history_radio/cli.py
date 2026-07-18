"""cli.py — 管理画面(React)が使えない時でも状態確認・停止・再開・バックアップができる
コマンドラインツール（development-plan.md Phase 11タスク4）。

管理API（api/main.py）と同じDB（`HISTORY_RADIO_DB_PATH`環境変数・既定
`data/history_radio.sqlite3`）へ直接アクセスする——FastAPIサーバーが落ちていても
このCLI単体で動く（api/db.pyの`get_session_maker()`/`get_db_path()`をそのまま使う）。

停止は`store/jobs.request_cancel()`と同じ「フラグを立てるだけ」の意味論
（`POST /api/v1/jobs/{id}/cancel`と同一）——実際に停止させるのはジョブを実行している
スレッド側で、生きているFastAPIプロセスがあればそちらが拾う。再開は
`POST /api/v1/jobs/{id}/retry`と同じ「新しいjob_idで作り直す」意味論だが、
CLIはバックグラウンドスレッドを持たないため、このプロセス内で同期的に実行し、
完了（成功/失敗）するまで呼び出し元へ結果を返さない。

バックアップはSQLiteの`backup()` API（書き込み中でも一貫性のあるスナップショットを
取れる——単純なファイルコピーだと書き込み最中のtorn readになり得る）でローカルへ
1ファイルを作るだけ——Google Drive/NAS等クラウド先への日次同期はPhase 12の仕事。

呼び出し: `uv run python -m history_radio.cli <サブコマンド>`
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer

from history_radio.api.db import get_db_path, get_session_maker
from history_radio.jobs.runner import run_episode_generation_job
from history_radio.store.episodes import list_episodes
from history_radio.store.jobs import (
    JobAlreadyTerminalError,
    JobNotFoundError,
    create_job,
    get_job,
    list_jobs,
    request_cancel,
)

# Windowsのcp932コンソール対策(日本語出力の文字化け防止 — scripts/repo_scan.pyの
# reconfigure_stdio()と同じ理由。scripts/配下ではないためここへ直接書く)。
# isinstance判定はbasedpyright strict対応(TextIOにはreconfigure()が無く、
# 実際の標準ストリームの型であるTextIOWrapperにのみ存在する)。
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper) and _stream.encoding.lower() != "utf-8":
        _stream.reconfigure(encoding="utf-8")

app = typer.Typer(
    help="history-radio 運用CLI（管理画面が使えない時の復旧操作）", no_args_is_help=True
)

_RETRYABLE_JOB_STATUSES = ("failed", "blocked", "cancelled")


@app.command()
def status() -> None:
    """ジョブとエピソードの現在の状態を一覧表示する。"""
    session_maker = get_session_maker()
    with session_maker() as session:
        jobs = list_jobs(session)
        episodes = list_episodes(session)

    typer.echo(f"ジョブ: {len(jobs)}件")
    for job in jobs:
        progress_pct = round(job.progress * 100)
        detail = f"  [{job.status}] {job.job_id} episode={job.episode_id} progress={progress_pct}%"
        if job.cancel_requested:
            detail += " cancel_requested=true"
        if job.error:
            detail += f" error={job.error}"
        typer.echo(detail)

    typer.echo(f"エピソード: {len(episodes)}件")
    for episode in episodes:
        typer.echo(f"  [{episode.state}] {episode.episode_id} {episode.title}")


@app.command()
def stop(job_id: str) -> None:
    """実行中/待機中のジョブへキャンセルを要求する（`POST /jobs/{id}/cancel`と同じ意味論）。"""
    session_maker = get_session_maker()
    with session_maker() as session:
        try:
            job = request_cancel(session, job_id)
        except (JobNotFoundError, JobAlreadyTerminalError) as exc:
            typer.echo(f"エラー: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"キャンセルを要求した: {job.job_id}（status={job.status}）")


@app.command()
def resume(job_id: str) -> None:
    """終端の失敗状態（failed/blocked/cancelled）のジョブを再実行する
    （`POST /jobs/{id}/retry`と同じ意味論）——このCLIプロセス内で完了まで同期的に実行する。
    """
    session_maker = get_session_maker()
    with session_maker() as session:
        try:
            original = get_job(session, job_id)
        except JobNotFoundError as exc:
            typer.echo(f"エラー: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if original.status not in _RETRYABLE_JOB_STATUSES:
            typer.echo(
                f"エラー: 終端の失敗状態のジョブのみ再実行できる（現在: {original.status}）",
                err=True,
            )
            raise typer.Exit(code=1)
        if original.episode_id is None:
            typer.echo("エラー: episode_idの無いジョブは再実行できない", err=True)
            raise typer.Exit(code=1)
        episode_id = original.episode_id
        new_job = create_job(
            session,
            job_id=f"job-{episode_id}-{uuid4().hex[:8]}",
            episode_id=episode_id,
            kind=original.kind,
            retry_of=original.job_id,
        )

    typer.echo(f"再実行を開始した: {new_job.job_id}")
    run_episode_generation_job(session_maker, job_id=new_job.job_id, episode_id=episode_id)

    with session_maker() as session:
        finished = get_job(session, new_job.job_id)
    typer.echo(f"完了: {finished.job_id}（status={finished.status}）")
    if finished.status != "succeeded":
        raise typer.Exit(code=1)


@app.command()
def backup(
    out_dir: Path = typer.Option(Path("backups"), help="バックアップ先ディレクトリ"),
) -> None:
    """SQLiteのライブバックアップを1ファイル作る（書き込み中でも安全な`sqlite3.Connection.backup()`を使う）。"""
    src_path = get_db_path()
    if not src_path.exists():
        typer.echo(f"エラー: DBファイルが無い: {src_path}", err=True)
        raise typer.Exit(code=1)

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_path = out_dir / f"{src_path.stem}-{timestamp}{src_path.suffix}"

    src_conn = sqlite3.connect(src_path)
    try:
        dest_conn = sqlite3.connect(dest_path)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    typer.echo(f"バックアップ完了: {dest_path}")


if __name__ == "__main__":
    app()
