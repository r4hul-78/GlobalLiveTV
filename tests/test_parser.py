import pytest
from app.services.m3u_parser import parse_m3u_content, _split_extinf_line, _parse_attributes
from app.services.security import is_safe_url, validate_stream_url


def test_parse_valid_m3u_standard():
    """Verify parsing of standard well-formed M3U playlist with full attributes."""
    content = """#EXTM3U
#EXTINF:-1 tvg-id="CNN.us" tvg-name="CNN" tvg-logo="https://example.com/cnn.png" group-title="News",CNN USA (720p)
https://example.com/cnn/live.m3u8
#EXTINF:0 tvg-id="BBC.uk" tvg-logo="https://example.com/bbc.png" group-title="General",BBC One
https://example.com/bbc/one.m3u8
"""
    records = parse_m3u_content(content)
    assert len(records) == 2

    cnn = records[0]
    assert cnn.name == "CNN USA (720p)"
    assert cnn.external_id == "CNN.us"
    assert cnn.logo_url == "https://example.com/cnn.png"
    assert cnn.stream_url == "https://example.com/cnn/live.m3u8"
    assert "News" in cnn.genres

    bbc = records[1]
    assert bbc.name == "BBC One"
    assert bbc.external_id == "BBC.uk"
    assert bbc.stream_url == "https://example.com/bbc/one.m3u8"
    assert "General" in bbc.genres


def test_parse_commas_in_channel_name():
    """Verify parser preserves commas in channel titles."""
    content = """#EXTM3U
#EXTINF:-1 tvg-id="Test.tv" group-title="Movies",Action, Drama, & Comedy TV (East)
https://example.com/stream.m3u8
"""
    records = parse_m3u_content(content)
    assert len(records) == 1
    assert records[0].name == "Action, Drama, & Comedy TV (East)"


def test_parse_commas_inside_quoted_attributes():
    """Verify commas inside quoted attributes do not break title extraction."""
    content = """#EXTM3U
#EXTINF:-1 tvg-id="Multi.tv" group-title="News, Current Affairs, Politics",World News 24
https://example.com/worldnews.m3u8
"""
    records = parse_m3u_content(content)
    assert len(records) == 1
    assert records[0].name == "World News 24"
    assert records[0].group_title == "News, Current Affairs, Politics"


def test_parse_missing_attributes():
    """Verify parser handles entries with missing attributes gracefully."""
    content = """#EXTM3U
#EXTINF:-1,Minimalist Channel
https://example.com/minimal.m3u8
"""
    records = parse_m3u_content(content)
    assert len(records) == 1
    rec = records[0]
    assert rec.name == "Minimalist Channel"
    assert rec.external_id is None
    assert rec.logo_url is None
    assert rec.country_code is None
    assert len(rec.genres) == 0


def test_parse_inconsistent_line_endings():
    """Verify parser works identically with CRLF, LF, and CR line endings."""
    crlf_content = "#EXTM3U\r\n#EXTINF:-1 tvg-id=\"A\",Channel A\r\nhttps://example.com/a.m3u8\r\n"
    cr_content = "#EXTM3U\r#EXTINF:-1 tvg-id=\"B\",Channel B\rhttps://example.com/b.m3u8\r"
    lf_content = "#EXTM3U\n#EXTINF:-1 tvg-id=\"C\",Channel C\nhttps://example.com/c.m3u8\n"

    r_crlf = parse_m3u_content(crlf_content)
    r_cr = parse_m3u_content(cr_content)
    r_lf = parse_m3u_content(lf_content)

    assert len(r_crlf) == 1 and r_crlf[0].name == "Channel A"
    assert len(r_cr) == 1 and r_cr[0].name == "Channel B"
    assert len(r_lf) == 1 and r_lf[0].name == "Channel C"


def test_parse_rejects_unsafe_and_private_urls():
    """Verify parser rejects stream URLs pointing to private/loopback IP ranges."""
    content = """#EXTM3U
#EXTINF:-1 tvg-id="Local.tv",Localhost Attack
http://127.0.0.1:8080/stream.m3u8
#EXTINF:-1 tvg-id="Private.tv",Private Network Attack
http://192.168.1.100/live.m3u8
#EXTINF:-1 tvg-id="Metadata.tv",Cloud Metadata Attack
http://169.254.169.254/latest/meta-data/
#EXTINF:-1 tvg-id="Valid.tv",Public Valid Stream
https://cdn.example.com/stream.m3u8
"""
    records = parse_m3u_content(content)
    assert len(records) == 1
    assert records[0].external_id == "Valid.tv"
    assert records[0].stream_url == "https://cdn.example.com/stream.m3u8"


def test_parse_malformed_records():
    """Verify malformed records without stream URL or with empty content are safely skipped."""
    content = """#EXTM3U
#EXTINF:-1 tvg-id="Orphan.1",Orphan Extinf 1
#EXTINF:-1 tvg-id="Orphan.2",Orphan Extinf 2
# Some other random comment
#EXTINF:-1 tvg-id="Good.tv",Good Channel
https://example.com/good.m3u8
"""
    records = parse_m3u_content(content)
    assert len(records) == 1
    assert records[0].external_id == "Good.tv"


def test_security_is_safe_url_validation():
    """Unit test for is_safe_url security constraints."""
    # Forbidden schemes
    assert is_safe_url("file:///etc/passwd", resolve_dns=False)[0] is False
    assert is_safe_url("ftp://example.com/stream", resolve_dns=False)[0] is False
    assert is_safe_url("javascript:alert(1)", resolve_dns=False)[0] is False

    # Prohibited hosts
    assert is_safe_url("http://localhost/stream.m3u8", resolve_dns=False)[0] is False
    assert is_safe_url("http://127.0.0.1/stream.m3u8", resolve_dns=False)[0] is False
    assert is_safe_url("http://10.0.0.1/stream.m3u8", resolve_dns=False)[0] is False
    assert is_safe_url("http://172.16.0.1/stream.m3u8", resolve_dns=False)[0] is False
    assert is_safe_url("http://192.168.0.1/stream.m3u8", resolve_dns=False)[0] is False
    assert is_safe_url("http://server.local/stream.m3u8", resolve_dns=False)[0] is False

    # Allowed public URL syntax
    assert is_safe_url("https://example.com/live.m3u8", resolve_dns=False)[0] is True
    assert is_safe_url("http://cdn.broadcaster.org/stream/index.m3u8", resolve_dns=False)[0] is True
