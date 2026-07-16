"""test_ndl_digital.py — Phase 4 DoD: NDL権利区分の機械フィルタ（PD区分のみ収集）を固定する"""

import pytest

from history_radio.ingest.adapter import SourceAdapter
from history_radio.ingest.adapters.ndl_digital import (
    NdlDigitalAdapter,
    NdlFetchError,
    NdlRestrictedError,
)
from tests.ingest.mock_http import Reply, scripted_fetcher


def _fixture(rights: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:dcndl="http://ndl.go.jp/dcndl/terms/">
  <channel>
    <item>
      <title>米欧回覧実記</title>
      <link>https://dl.ndl.go.jp/pid/1234567</link>
      <dc:creator>久米邦武 編</dc:creator>
      <dc:rights>{rights}</dc:rights>
      <dcndl:dateDigitized>2011-03-31</dcndl:dateDigitized>
    </item>
  </channel>
</rss>"""


def test_adapter_satisfies_protocol() -> None:
    assert isinstance(NdlDigitalAdapter(), SourceAdapter)


def test_internet_pd_item_is_collected_with_granted_permissions() -> None:
    fetcher, _clock, requests = scripted_fetcher(
        [Reply(text=_fixture("インターネット公開（保護期間満了）"))]
    )
    doc = NdlDigitalAdapter().fetch(fetcher, "info:ndljp/pid/1234567")
    assert doc.rights.normalized_license_id == "ndl-internet-pd"
    assert doc.storage_permission == "granted"
    assert doc.publication_permission == "granted"
    assert doc.title == "米欧回覧実記"
    assert "ndlsearch.ndl.go.jp/api" in requests[0].url  # API優先（§7.1）


@pytest.mark.parametrize(
    "restricted_rights",
    [
        "個人向けデジタル化資料送信サービス",
        "国立国会図書館内限定公開",
        "インターネット公開（許諾）",
    ],
)
def test_non_pd_rights_categories_are_rejected_before_document_creation(
    restricted_rights: str,
) -> None:
    """§5.3: 個人送信・館内限定等の区分は取得対象にしない——候補にも入れない。"""
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=_fixture(restricted_rights))])
    with pytest.raises(NdlRestrictedError, match="取得対象外"):
        NdlDigitalAdapter().fetch(fetcher, "info:ndljp/pid/9999999")


def test_missing_rights_metadata_raises() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel><item><title>権利表示なし資料</title>
  <link>https://dl.ndl.go.jp/pid/1</link></item></channel></rss>"""
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=xml)])
    with pytest.raises(NdlFetchError, match="欠落"):
        NdlDigitalAdapter().fetch(fetcher, "info:ndljp/pid/1")


def test_empty_result_raises() -> None:
    xml = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    fetcher, _clock, _requests = scripted_fetcher([Reply(text=xml)])
    with pytest.raises(NdlFetchError, match="該当資料が無い"):
        NdlDigitalAdapter().fetch(fetcher, "info:ndljp/pid/0")


def test_broken_xml_raises_parse_error_not_partial_document() -> None:
    fetcher, _clock, _requests = scripted_fetcher([Reply(text="<rss><broken")])
    with pytest.raises(NdlFetchError, match="解析できない"):
        NdlDigitalAdapter().fetch(fetcher, "info:ndljp/pid/2")
