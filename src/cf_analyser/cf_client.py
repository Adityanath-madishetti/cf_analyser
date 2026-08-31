"""Thin async wrapper over the Codeforces REST API.

Every request is signed and authenticated using a Codeforces API key + secret
(see https://codeforces.com/apiHelp), read from the CF_API_KEY / CF_API_SECRET
environment variables. Tool code should never call the API directly or build
signed params itself -- it goes through the methods on CFClient.
"""

from __future__ import annotations

import hashlib
import os
import random
import string
import time
from typing import Any

import httpx

BASE_URL = "https://codeforces.com/api"


class CFApiError(RuntimeError):
    """Raised when the Codeforces API returns status == FAILED, or the request itself fails."""


class CFClient:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None) -> None:

        # setting apikey and secret in class variables
        self.api_key = api_key or os.environ.get("CF_API_KEY")
        self.api_secret = api_secret or os.environ.get("CF_API_SECRET")

        if not self.api_key or not self.api_secret:
            raise CFApiError(
                "CF_API_KEY and CF_API_SECRET must be set in the environment "
                "(generate a key/secret pair at https://codeforces.com/settings/api)."
            )

        #setting up connection client
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    #authentication machinery
    def _sign(self, method: str, params: dict[str, Any]) -> dict[str, Any]:

        signed = {k: str(v) for k, v in params.items() if v is not None}
        signed["apiKey"] = self.api_key
        signed["time"] = str(int(time.time()))

        rand6 = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        sorted_query = "&".join(f"{k}={v}" for k, v in sorted(signed.items()))
        to_hash = f"{rand6}/{method}?{sorted_query}#{self.api_secret}"
        digest = hashlib.sha512(to_hash.encode("utf-8")).hexdigest()

        signed["apiSig"] = f"{rand6}{digest}"
        return signed

    async def call(self, method: str, **params: Any) -> Any:
        """Call a Codeforces API method and return its `result` payload."""
        # this adds authentication params and also stringify the query aprams taht are menat for this method and provided by user
        signed_params = self._sign(method, params)
        try:
            response = await self._http.get(f"/{method}", params=signed_params)
        except httpx.HTTPError as exc:
            raise CFApiError(f"Request to {method} failed: {exc}") from exc

        # Codeforces returns a JSON body with status/comment even on 4xx responses
        # (e.g. bad handle, bad signature), so try to parse that before falling
        # back to a generic HTTP error.
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise CFApiError(f"{method} returned a non-JSON response")

        if data.get("status") != "OK":
            raise CFApiError(f"{method} failed: {data.get('comment', 'unknown error')}")
        return data["result"]

    # -- convenience wrappers over the endpoints this server uses --

    async def user_info(self, handles: list[str]) -> list[dict[str, Any]]:
        return await self.call("user.info", handles=";".join(handles))

    async def user_rating(self, handle: str) -> list[dict[str, Any]]:
        return await self.call("user.rating", handle=handle)

    async def user_status(self, handle: str, count: int | None = None) -> list[dict[str, Any]]:
        return await self.call("user.status", handle=handle, count=count)

    async def problemset_problems(self, tags: list[str] | None = None) -> dict[str, Any]:
        tag_param = ";".join(tags) if tags else None
        return await self.call("problemset.problems", tags=tag_param)

    async def contest_list(self, gym: bool = False) -> list[dict[str, Any]]:
        return await self.call("contest.list", gym=gym)

    async def contest_standings(
        self, contest_id: int, handles: list[str], count: int | None = None
    ) -> dict[str, Any]:
        return await self.call(
            "contest.standings",
            contestId=contest_id,
            handles=";".join(handles),
            count=count,
        )
