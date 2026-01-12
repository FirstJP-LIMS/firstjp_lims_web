"""
    Preparing Project for Deployment
        - Calculate Django Memory for running the settings file...
        Based on your 62.31 MB baseline, here is the math for a standard setup:
        - OS & System Services: ~350 MB (Linux needs this just to stay alive).
        - 3 Gunicorn Workers: 62.31MB * 3 = 186.93MB 
        - Database (Postgres/MySQL): ~200 MB (If hosted on the same instance).
        - Buffer for "Spikes": ~200 MB (When you run a heavy query or export data).
    Total Estimated Usage: 937MB    
"""
import os
import psutil
import django

# 1. Point to your settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_auth.settings') 
# Change 'config' to your project name

# 2. Load Django
django.setup()

def get_memory_usage():
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / (1024 * 1024)
    return f"{mem_mb:.2f} MB"

print(f"Full Django Load Memory: {get_memory_usage()}")