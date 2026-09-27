from app.nlp.token_diff import changed_token_count, diff_tokens, tokenize


def test_tokenize_splits_words_and_punctuation():
    assert tokenize("Pay ₹50,000 now.") == ["Pay", "₹", "50", ",", "000", "now", "."]


def test_diff_tokens_detects_replace_insert_delete_equal():
    ops = diff_tokens("the fee is 50 dollars total", "the fee is 80 dollars only total")
    tags = [op.op for op in ops]
    assert "replace" in tags
    assert "insert" in tags
    assert "equal" in tags
    # reconstructing "after" tokens from ops must reproduce the after text's tokens
    after_tokens = tokenize("the fee is 80 dollars only total")
    rebuilt: list[str] = []
    for op in ops:
        rebuilt.extend(op.after)
    assert rebuilt == after_tokens


def test_diff_tokens_pure_delete_has_empty_after():
    ops = diff_tokens("clause one and clause two", "clause one")
    delete_ops = [op for op in ops if op.op == "delete"]
    assert delete_ops
    assert all(op.after == () for op in delete_ops)


def test_changed_token_count_ignores_equal_ops():
    ops = diff_tokens("alpha beta gamma", "alpha beta gamma")
    assert changed_token_count(ops) == 0

    ops = diff_tokens("alpha beta gamma", "alpha zeta gamma")
    assert changed_token_count(ops) == 2  # one before token + one after token replaced
