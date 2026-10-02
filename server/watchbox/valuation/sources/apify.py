"""Minimal client for running Apify actors synchronously and reading their dataset."""
import httpx

API = "https://api.apify.com/v2"


class SourceError(Exception):
    pass


class ApifyClient:
    def _redact(self, message: str) -> str:
        return message.replace(self._token, "***") if self._token else message

    def __init__(self, token: str, http: httpx.Client | None = None, timeout_s: int = 300):
        self._token = token
        self._http = http or httpx.Client()
        self._timeout_s = timeout_s

    def run(self, actor: str, payload: dict) -> list[dict]:
        url = f"{API}/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items"
        try:
            response = self._http.post(url, params={"timeout": self._timeout_s}, json=payload,
                                       headers={"Authorization": f"Bearer {self._token}"},
                                       timeout=self._timeout_s + 30)
        except httpx.HTTPError as e:
            raise SourceError(self._redact(f"{actor}: request failed ({type(e).__name__})")) from None
        if response.status_code not in (200, 201):
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.text[:200]
            raise SourceError(self._redact(f"{actor}: HTTP {response.status_code} {message}"))
        try:
            data = response.json()
        except ValueError:
            raise SourceError(f"{actor}: response was not JSON") from None
        if not isinstance(data, list):
            raise SourceError(f"{actor}: unexpected response shape")
        return data
