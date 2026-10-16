from app.core.redact import redact


def test_tokens_emails_and_signatures_are_hidden():
    url = "https://x.example/a.pdf?token=abc&email=me@x.org&sig=s1&signature=s2&page=2&api_key=k"
    assert redact(url) == "https://x.example/a.pdf?token=***&email=***&sig=***&signature=***&page=2&api_key=***"
