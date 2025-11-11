import json
import hashlib
import os
import urllib.request
import urllib.parse
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

UPSTREAM_BASE = "https://openexchangerates.org"

def handler(event, context):
    path = event.get("rawPath", "/")
    query_params = event.get("queryStringParameters") or {}
    
    # Build full upstream URL
    query_string = urllib.parse.urlencode(query_params)
    full_path = f"{path}?{query_string}" if query_string else path
    upstream_url = f"{UPSTREAM_BASE}{full_path}"
    
    # Check if this is a cacheable path
    should_cache = path.startswith("/api/historical/")
    
    if should_cache:
        # Generate hash for cache key
        request_hash = hashlib.sha256(full_path.encode()).hexdigest()
        
        # Try to get from cache
        try:
            response = table.get_item(Key={'requestHash': request_hash})
            if 'Item' in response:
                cached_data = response['Item']['data']
                return {
                    'statusCode': 200,
                    'body': cached_data,
                    'headers': {
                        'Content-Type': 'application/json',
                        'X-Cache': 'HIT',
                    },
                }
        except Exception as e:
            print(f"Cache lookup error: {e}")
    
    # Make upstream request
    try:
        req = urllib.request.Request(
            upstream_url,
            headers={'accept': 'application/json'}
        )
        with urllib.request.urlopen(req) as response:
            data = response.read().decode('utf-8')
            
            # Cache if applicable
            if should_cache:
                try:
                    table.put_item(Item={
                        'requestHash': request_hash,
                        'data': data,
                    })
                except Exception as e:
                    print(f"Cache write error: {e}")
            
            return {
                'statusCode': 200,
                'body': data,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Cache': 'MISS',
                },
            }
    except urllib.error.HTTPError as e:
        return {
            'statusCode': e.code,
            'body': json.dumps({'error': str(e)}),
            'headers': {'Content-Type': 'application/json'},
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {'Content-Type': 'application/json'},
        }
