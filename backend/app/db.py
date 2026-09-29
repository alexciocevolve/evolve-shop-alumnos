from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    # One session per request: opened here, closed automatically when the request ends.
    # Commits are NOT done here but in the services, which know which operations form a unit.
    with SessionLocal() as db:
        yield db
