from meme_finder.digest import render_digest


def test_render_digest_empty():
    out = render_digest([])
    assert "每日幽默精选" in out
    assert "没有新内容" in out


def test_render_digest_with_blocks():
    out = render_digest(["- block one", "- block two"])
    assert "block one" in out
    assert "block two" in out
    assert "快速扫一眼" in out
