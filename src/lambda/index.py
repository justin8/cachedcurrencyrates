import json
import hashlib
import os
import urllib.request
import urllib.parse
import boto3

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


def is_cacheable(path):
    """Check if the path should be cached."""
    path_clean = path.lstrip("/")
    return any(path_clean.startswith(pattern) for pattern in CACHEABLE_PATHS)


def handler(event, context):
    path = event.get("rawPath", "/")
    query_params = event.get("queryStringParameters") or {}

    # Validate domain is allowed
    if not is_allowed_domain(path):
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Domain not allowed"}),
            "headers": {"Content-Type": "application/json"},
        }

    # Build full upstream URL (path includes domain)
    query_string = urllib.parse.urlencode(query_params)
    full_path = f"{path}?{query_string}" if query_string else path
    upstream_url = f"https:/{full_path}"

    # Check if this is a cacheable path
    should_cache = is_cacheable(path)

    if should_cache:
        # Generate hash for cache key
        request_hash = hashlib.sha256(full_path.encode()).hexdigest()

        # Try to get from cache
        try:
            response = table.get_item(Key={"requestHash": request_hash})
            if "Item" in response:
                cached_data = response["Item"]["data"]
                return {
                    "statusCode": 200,
                    "body": cached_data,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Cache": "HIT",
                    },
                }
        except Exception as e:
            print(f"Cache lookup error: {e}")

    # Make upstream request
    try:
        req = urllib.request.Request(
            upstream_url, headers={"accept": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            data = response.read().decode("utf-8")

            # Only cache if the response is successful or no data
            if should_cache and status_code in (200, 400):
                try:
                    table.put_item(
                        Item={
                            "requestHash": request_hash,
                            "data": data,
                        }
                    )
                except Exception as e:
                    print(f"Cache write error: {e}")

            return {
                "statusCode": status_code,
                "body": data,
                "headers": {
                    "Content-Type": "application/json",
                    "X-Cache": "MISS",
                },
            }
    except urllib.error.HTTPError as e:
        return {
            "statusCode": e.code,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"},
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"},
        }
