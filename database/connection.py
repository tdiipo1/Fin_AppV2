from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Define the database file path
DB_FOLDER = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(DB_FOLDER, "..", "finapp_v2.db")
DATABASE_URL = f"sqlite:///{DB_FILE}"

# Create the engine
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}, # Needed for SQLite
    echo=False # Set to True to see SQL queries in logs
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db():
    """Dependency to get a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize the database tables."""
    Base.metadata.create_all(bind=engine)
