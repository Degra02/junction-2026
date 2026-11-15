from propaganda_eval.memes import fits, item, select
from propaganda_eval.runner import MAX_IMAGE_DATA_URI_CHARS, image_mime

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def test_image_type_comes_from_the_bytes_not_the_name():
    # The corpus saves JPEGs as `.png`: a data URI typed from the name would lie.
    assert image_mime(JPEG) == "image/jpeg"
    assert image_mime(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10) == "image/png"
    assert image_mime(b"<html>not an image</html>") is None


def test_images_over_the_api_limit_do_not_fit():
    assert fits(JPEG)
    assert not fits(b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_DATA_URI_CHARS * 3 // 4))
    assert not fits(b"plain text")


def test_selection_keeps_every_negative_and_is_stable():
    annotations = [
        {"id": f"{i}", "labels": ["Smears"] if i % 5 else [], "image": f"{i}.png"}
        for i in range(100)
    ]
    first = select(annotations, positives=10)
    assert [a["id"] for a in first] == [a["id"] for a in select(annotations, positives=10)]
    assert sum(not a["labels"] for a in first) == 20  # all of them
    row = item(first[0])
    assert row["labels"] == {"single": False, "coordinated": None}
    assert row["image"].startswith("semeval2021/images/") and "text" not in row
