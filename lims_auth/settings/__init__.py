import os
from dotenv import load_dotenv
import os 

load_dotenv()  # take environment variables from .env file


env = os.getenv("ENVIRONMENT", "development").lower()

if env == "production":
    from .production import *
else:
    from .development import *
    
