"""Peticiones HTTP sencillas (solo biblioteca estándar)."""
import json
import urllib.parse
import urllib.request

from . import __version__

USER_AGENT = f"EasyTunrMusic/{__version__}"
BROWSER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def get(url, params=None, headers=None, data=None, timeout=20, user_agent=USER_AGENT):
    """Devuelve los bytes de la respuesta. Lanza urllib.error.HTTPError/URLError."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, data=data, headers={"User-Agent": user_agent, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read()


def get_json(url, params=None, **kwargs):
    return json.loads(get(url, params, **kwargs).decode("utf-8"))
