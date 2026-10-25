from kept import research
from kept.seed import seed


def test_personal_and_demo_addresses_are_not_looked_up():
    assert research.own_domain("jo@example.com") is None
    assert research.own_domain("maria@sunrisebakery.example") is None
    assert research.own_domain("sam@pipsoriginal.com") == "pipsoriginal.com"


def test_only_quoted_facts_from_pages_naming_the_business_survive(fake, monkeypatch):
    seed(force=True)
    from kept.tools import search
    pages = [{"id": "web:a", "title": "", "url": "https://news.example/a", "published": "",
              "content": "Happy Paws Grooming opened on Hawthorne in May and books by phone only."},
             {"id": "web:b", "title": "", "url": "https://other.example/b", "published": "",
              "content": "A different shop entirely, with online booking."}]
    monkeypatch.setattr(search, "search", lambda *a, **k: pages)
    monkeypatch.setattr(search, "extract", lambda urls: [])
    fake([("name the business", {"business": "Happy Paws Grooming", "city": "Portland", "kind": "grooming"}),
          ("give up to 4 short facts", {"facts": [
              {"text": "Opened in May, books by phone", "source": "web:a", "quote": "books by phone only"},
              {"text": "Has online booking", "source": "web:b", "quote": "with online booking"},
              {"text": "Has 500 reviews", "source": "web:a", "quote": "500 five-star reviews"}]})])
    out = research.look_up("Jo", "jo@example.com", "I run Happy Paws Grooming in Portland")
    assert [f["text"] for f in out["facts"]] == ["Opened in May, books by phone"]
    assert research.known("jo@example.com")["business"] == "Happy Paws Grooming"


def test_the_part_of_the_page_about_the_business_reaches_the_model():
    page = "Menu Home Shop Cookies " * 400 + "Pip’s Original Doughnuts & Chai opened in 2010 on NE Fremont."
    key = research._norm("Pip's Original Doughnuts")[:14]
    assert key in research._norm(page)
    part = research.excerpt(page, key)
    assert "opened in 2010" in part and len(part) <= 3100
    assert research.excerpt("no mention here", key) == "no mention here"


def test_a_business_read_into_the_email_address_is_not_looked_up(fake, monkeypatch):
    """Live, Oct 24: 'jo@riverahome.example' became 'Rivera Home', a real shop was found, and Jo, a homeowner,
    was treated as a commercial client. A business counts only if the email itself names it."""
    from kept import research
    from kept.tools import search
    calls = []
    monkeypatch.setattr(search, "search", lambda *a, **k: calls.append(a) or [])
    fake([("name the business", {"business": "Rivera Home", "city": "Portland", "kind": "home goods"})])
    out = research.look_up("Jo Rivera", "jo@riverahome.example", "Hi Alex, we just bought a house. What would a new kitchen cost?")
    assert calls == [] and not out["facts"]
