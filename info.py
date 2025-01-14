import re
from os import environ

id_pattern = re.compile(r'^.\d+$')

# Bot information
SESSION = environ.get('SESSION', 'FileToLink')
API_ID = int(environ.get('API_ID', '20836266'))
API_HASH = environ.get('API_HASH', 'bbdd206f92e1ca4bc4935b43dfd4a2a1')
BOT_TOKEN = environ.get('BOT_TOKEN', "")

# Bot settings
PORT = environ.get("PORT", "8080")

# Image URL for the start command
START_IMAGE_URL = environ.get("START_IMAGE_URL", "https://envs.sh/vp4.jpg")

# Online Stream and Download
MULTI_CLIENT = False
SLEEP_THRESHOLD = int(environ.get('SLEEP_THRESHOLD', '60'))
PING_INTERVAL = int(environ.get("PING_INTERVAL", "1200"))  # 20 minutes
ON_HEROKU = 'DYNO' in environ

# URL for the bot (should be set in environment variables)
URL = environ.get("URL", "")

# Admins, Channels & Users
LOG_CHANNEL = int(environ.get('LOG_CHANNEL', '-1002441553603'))
ADMINS = [int(admin) if id_pattern.search(admin) else admin for admin in environ.get('ADMINS', '7577977996').split()]
AUTH_CHANNEL = [int(ch) if id_pattern.search(ch) else ch for ch in environ.get('AUTH_CHANNEL', '-1002393199149 -1002298889599').split()]

# MongoDB information
DATABASE_URI = environ.get('DATABASE_URI', "mongodb+srv://cristi7jjr:tRjSVaoSNQfeZ0Ik@cluster0.kowid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
DATABASE_NAME = environ.get('DATABASE_NAME', "FileToLink")

# Shortlink Info
SHORTLINK = bool(environ.get('SHORTLINK', False))
SHORTLINK_URL = environ.get('SHORTLINK_URL', 'api.shareus.io')
SHORTLINK_API = environ.get('SHORTLINK_API', 'hRPS5vvZc0OGOEUQJMJzPiojoVK2')
