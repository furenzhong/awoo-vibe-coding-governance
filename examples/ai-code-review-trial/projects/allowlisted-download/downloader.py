from urllib.parse import urlsplit


def may_download(url, allowed_hosts):
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "https" and parsed.hostname in allowed_hosts and parsed.port in (None, 443)
    except ValueError:
        return False
