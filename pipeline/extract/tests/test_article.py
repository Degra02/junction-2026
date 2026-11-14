from pipeline.extract.article import extract_article

_BODY = [
    "The city council approved the new tram line on Tuesday after a debate that lasted six hours.",
    "Opponents said the cost estimate had doubled since the first proposal two years ago.",
    "The mayor said construction would start in spring and the first section would open in 2028.",
]

# Synthetic page with the usual clutter around the article: menu, cookie banner, footer.
PAGE = f"""<!doctype html><html lang="en-GB"><head><title>Tram line approved | City Paper</title>
<meta name="author" content="Jane Doe">
<meta property="og:site_name" content="City Paper">
<meta property="article:published_time" content="2026-11-10T18:05:00Z">
</head><body>
<nav><a href="/">Home</a> <a href="/sport">Sport</a> <a href="/weather">Weather</a></nav>
<div class="cookie">We use cookies. Accept all?</div>
<article><h1>Tram line approved</h1>{"".join(f"<p>{p}</p>" for p in _BODY)}</article>
<footer>Copyright City Paper. All rights reserved.</footer>
</body></html>"""


def test_article_body_and_metadata():
    art = extract_article(PAGE, "https://citypaper.example/tram")
    assert art is not None
    assert art.paragraphs == _BODY  # menu, cookie banner and footer are gone
    assert art.title == "Tram line approved"
    assert art.author == "Jane Doe"
    assert art.published_at == "2026-11-10T18:05:00Z"
    assert art.site_name == "City Paper"
    assert art.language == "en"
    assert art.text.startswith("The city council")


def test_page_without_article_returns_none():
    assert extract_article("<html><body><nav>Home</nav></body></html>") is None
