# Cached Currency Rates

A caching proxy for currency rate APIs using AWS CDK.

## Architecture

- API Gateway v2 HTTP API
- Python Lambda function (Python 3.12)
- DynamoDB table for caching (2 RCU/WCU)

## Supported APIs

- `openexchangerates.org` - All endpoints
- `api.twelvedata.com` - All endpoints

Requests to other domains will return 403 Forbidden.

## Features

- Caches responses for:
  - `openexchangerates.org/api/historical/*`
  - `api.twelvedata.com/eod/*`
- Forwards all other requests without caching
- Uses request path + parameters hash as cache key
- Returns `X-Cache: HIT` or `X-Cache: MISS` headers

## Usage

Include the domain in the path:

```
https://your-api.execute-api.region.amazonaws.com/openexchangerates.org/api/historical/2025-01-01.json?app_id=xxx&base=USD&symbols=AUD
```

## Deployment

```bash
npx cdk deploy
```

The API URL will be output after deployment.
