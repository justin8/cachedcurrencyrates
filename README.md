# Cached Currency Rates

A caching proxy for the OpenExchangeRates API using AWS CDK.

## Architecture

- API Gateway v2 HTTP API
- Python Lambda function (Python 3.12)
- DynamoDB table for caching (2 RCU/WCU)

## Features

- Caches responses for `/api/historical/*` endpoints
- Forwards all other requests without caching
- Uses request path + parameters hash as cache key
- Returns `X-Cache: HIT` or `X-Cache: MISS` headers

## Deployment

```bash
npx cdk deploy
```

The API URL will be output after deployment.
