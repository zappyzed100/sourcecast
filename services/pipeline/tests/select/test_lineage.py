"""test_lineage.py — Phase 5 DoD: 仕様書§6.2の独立性パターンをnamedテストで固定する"""

from history_radio.select.lineage import (
    EvidenceSource,
    count_independent_families,
    group_source_families,
)


def test_wikipedia_and_its_reprint_site_count_as_one_family() -> None:
    """§6.2: Wikipediaと、そのWikipediaを転載したサイトは1系統。"""
    sources = [
        EvidenceSource(document_id="wikipedia-article"),
        EvidenceSource(
            document_id="mirror-site-copy", derived_from=frozenset({"wikipedia-article"})
        ),
    ]
    assert count_independent_families(sources) == 1


def test_wikipedia_used_with_its_cited_primary_adds_no_extra_family() -> None:
    """§6.2: Wikipediaと脚注の原資料を併用する場合、Wikipedia自体を追加系統に数えない。"""
    sources = [
        EvidenceSource(
            document_id="wikipedia-article",
            cites=frozenset({"primary-doc"}),
            based_solely_on_citations=True,
        ),
        EvidenceSource(document_id="primary-doc"),
    ]
    assert count_independent_families(sources) == 1


def test_multiple_articles_based_solely_on_same_primary_count_as_one() -> None:
    """§6.2: 複数記事が同じ一次資料だけを根拠にしている場合は1系統。"""
    sources = [
        EvidenceSource(
            document_id="article-a",
            cites=frozenset({"primary-doc"}),
            based_solely_on_citations=True,
        ),
        EvidenceSource(
            document_id="article-b",
            cites=frozenset({"primary-doc"}),
            based_solely_on_citations=True,
        ),
        EvidenceSource(document_id="primary-doc"),
    ]
    assert count_independent_families(sources) == 1


def test_duplicate_records_in_same_institution_db_count_as_one() -> None:
    """§6.2: 同一機関の同一データベース内にある重複レコードは1系統。"""
    sources = [
        EvidenceSource(
            document_id="ndl-rec-1", institution_db="ndl-digital", record_signature="bib-123"
        ),
        EvidenceSource(
            document_id="ndl-rec-2", institution_db="ndl-digital", record_signature="bib-123"
        ),
    ]
    assert count_independent_families(sources) == 1


def test_same_db_different_records_stay_independent() -> None:
    sources = [
        EvidenceSource(
            document_id="ndl-rec-1", institution_db="ndl-digital", record_signature="bib-123"
        ),
        EvidenceSource(
            document_id="ndl-rec-2", institution_db="ndl-digital", record_signature="bib-999"
        ),
    ]
    assert count_independent_families(sources) == 2


def test_primary_plus_independent_secondary_count_as_two_families() -> None:
    """§6.2の優先組合せ: 一次資料と、それを独自検討した二次資料は2系統
    （based_solely_on_citations=False の二次資料は独立性を保つ）。"""
    sources = [
        EvidenceSource(document_id="primary-doc"),
        EvidenceSource(
            document_id="scholarly-analysis",
            cites=frozenset({"primary-doc"}),
            based_solely_on_citations=False,  # 独自検討あり
        ),
    ]
    assert count_independent_families(sources) == 2


def test_chained_reprints_collapse_into_the_origin_family() -> None:
    sources = [
        EvidenceSource(document_id="origin"),
        EvidenceSource(document_id="copy-1", derived_from=frozenset({"origin"})),
        EvidenceSource(document_id="copy-of-copy", derived_from=frozenset({"copy-1"})),
        EvidenceSource(document_id="unrelated"),
    ]
    families = group_source_families(sources)
    assert len(families) == 2
    assert frozenset({"origin", "copy-1", "copy-of-copy"}) in families
    assert frozenset({"unrelated"}) in families
