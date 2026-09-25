import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()  # finds .env by walking up from this file, so it works from any directory
DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    # One session per request: opened here, closed automatically when the request ends.
    # Commits are NOT done here but in the services, which know which operations form a unit.
    with SessionLocal() as db:
        yield db
