from django.core.cache import cache

cache.set("greeting", "Hello from Redis!", timeout=60)
print(cache.get("greeting"))  # should print "Hello from Redis!"



if ENVIRONMENT == "production":
    # Production with Redis
    REDIS_URL = os.getenv('REDIS_URL')  # From Render or external provider
    
    if REDIS_URL:
        # Using REDIS_URL (preferred for Render)
        CACHES = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": REDIS_URL,
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    "SOCKET_CONNECT_TIMEOUT": 5,  # Timeout if Redis is down
                    "SOCKET_TIMEOUT": 5,
                    "RETRY_ON_TIMEOUT": True,
                    "MAX_CONNECTIONS": 50,  # Connection pool size
                    "CONNECTION_POOL_KWARGS": {
                        "max_connections": 50,
                        "retry_on_timeout": True,
                    },
                    # Optional: Add compression for large objects
                    # "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
                },
                "KEY_PREFIX": "lims",  # Prefix all keys with 'lims:'
                "TIMEOUT": 900,  # Default timeout: 15 minutes
            }
        }
    else:
        # Fallback to local memory if Redis not configured
        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "lims-fallback-cache",
            }
        }
else:
    # Development - use local memory cache
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "lims-dev-cache",
            "OPTIONS": {
                "MAX_ENTRIES": 2000,
            }
        }
    }
