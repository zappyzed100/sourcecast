# llm_quality_probe.py — 無料LLMの出力品質を実測する検証ハーネス（仕様書§8.1の回帰前段）
"""「APIで十分な質の文章が出せるか」を実測する使い捨てでない検証ツール。

2タスク×モデルで実行し、Phase 6の検証器（extraction/validator）へそのまま通す:

  1. extraction — §8.2のJSONを返させ、スキーマ適合・根拠抜粋の完全一致・
     オフセット正確性を機械判定する
  2. script — 主張台帳を与えて§9.1の7段構成台本JSONを返させ、
     validate_script（claim_id結び付け・禁止表現・構成）を通す

日本語の自然さは機械判定しない——出力全文を表示するので人間が読んで判断する
（§8.1「日本語回帰テスト」の判断材料。合格したモデルだけ model_registry.yaml の
japanese_regression_passed を true にする）。

使い方:
  set OPENROUTER_API_KEY=sk-...   (PowerShell: $env:OPENROUTER_API_KEY="sk-...")
  uv run scripts/llm_quality_probe.py                     # レジストリの全モデル
  uv run scripts/llm_quality_probe.py --model vendor/x:free --runs 3 --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "pipeline" / "src"))

from history_radio.ingest.schema import (  # noqa: E402
    EvidenceLocator,
    FetchedDocument,
    FetchResponseInfo,
    RightsEvidence,
)
from history_radio.llm.extraction import (  # noqa: E402
    ExtractionValidationError,
    parse_extraction,
)
from history_radio.llm.ledger import ClaimInput, build_claim_ledger  # noqa: E402
from history_radio.llm.openrouter import OpenRouterCaller, OpenRouterError  # noqa: E402
from history_radio.script.schema import Script  # noqa: E402
from history_radio.script.validator import ScriptValidationError, validate_script  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---- 検証素材（PD事実に基づく自作テキスト。実行のたびに変えない——比較可能性のため）----

SOURCE_TEXT = (
    "明治五年九月十二日（1872年10月14日）、新橋停車場と横浜停車場を結ぶ日本初の鉄道が正式開業した。"
    "開業式には明治天皇が臨席し、勅語を述べた。翌日から旅客営業が始まり、一日九往復が運行された。"
    "全線約二十九キロメートルの所要時間は五十三分であった。"
    "建設は英国人技師エドモンド・モレルの指導の下で進められたが、モレルは開業を見ずに前年病没した。"
    "客車は上等・中等・下等の三等級に分かれ、下等の運賃は三十七銭五厘であった。"
)

EXTRACTION_PROMPT_VERSION = "probe-extraction-v1"
EXTRACTION_PROMPT = (
    "あなたは歴史資料から事実を抽出する調査員です。次の資料本文から確認可能な事実を"
    "3〜5件抽出し、指定のJSONだけを出力してください。"
    "JSON以外の文字（説明・マークダウン記法）を含めてはいけません。\n\n"
    "厳守事項:\n"
    "- evidence_quote は資料本文から一字一句変えずに抜き出すこと（要約・言い換え禁止）\n"
    "- locator の start_offset / end_offset は資料本文の文字位置（0始まり）で、"
    "本文[start:end] == evidence_quote になること\n"
    "- キーは summary_ja, facts, people, places, dates, uncertainties のみ。"
    "facts の各要素は claim, evidence_quote, source_id, locator のみ。"
    "locator は start_offset, end_offset のみ\n"
    '- source_id は "probe-source" とすること\n\n'
    f"資料本文:\n{SOURCE_TEXT}"
)

SCRIPT_PROMPT_VERSION = "probe-script-v1"
_LEDGER_FOR_PROMPT = [
    {"claim_id": "claim-001", "text": "1872年10月14日に新橋・横浜間で日本初の鉄道が正式開業した"},
    {"claim_id": "claim-002", "text": "開業当時の全線所要時間は約53分だった"},
    {
        "claim_id": "claim-003",
        "text": "英国人技師エドモンド・モレルが建設を指導したが開業前年に病没した",
    },
]
_SCRIPT_OUTPUT_SHAPE = (
    '{"schema_version": 1, "episode_id": "probe-ep-1", "sections": '
    '[{"kind": "hook", "sentences": '
    '[{"text": "...", "kind": "presentation", "claim_id": null}]}, ...]}'
)
SCRIPT_PROMPT = (
    "あなたは歴史番組の台本作家です。以下の主張台帳だけを事実の根拠として、"
    "7段構成の台本をJSONで出力してください。JSON以外の文字を含めてはいけません。\n\n"
    "厳守事項:\n"
    '- 外部検証可能な事実文は必ず kind="claim" とし、主張台帳の claim_id を付けること\n'
    '- 台帳にない事実を追加しないこと。演出・つなぎの文は kind="presentation" / "transition"\n'
    "- sections は次の順で7個: hook, setting, development, twist, modern_link, "
    "uncertainty, sources\n"
    "- 各文はずんだもん口調（「〜のだ」「〜なのだ」）。全体で600〜900字\n"
    f"- 出力の形: {_SCRIPT_OUTPUT_SHAPE}\n\n"
    f"主張台帳:\n{json.dumps(_LEDGER_FOR_PROMPT, ensure_ascii=False, indent=1)}"
)


def _probe_document() -> FetchedDocument:
    return FetchedDocument.model_validate(
        {
            "document_id": "probe-doc-1",
            "source_id": "probe-source",
            "original_url": "https://example.org/probe",
            "canonical_url": "https://example.org/probe",
            "revision_id": "probe-1",
            "title": "日本の鉄道開業（検証用）",
            "creator": "probe",
            "fetched_at": datetime.now(timezone.utc),
            "full_text": SOURCE_TEXT,
            "locator": EvidenceLocator(),
            "language": "ja",
            "rights": RightsEvidence.model_validate(
                {
                    "license_name": "検証用自作テキスト",
                    "normalized_license_id": "cc0",
                    "use_class": "A",
                    "rights_statement_text": "検証用",
                    "rights_page_url": "https://example.org/probe",
                }
            ),
            "permalink": "https://example.org/probe",
            "content_hash": "sha256:probe",
            "response": FetchResponseInfo(
                fetch_method="api", http_status=200, robots_txt_allowed=True, terms_checked=True
            ),
            "storage_permission": "granted",
            "publication_permission": "granted",
        }
    )


def _probe_ledger() -> list[Any]:
    return build_claim_ledger(
        [
            ClaimInput.model_validate(
                {
                    "claim_id": entry["claim_id"],
                    "text": entry["text"],
                    "evidence_ids": ["evidence-probe"],
                    "source_family_ids": ["family-a", "family-b"],
                    "reliability_score": 0.9,
                    "qualification": "断定",
                }
            )
            for entry in _LEDGER_FOR_PROMPT
        ]
    )


def _strip_fences(text: str) -> tuple[str, bool]:
    """```json フェンスで包まれた出力を剥がす（剥がしたかを品質指標として記録）。"""
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if match:
        return match.group(1), True
    return stripped, False


def run_extraction_task(output_text: str) -> dict[str, Any]:
    doc = _probe_document()
    body, had_fences = _strip_fences(output_text)
    result: dict[str, Any] = {"had_markdown_fences": had_fences}
    try:
        extraction = parse_extraction(body)
    except ExtractionValidationError as exc:
        result["schema_ok"] = False
        result["error"] = str(exc)[:300]
        return result
    result["schema_ok"] = True
    result["fact_count"] = len(extraction.facts)
    text = SOURCE_TEXT
    exact = sum(1 for f in extraction.facts if f.evidence_quote in text)
    offsets = sum(
        1
        for f in extraction.facts
        if f.locator.end_offset <= len(text)
        and text[f.locator.start_offset : f.locator.end_offset] == f.evidence_quote
    )
    result["quotes_exact_substring"] = f"{exact}/{len(extraction.facts)}"
    result["offsets_correct"] = f"{offsets}/{len(extraction.facts)}"
    result["summary_ja"] = extraction.summary_ja
    _ = doc  # 将来: attach_provenanceまで通す
    return result


def run_script_task(output_text: str) -> dict[str, Any]:
    body, had_fences = _strip_fences(output_text)
    result: dict[str, Any] = {"had_markdown_fences": had_fences}
    try:
        script = Script.model_validate_json(body)
    except Exception as exc:  # ValidationError含む。probeは報告が仕事なので握らず記録する
        result["schema_ok"] = False
        result["error"] = str(exc)[:300]
        return result
    result["schema_ok"] = True
    try:
        validate_script(script, _probe_ledger())
        result["validator_ok"] = True
    except ScriptValidationError as exc:
        result["validator_ok"] = False
        result["problems"] = exc.problems[:5]
    total_chars = sum(len(s.text) for sec in script.sections for s in sec.sentences)
    result["total_chars"] = total_chars
    result["script_text"] = "\n".join(
        f"[{sec.kind}] " + " ".join(s.text for s in sec.sentences) for sec in script.sections
    )
    return result


def registry_model_ids() -> list[str]:
    raw = yaml.safe_load((REPO_ROOT / "config" / "model_registry.yaml").read_text("utf-8"))
    return [m["model_id"] for m in raw["models"]]


def _call_with_retry(caller, *, model_id: str, prompt: str, retries: int = 3):
    """無料枠の一時的な429は数十秒で解けることが多い——リトライしてから諦める。"""
    last_error = None
    for attempt in range(retries + 1):
        try:
            return caller(model_id=model_id, prompt=prompt)
        except OpenRouterError as exc:
            last_error = exc
            if "429" not in str(exc) or attempt == retries:
                raise
            wait = 30 * (attempt + 1)
            print(f"  (429: {wait}秒待って再試行 {attempt + 1}/{retries})")
            time.sleep(wait)
    raise last_error  # 到達しない（型のため）


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # Windowsのcp932コンソール対策
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="無料LLMの出力品質を実測する")
    ap.add_argument(
        "--model", action="append", help="対象モデルID（複数可。省略時はレジストリ全件）"
    )
    ap.add_argument("--runs", type=int, default=1, help="各タスクの実行回数（安定性確認用）")
    ap.add_argument("--task", choices=["extraction", "script", "all"], default="all")
    ap.add_argument("--verbose", action="store_true", help="生成全文を表示する")
    args = ap.parse_args()

    models = args.model or registry_model_ids()
    caller = OpenRouterCaller.from_env(httpx.Client())

    tasks: list[tuple[str, str, Any]] = []
    if args.task in ("extraction", "all"):
        tasks.append(("extraction", EXTRACTION_PROMPT, run_extraction_task))
    if args.task in ("script", "all"):
        tasks.append(("script", SCRIPT_PROMPT, run_script_task))

    for model_id in models:
        for task_name, prompt, evaluate in tasks:
            for run_index in range(args.runs):
                label = f"{model_id} / {task_name} / run{run_index + 1}"
                try:
                    llm = _call_with_retry(caller, model_id=model_id, prompt=prompt)
                except OpenRouterError as exc:
                    print(f"\n=== {label}: 呼び出し失敗 ===\n{exc}")
                    continue
                report = evaluate(llm.output_text)
                print(f"\n=== {label} ===")
                print(f"tokens: prompt={llm.prompt_tokens} completion={llm.completion_tokens}")
                for key, value in report.items():
                    if key in ("script_text", "summary_ja") and not args.verbose:
                        continue
                    print(f"{key}: {value}")
                if args.verbose:
                    print("--- 生成全文 ---")
                    print(llm.output_text)
    print(
        "\n判定基準の目安: schema_ok=100%・quotes_exact_substring=全件・validator_ok=true が"
        "自動採用の最低線。日本語の自然さは--verboseで全文を読んで判断し、合格モデルのみ "
        "config/model_registry.yaml の japanese_regression_passed を true にする（§8.1）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
