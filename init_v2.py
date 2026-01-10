from database.connection import init_db
from database.models import Category, Transaction

if __name__ == "__main__":
    print("Initializing FinApp V2 Database...")
    init_db()
    print("Database initialized successfully at finapp_v2.db")
