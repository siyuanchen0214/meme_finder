from meme_finder.digest import render_digest


def test_render_digest_empty():
    out = render_digest([])
    assert "Nothing new" in out
    assert "Daily Humor Digest" in out


def test_render_digest_with_blocks():
    out = render_digest(["- block one", "- block two"])
    assert "block one" in out
    assert "block two" in out
    assert "Quick scan" in out
