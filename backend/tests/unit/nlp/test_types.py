from app.nlp.types import Category, ChangeAnalysis, DiffOp, EntityChange


def test_diff_op_to_dict():
    op = DiffOp(op="replace", before=("a", "b"), after=("c",))
    assert op.to_dict() == {"op": "replace", "before": ["a", "b"], "after": ["c"]}


def test_entity_change_to_dict():
    change = EntityChange(type="MONEY", before="INR:500.00", after=None)
    assert change.to_dict() == {"type": "MONEY", "before": "INR:500.00", "after": None}


def test_change_analysis_to_dict_is_json_shaped():
    analysis = ChangeAnalysis(
        region_id="r1",
        primary_category=Category.AMOUNT_CHANGE,
        categories=(Category.AMOUNT_CHANGE, Category.DATE_CHANGE),
        severity="HIGH",
        similarity=0.42,
        entity_changes=(EntityChange(type="MONEY", before="INR:500.00", after="INR:800.00"),),
        token_diff=(DiffOp(op="equal", before=("a",), after=("a",)),),
        explanation="the amount changed",
        method="RULES+EMBEDDINGS",
    )
    assert analysis.to_dict() == {
        "region_id": "r1",
        "primary_category": "AMOUNT_CHANGE",
        "categories": ["AMOUNT_CHANGE", "DATE_CHANGE"],
        "severity": "HIGH",
        "similarity": 0.42,
        "entity_changes": [{"type": "MONEY", "before": "INR:500.00", "after": "INR:800.00"}],
        "token_diff": [{"op": "equal", "before": ["a"], "after": ["a"]}],
        "explanation": "the amount changed",
        "method": "RULES+EMBEDDINGS",
    }
