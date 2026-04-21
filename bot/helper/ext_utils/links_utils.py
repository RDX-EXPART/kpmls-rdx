from urllib.parse import unquote, urlparse, unquote_plus, urlunparse


def get_url_name(url: str):
    return unquote_plus(unquote(urlparse(url).path.rpartition('/')[-1]))
