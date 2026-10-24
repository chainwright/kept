from kept import research
from kept.seed import seed


def test_personal_and_demo_addresses_are_not_looked_up():
    assert research.own_domain("jo@gmail.com") is None
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
    out = research.look_up("Jo", "jo@gmail.com", "I run Happy Paws Grooming in Portland")
    assert [f["text"] for f in out["facts"]] == ["Opened in May, books by phone"]
    assert research.known("jo@gmail.com")["business"] == "Happy Paws Grooming"
