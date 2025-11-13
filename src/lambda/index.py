import json
import hashlib
import os
import urllib.request
import urllib.parse
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])

# Allowed domains
ALLOWED_DOMAINS = [
    "openexchangerates.org",
    "api.twelvedata.com",
]

# Cacheable path patterns: domain/path prefix
CACHEABLE_PATHS = [
    "openexchangerates.org/api/historical",
    "api.twelvedata.com/eod",
]


def is_allowed_domain(path):
    """Check if the domain is allowed."""
    path_clean = path.lstrip("/")
    return any(path_clean.startswith(domain) for domain in ALLOWED_DOMAINS)


def is_cacheable_path(path):
    """Check if the path should be cached."""
    path_clean = path.lstrip("/")
    return any(path_clean.startswith(pattern) for pattern in CACHEABLE_PATHS)


def should_cache_response(path, status_code, data):
    """Determine if response should be cached based on path-specific rules."""
    if not is_cacheable_path(path):
        logger.info(f"Path not cacheable: {path}")
        return False

    # Only cache HTTP 200 responses
    if status_code != 200:
        logger.info(f"Status code {status_code} not cacheable")
        return False

    path_clean = path.lstrip("/")
    if path_clean.startswith("openexchangerates.org"):
        # For openexchangerates, cache all 200 responses
        logger.info("openexchangerates: caching 200 response")
        return True
    elif path_clean.startswith("api.twelvedata.com"):
        # For twelvedata, check JSON body for error codes
        try:
            json_data = json.loads(data)
            if "code" in json_data:
                code = json_data["code"]
                # Don't cache 429 (rate limit) or 5xx errors
                if code == 429 or (code >= 500 and code < 600):
                    logger.info(f"twelvedata: not caching error code {code}")
                    return False
            logger.info("twelvedata: caching successful response")
            return True
        except (json.JSONDecodeError, KeyError):
            # If we can't parse JSON, cache it anyway
            logger.info("twelvedata: caching non-JSON response")
            return True
    return False


def handler(event, context):
    path = event.get("rawPath", "/")
    query_params = event.get("queryStringParameters") or {}

    logger.info(f"Request received: path={path}, params={query_params}")

    # Validate domain is allowed
    if not is_allowed_domain(path):
        logger.warning(f"Domain not allowed: {path}")
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Domain not allowed"}),
            "headers": {"Content-Type": "application/json"},
        }

    # Build full upstream URL (path includes domain)
    query_string = urllib.parse.urlencode(query_params)
    full_path = f"{path}?{query_string}" if query_string else path
    upstream_url = f"https:/{full_path}"

    if is_cacheable_path(path):
        # Generate hash for cache key
        request_hash = hashlib.sha256(full_path.encode()).hexdigest()
        logger.info(f"Cacheable path detected, hash={request_hash}")

        # Try to get from cache
        try:
            response = table.get_item(Key={"requestHash": request_hash})
            if "Item" in response:
                cached_data = response["Item"]["data"]
                logger.info(f"Cache HIT for hash={request_hash}")
                return {
                    "statusCode": 200,
                    "body": cached_data,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Cache": "HIT",
                    },
                }
            logger.info(f"Cache MISS for hash={request_hash}")
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")

    # Make upstream request
    try:
        logger.info(f"Making upstream request to: {upstream_url}")
        req = urllib.request.Request(
            upstream_url, headers={"accept": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            data = response.read().decode("utf-8")
            logger.info(
                f"Upstream response: status={status_code}, data_length={len(data)}"
            )

            # Check if we should cache this response
            should_cache = should_cache_response(path, status_code, data)
            logger.info(f"Should cache response: {should_cache}")

            if should_cache:
                try:
                    table.put_item(
                        Item={
                            "requestHash": request_hash,
                            "data": data,
                        }
                    )
                    logger.info(f"Cached response for hash={request_hash}")
                except Exception as e:
                    logger.error(f"Cache write error: {e}")

            return {
                "statusCode": status_code,
                "body": data,
                "headers": {
                    "Content-Type": "application/json",
                    "X-Cache": "MISS",
                },
            }
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error from upstream: {e.code} - {e}")
        return {
            "statusCode": e.code,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"},
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"},
        }
