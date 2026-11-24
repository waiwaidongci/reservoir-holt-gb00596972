import os
from pathlib import Path

DB_URL = os.environ['DATABASE_URL']
JWT_SECRET = os.environ['JWT_SECRET']
ARTIFACTS = Path(os.environ.get('ARTIFACT_DIR', '/artifacts'))
SEED_DEMO = os.environ.get('SEED_DEMO', 'true').lower() == 'true'
