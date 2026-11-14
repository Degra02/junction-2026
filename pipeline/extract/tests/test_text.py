from pipeline.extract.text import paragraphs_from_text


def test_blank_lines_separate_paragraphs_and_wraps_are_joined():
    text = "First line\nwrapped here.\n\n  Second   paragraph. \r\n\r\nThird."
    assert paragraphs_from_text(text) == [
        "First line wrapped here.",
        "Second paragraph.",
        "Third.",
    ]


def test_text_without_blank_lines_splits_on_line_breaks():
    post = "Breaking: they lied to you\nShare before it is deleted!!\n"
    assert paragraphs_from_text(post) == [
        "Breaking: they lied to you",
        "Share before it is deleted!!",
    ]


def test_unicode_is_normalised_and_nbsp_removed():
    decomposed = "Città eterna"  # "à" as two code points, non-breaking space
    assert paragraphs_from_text(decomposed) == ["Città eterna"]


def test_empty_input():
    assert paragraphs_from_text("  \n\n \n") == []
