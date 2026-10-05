"""Sending a request spec over the wire."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from flare import __version__
from flare.request import RequestSpec


class RequestError(Exception):
    pass


@dataclass
class Exchange:
    spec: RequestSpec
    request: httpx.Request
    response: httpx.Response
    elapsed: float


def send(spec: RequestSpec, timeout: float = 30.0, transport: httpx.BaseTransport | None = None) -> Exchange:
    timeout = spec.timeout or timeout
    headers = list(spec.headers)
    if spec.header("User-Agent") is None:
        headers.insert(0, ("User-Agent", f"flare/{__version__}"))
    try:
        with httpx.Client(follow_redirects=spec.follow_redirects, verify=spec.verify, timeout=timeout, transport=transport) as client:
            request = client.build_request(
                spec.method,
                spec.url,
                headers=headers,
                content=spec.data.encode() if spec.data is not None else None,
            )
            if spec.auth:
                request = next(httpx.BasicAuth(*spec.auth).auth_flow(request))
            started = time.perf_counter()
            response = client.send(request)
            elapsed = time.perf_counter() - started
    except httpx.TimeoutException:
        raise RequestError(f"timed out after {timeout:g}s") from None
    except httpx.ConnectError as e:
        raise RequestError(f"could not connect to {httpx.URL(spec.url).host or spec.url}: {_reason(e)}") from None
    except (httpx.InvalidURL, httpx.UnsupportedProtocol) as e:
        raise RequestError(f"bad URL {spec.url!r}: {e}") from None
    except httpx.HTTPError as e:
        raise RequestError(f"{type(e).__name__}: {_reason(e)}") from None
    return Exchange(spec, request, response, elapsed)


def _reason(e: Exception) -> str:
    text = str(e) or type(e).__name__
    # "[Errno 8] nodename nor servname provided, or not known" → the readable part
    return text.split("] ", 1)[-1]
