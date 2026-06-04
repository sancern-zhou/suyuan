"""
HTTP client utilities with retry logic and error handling.
"""
import httpx
import asyncio
from typing import Optional, Dict, Any
from config.settings import settings
import structlog

logger = structlog.get_logger()


class HTTPClient:
    """Async HTTP client with retry and timeout logic."""

    def __init__(
        self,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_interval_ms: Optional[int] = None,
    ):
        # Use settings values if not provided, evaluated at runtime
        self.timeout = timeout if timeout is not None else settings.request_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.max_retries
        self.retry_interval_ms = retry_interval_ms if retry_interval_ms is not None else settings.retry_interval_ms
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retry: bool = True,
    ) -> Dict[str, Any]:
        """
        Perform GET request with retry logic.

        Args:
            url: Request URL
            params: Query parameters
            headers: Request headers
            retry: Whether to enable retry

        Returns:
            Response JSON as dict

        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        retries = 0
        last_error = None

        while retries <= (self.max_retries if retry else 0):
            try:
                # Log detailed request information
                # print(f"\n{'='*80}")
                # print(f"[HTTP GET] {url}")
                # print(f"Params: {params}")
                # print(f"Headers: {headers}")
                # print(f"Retry attempt: {retries}")
                # print(f"{'='*80}")

                logger.info(
                    "http_request_detail",
                    method="GET",
                    url=url,
                    params=params,
                    headers=headers,
                    retry_attempt=retries,
                )

                # print(f"[DEBUG] About to make HTTP GET request...")
                # print(f"[DEBUG] Timeout setting: {self.timeout}s")

                response = await self.client.get(url, params=params, headers=headers)

                # print(f"[DEBUG] Request completed! Got response object")

                # Log response details
                # print(f"\n[RESPONSE RECEIVED]")
                # print(f"Status: {response.status_code}")
                # print(f"Content-Length: {len(response.content)} bytes")
                # print(f"Response preview: {response.text[:200]}")
                # print(f"{'='*80}\n")

                logger.info(
                    "http_response_received",
                    method="GET",
                    url=url,
                    status_code=response.status_code,
                    content_length=len(response.content),
                    response_preview=response.text[:200],
                )

                response.raise_for_status()

                # Try to parse JSON
                try:
                    result = response.json()
                    logger.info(
                        "http_response_parsed",
                        method="GET",
                        url=url,
                        response_type=type(result).__name__,
                        response_keys=list(result.keys()) if isinstance(result, dict) else None,
                    )
                    return result
                except Exception as json_error:
                    logger.error(
                        "json_parse_failed",
                        method="GET",
                        url=url,
                        status_code=response.status_code,
                        response_text=response.text[:500],
                        error=str(json_error),
                    )
                    raise

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    "http_request_failed",
                    method="GET",
                    url=url,
                    error=f"Timeout after {self.timeout}s",
                    error_type="TimeoutException",
                    retry_attempt=retries,
                )
                if retries < self.max_retries and retry:
                    await asyncio.sleep(self.retry_interval_ms / 1000)
                    retries += 1
                else:
                    break
            except httpx.HTTPError as e:
                last_error = e
                error_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
                logger.warning(
                    "http_request_failed",
                    method="GET",
                    url=url,
                    error=error_msg,
                    error_type=type(e).__name__,
                    retry_attempt=retries,
                )
                if retries < self.max_retries and retry:
                    await asyncio.sleep(self.retry_interval_ms / 1000)
                    retries += 1
                else:
                    break
            except Exception as e:
                last_error = e
                error_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
                logger.error(
                    "http_request_unexpected_error",
                    method="GET",
                    url=url,
                    error=error_msg,
                    error_type=type(e).__name__,
                    retry_attempt=retries,
                )
                if retries < self.max_retries and retry:
                    await asyncio.sleep(self.retry_interval_ms / 1000)
                    retries += 1
                else:
                    break

        error_msg = f"{type(last_error).__name__}: {str(last_error)}" if last_error and str(last_error) else (type(last_error).__name__ if last_error else "Unknown error")
        logger.error(
            "http_request_exhausted",
            method="GET",
            url=url,
            error=error_msg,
            error_type=type(last_error).__name__ if last_error else "Unknown",
        )
        raise last_error

    async def post(
        self,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        retry: bool = True,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Perform POST request with retry logic.

        Args:
            url: Request URL
            json_data: JSON body
            data: Raw body data
            headers: Request headers
            retry: Whether to enable retry
            timeout: Request timeout in seconds (uses default if not specified)

        Returns:
            Response JSON as dict

        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        retries = 0
        last_error = None
        # Use provided timeout or default
        request_timeout = timeout if timeout is not None else self.timeout

        while retries <= (self.max_retries if retry else 0):
            try:
                # Log detailed request information
                import json as json_lib

                # Print full request details for debugging
                # print(f"\n{'='*80}")
                # print(f"[HTTP POST] {url}")
                # print(f"Headers: {headers}")
                # print(f"Retry attempt: {retries}")
                # print(f"Timeout: {request_timeout}s")
                # if json_data:
                #     print(f"JSON Body:")
                #     print(json_lib.dumps(json_data, ensure_ascii=False, indent=2))
                # print(f"{'='*80}")

                logger.info(
                    "http_request_detail",
                    method="POST",
                    url=url,
                    json_data=json_lib.dumps(json_data, ensure_ascii=False)[:500] if json_data else None,
                    headers=headers,
                    retry_attempt=retries,
                    timeout=request_timeout,
                )

                # Create a client with the specified timeout for this request
                async with httpx.AsyncClient(timeout=httpx.Timeout(request_timeout)) as client:
                    response = await client.post(
                        url, json=json_data, data=data, headers=headers
                    )

                # Log response details
                # print(f"\n[RESPONSE RECEIVED]")
                # print(f"Status: {response.status_code}")
                # print(f"Content-Length: {len(response.content)} bytes")
                # print(f"Response text (first 500 chars):")
                # print(response.text[:500])
                # print(f"{'='*80}\n")

                logger.info(
                    "http_response_received",
                    method="POST",
                    url=url,
                    status_code=response.status_code,
                    content_length=len(response.content),
                    response_preview=response.text[:200],
                )

                response.raise_for_status()

                # Try to parse JSON
                try:
                    result = response.json()
                    logger.info(
                        "http_response_parsed",
                        method="POST",
                        url=url,
                        response_type=type(result).__name__,
                        response_keys=list(result.keys()) if isinstance(result, dict) else None,
                    )
                    return result
                except Exception as json_error:
                    logger.error(
                        "json_parse_failed",
                        method="POST",
                        url=url,
                        status_code=response.status_code,
                        response_text=response.text[:500],
                        error=str(json_error),
                    )
                    raise

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    "http_request_failed",
                    method="POST",
                    url=url,
                    error=f"Timeout after {self.timeout}s",
                    error_type="TimeoutException",
                    retry_attempt=retries,
                )
                if retries < self.max_retries and retry:
                    await asyncio.sleep(self.retry_interval_ms / 1000)
                    retries += 1
                else:
                    break
            except httpx.HTTPError as e:
                last_error = e
                error_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
                logger.warning(
                    "http_request_failed",
                    method="POST",
                    url=url,
                    error=error_msg,
                    error_type=type(e).__name__,
                    retry_attempt=retries,
                )
                if retries < self.max_retries and retry:
                    await asyncio.sleep(self.retry_interval_ms / 1000)
                    retries += 1
                else:
                    break
            except Exception as e:
                last_error = e
                error_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
                logger.error(
                    "http_request_unexpected_error",
                    method="POST",
                    url=url,
                    error=error_msg,
                    error_type=type(e).__name__,
                    retry_attempt=retries,
                )
                if retries < self.max_retries and retry:
                    await asyncio.sleep(self.retry_interval_ms / 1000)
                    retries += 1
                else:
                    break

        error_msg = f"{type(last_error).__name__}: {str(last_error)}" if last_error and str(last_error) else (type(last_error).__name__ if last_error else "Unknown error")
        logger.error(
            "http_request_exhausted",
            method="POST",
            url=url,
            error=error_msg,
            error_type=type(last_error).__name__ if last_error else "Unknown",
        )
        raise last_error


# Global HTTP client instance
http_client = HTTPClient()
