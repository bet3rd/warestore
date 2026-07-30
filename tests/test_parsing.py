from warestore.domain.accounts.services.token_parser import TokenParser

PARSER = TokenParser()
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"


def test_sanitize_token_strips_whitespace_and_pipe_suffix():
    assert TokenParser.sanitize_token("  eyJ.x.y|extra  ") == "eyJ.x.y"


def test_sanitize_entry_username_token_pair():
    assert PARSER.sanitize_entry(f"user----{JWT}") == f"user----{JWT}"


def test_sanitize_entry_rejects_garbage():
    assert PARSER.sanitize_entry("not-a-jwt") is None
    assert PARSER.sanitize_entry("") is None


def test_sanitize_entry_bare_jwt():
    assert PARSER.sanitize_entry(JWT) == JWT


def test_parse_bulk_tokens_dedupes():
    text = f"{JWT}\n{JWT}\nuser----{JWT}\n"
    tokens = PARSER.parse_bulk(text)
    assert len(tokens) == 2


def test_jwt_from_entry():
    assert TokenParser.jwt_from_entry(JWT) == JWT
    assert TokenParser.jwt_from_entry(f"alice----{JWT}") == JWT
