import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0"}

SUPPORTED_HOSTS = [
    "drive.google.com",
    "pixeldrain.com",
    "mega.nz",
    "mediafire.com",
    "gofile.io",
]

WRAPPER_SITES = [
    "gdflix",
    "gdtot",
    "hubdrive"
]


def extract_mirrors(url):

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        mirrors = []

        for a in soup.find_all("a", href=True):

            link = a["href"]

            if any(host in link for host in SUPPORTED_HOSTS):
                mirrors.append(link)

            elif link.startswith("http") and "download" in link:
                mirrors.append(link)

        return list(set(mirrors))

    except:
        return []
