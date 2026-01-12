# import psutil
# import os

# def get_memory_usage():
#     process = psutil.Process(os.getpid())
#     # Convert bytes to Megabytes
#     mem_mb = process.memory_info().rss / (1024 * 1024)
#     return f"{mem_mb:.2f} MB"

# print(f"Initial Django Memory: {get_memory_usage()}")
# # You can call this function inside a Django view to see memory spikes


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