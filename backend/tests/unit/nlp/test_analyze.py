from app.nlp.analyze import NlpPipeline, analyze_regions
from app.nlp.classifier import ChangeClassifier
from app.nlp.types import Category, ChangeAnalysis
from proofchain_core.types import BBox, ChangeRegion, RegionType


class _FakeClassifier:
    """Returns a canned analysis keyed by region id, so tests control categories precisely."""

    def __init__(self, by_region_id: dict[str, ChangeAnalysis]) -> None:
        self._by_region_id = by_region_id

    def analyze(self, region: ChangeRegion) -> ChangeAnalysis:
        return self._by_region_id[region.id]


def _analysis(region_id: str, category: Category) -> ChangeAnalysis:
    return ChangeAnalysis(
        region_id=region_id,
        primary_category=category,
        categories=(category,),
        severity="HIGH",
        similarity=None,
        entity_changes=(),
        token_diff=(),
        explanation="template explanation",
        method="RULES",
    )


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text: str) -> None:
        self.content = [_TextBlock(text)]


class _RecordingMessages:
    def __init__(self, outer: "_RecordingLlmClient") -> None:
        self._outer = outer

    async def create(self, **kwargs):
        self._outer.calls.append(kwargs)
        return _Response(self._outer._reply)


class _RecordingLlmClient:
    """Fake Anthropic-shaped client: records every `messages.create` call verbatim."""

    def __init__(self, reply: str = "llm explanation") -> None:
        self._reply = reply
        self.calls: list[dict] = []
        self.messages = _RecordingMessages(self)


async def test_analyze_regions_without_llm_returns_rule_based_analyses():
    region = ChangeRegion(id="r1", type=RegionType.MODIFIED, ref_text="a", cand_text="b")
    classifier = _FakeClassifier({"r1": _analysis("r1", Category.MINOR_EDIT)})
    results = await analyze_regions([region], classifier, llm_client=None, llm_model="m")
    assert results == [_analysis("r1", Category.MINOR_EDIT)]


async def test_analyze_regions_with_llm_replaces_explanation_and_bumps_method():
    region = ChangeRegion(id="r1", type=RegionType.MODIFIED, ref_text="a", cand_text="b")
    classifier = _FakeClassifier({"r1": _analysis("r1", Category.MINOR_EDIT)})
    llm = _RecordingLlmClient("a richer explanation")
    [result] = await analyze_regions([region], classifier, llm_client=llm, llm_model="m")
    assert result.explanation == "a richer explanation"
    assert result.method == "RULES+EMBEDDINGS+LLM"
    assert result.primary_category == Category.MINOR_EDIT  # category/severity untouched


async def test_analyze_regions_llm_payload_contains_only_that_regions_text_and_categories():
    """Privacy guarantee (06 "never sends whole documents"): build a region drawn from a large,
    multi-page document with a second, unrelated region alongside it (distinct page, section,
    chunk ids, bbox, text). The LLM call made for the region of interest must contain that
    region's before/after text and its own detected categories -- and nothing else: not the
    other region's text, not either region's section title, page number, chunk id, bbox, or
    region id, and no document/revision metadata (neither region carries a document id, so
    there is nothing of the kind to check for a positive match, and the call payload is
    exhaustively asserted below to rule out anything besides the sanctioned fields).
    """
    region_of_interest = ChangeRegion(
        id="region-of-interest-id",
        type=RegionType.MODIFIED,
        ref_text="The Executive shall receive a base salary of Rs. 500.",
        cand_text="The Executive may receive a base salary of Rs. 800.",
        ref_page=47,
        cand_page=47,
        ref_bbox=BBox(10, 10, 20, 20),
        cand_bbox=BBox(10, 10, 20, 20),
        ref_chunk_id="chunk-secret-991",
        cand_chunk_id="chunk-secret-992",
        section_id="sec-9",
        section_title="Confidential Schedule B: Executive Compensation",
    )
    decoy_region = ChangeRegion(
        id="decoy-region-id",
        type=RegionType.MODIFIED,
        ref_text="SECRET_OTHER_REGION_TEXT_DO_NOT_LEAK before",
        cand_text="SECRET_OTHER_REGION_TEXT_DO_NOT_LEAK after",
        ref_page=999,
        cand_page=999,
        section_title="OTHER_SECTION_DO_NOT_LEAK",
        ref_chunk_id="OTHER_CHUNK_DO_NOT_LEAK",
        cand_chunk_id="OTHER_CHUNK_DO_NOT_LEAK",
    )
    classifier = _FakeClassifier(
        {
            "region-of-interest-id": _analysis("region-of-interest-id", Category.OBLIGATION_CHANGE),
            "decoy-region-id": _analysis("decoy-region-id", Category.AMOUNT_CHANGE),
        }
    )
    llm = _RecordingLlmClient()

    await analyze_regions(
        [region_of_interest, decoy_region], classifier, llm_client=llm, llm_model="m"
    )

    assert len(llm.calls) == 2
    call_for_region_of_interest = llm.calls[0]
    [message] = call_for_region_of_interest["messages"]
    content = message["content"]

    # the sanctioned content: this region's own before/after text and its own category
    assert region_of_interest.ref_text in content
    assert region_of_interest.cand_text in content
    assert "OBLIGATION_CHANGE" in content

    # nothing from the other region
    assert "SECRET_OTHER_REGION_TEXT_DO_NOT_LEAK" not in content
    assert "OTHER_SECTION_DO_NOT_LEAK" not in content
    assert "OTHER_CHUNK_DO_NOT_LEAK" not in content
    assert "999" not in content
    assert "AMOUNT_CHANGE" not in content

    # nothing from this region's own metadata either -- only text and categories are sanctioned
    assert "region-of-interest-id" not in content
    assert "sec-9" not in content
    assert "Confidential Schedule B" not in content
    assert "chunk-secret-991" not in content
    assert "chunk-secret-992" not in content
    assert "47" not in content

    # the full call has no extra fields beyond what messages.create needs
    assert set(call_for_region_of_interest.keys()) <= {"model", "max_tokens", "system", "messages"}
    assert call_for_region_of_interest["model"] == "m"


async def test_analyze_regions_keeps_template_explanation_when_llm_returns_nothing():
    """LLM client is present but fails/times out/replies blank (see test_llm.py): the region
    keeps its rule-based explanation and method, unchanged."""
    region = ChangeRegion(id="r1", type=RegionType.MODIFIED, ref_text="a", cand_text="b")
    classifier = _FakeClassifier({"r1": _analysis("r1", Category.MINOR_EDIT)})
    llm = _RecordingLlmClient(reply="   ")  # blank reply -> explain_with_llm returns None
    [result] = await analyze_regions([region], classifier, llm_client=llm, llm_model="m")
    assert result == _analysis("r1", Category.MINOR_EDIT)


async def test_nlp_pipeline_returns_empty_list_when_disabled():
    pipeline = NlpPipeline(
        classifier=_FakeClassifier({}), enabled=False, llm_client=None, llm_model="m"
    )
    region = ChangeRegion(id="r1", type=RegionType.MODIFIED, ref_text="a", cand_text="b")
    assert await pipeline.analyze([region]) == []


async def test_nlp_pipeline_returns_empty_list_for_no_regions():
    pipeline = NlpPipeline(
        classifier=_FakeClassifier({}), enabled=True, llm_client=None, llm_model="m"
    )
    assert await pipeline.analyze([]) == []


async def test_nlp_pipeline_analyzes_when_enabled_with_regions():
    region = ChangeRegion(id="r1", type=RegionType.MODIFIED, ref_text="a", cand_text="b")
    classifier = _FakeClassifier({"r1": _analysis("r1", Category.CLAUSE_MODIFIED)})
    pipeline = NlpPipeline(classifier=classifier, enabled=True, llm_client=None, llm_model="m")
    assert await pipeline.analyze([region]) == [_analysis("r1", Category.CLAUSE_MODIFIED)]


def test_change_classifier_protocol_is_satisfied_by_fake() -> None:
    fake: ChangeClassifier = _FakeClassifier({})
    assert hasattr(fake, "analyze")
