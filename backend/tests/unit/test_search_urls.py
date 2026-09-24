"""网址识别测试（tasks 3.1）。"""

from app.services.search.urls import extract_urls, has_url


def test_plain_url() -> None:
    assert extract_urls("https://example.com/post/1") == ["https://example.com/post/1"]


def test_url_with_surrounding_text() -> None:
    text = "帮我学一下这个 https://example.com/harness 里讲的东西"

    assert extract_urls(text) == ["https://example.com/harness"]


def test_multiple_urls_are_deduped_and_ordered() -> None:
    text = "https://a.com/x 和 https://b.com/y 还有 https://a.com/x"

    assert extract_urls(text) == ["https://a.com/x", "https://b.com/y"]


def test_www_url_gets_scheme() -> None:
    assert extract_urls("看看 www.example.com/docs 这篇") == ["https://www.example.com/docs"]


def test_trailing_chinese_punctuation_is_trimmed() -> None:
    assert extract_urls("参考 https://example.com/a。") == ["https://example.com/a"]


def test_plain_text_has_no_url() -> None:
    assert extract_urls("存款准备金率是商业银行缴存的准备金占存款总额的比例") == []
    assert has_url("纯文字内容，没有链接") is False
