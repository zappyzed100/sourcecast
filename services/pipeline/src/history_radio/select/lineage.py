"""lineage.py — 出典の系統判定（仕様書§6.2）。

「2資料以上」はURL数ではなく**情報の系統数**で数える。§6.2の4パターンを
union-find（素集合データ構造）の併合規則に写す:

1. 転載: AがBの転載（derived_from）なら同一系統。
2. 脚注原資料の併用: Wikipedia等の二次資料Wが一次資料Pを脚注引用しており、
   WとPを併用する場合、Wを追加の独立系統として数えない（based_solely_on_citations
   が真の資料は、引用先と同一系統に併合される）。
3. 同一一次資料のみ根拠: 複数記事が同じ一次資料だけを根拠にしていれば1系統
   （2.の規則で同じ一次資料へ併合されることで実現される）。
4. 同一機関の同一DB内重複レコード: institution_db と record_signature が
   一致すれば1系統。

すべて純粋関数——I/Oなし。判定の入力（derived_from・cites等）は収集メタデータと
人手レビューが埋める（機械が全自動で系統を推定できる、とは主張しない——§6.2の
規則を「与えられた関係の下で正しく数える」のがこの module の責務）。
"""

from __future__ import annotations

from pydantic import Field

from history_radio.domain.base import SchemaModel


class EvidenceSource(SchemaModel):
    """系統判定の入力1件（収集済み資料の系統関連メタデータ）。"""

    document_id: str = Field(min_length=1)
    # この資料がどの資料の転載か（転載元のdocument_id。転載でなければ空）
    derived_from: frozenset[str] = frozenset()
    # この資料が根拠として引用する資料（脚注の一次資料等のdocument_id）
    cites: frozenset[str] = frozenset()
    # 真なら「引用先だけを根拠にした資料」（Wikipedia型の二次資料等）——
    # 引用先と同一系統に併合され、追加の独立系統として数えない（§6.2）
    based_solely_on_citations: bool = False
    # 同一機関の同一データベース識別子（例: "ndl-digital"）。Noneなら非該当
    institution_db: str | None = None
    # 同一DB内の重複レコードを束ねる署名（例: 正規化した書誌ID）。Noneなら非該当
    record_signature: str | None = None


class _UnionFind:
    def __init__(self, keys: list[str]) -> None:
        self._parent = {k: k for k in keys}

    def find(self, key: str) -> str:
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:  # 経路圧縮
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def group_source_families(sources: list[EvidenceSource]) -> list[frozenset[str]]:
    """§6.2の規則で資料を系統へ束ね、系統ごとのdocument_id集合を返す。"""
    ids = [s.document_id for s in sources]
    known = set(ids)
    uf = _UnionFind(ids)
    for s in sources:
        for origin in s.derived_from:
            if origin in known:  # 転載元が判定対象に居る場合のみ併合（規則1）
                uf.union(s.document_id, origin)
        if s.based_solely_on_citations:
            for cited in s.cites:
                if cited in known:  # 引用先併用時のみ独立性を失う（規則2・3）
                    uf.union(s.document_id, cited)
    # 規則4: 同一機関DB・同一レコード署名
    by_signature: dict[tuple[str, str], str] = {}
    for s in sources:
        if s.institution_db is not None and s.record_signature is not None:
            key = (s.institution_db, s.record_signature)
            if key in by_signature:
                uf.union(s.document_id, by_signature[key])
            else:
                by_signature[key] = s.document_id

    families: dict[str, set[str]] = {}
    for doc_id in ids:
        families.setdefault(uf.find(doc_id), set()).add(doc_id)
    return [frozenset(members) for members in families.values()]


def count_independent_families(sources: list[EvidenceSource]) -> int:
    """独立系統数（`Candidate.independent_source_families`・§6.2「2資料以上」の分母）。"""
    return len(group_source_families(sources))
