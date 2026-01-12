from database.connection import engine
from sqlalchemy import text

def run_migrations():
    with engine.connect() as conn:
        print("Running migrations...")
        
        # Helper to ignore error if column exists
        def add_column(table, col_def):
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
                print(f"Added {col_def} to {table}")
            except Exception as e:
                # SQLite throws specific error usually, or generic
                pass

        # MerchantMap
        add_column("merchant_maps", "created_at DATETIME")
        add_column("merchant_maps", "updated_at DATETIME")
        add_column("merchant_maps", "notes TEXT")
        add_column("merchant_maps", "is_active BOOLEAN DEFAULT 1")

        # CategoryMap
        add_column("category_maps", "source TEXT DEFAULT 'manual'")
        add_column("category_maps", "created_at DATETIME")
        add_column("category_maps", "updated_at DATETIME")
        add_column("category_maps", "is_active BOOLEAN DEFAULT 1")
        
        # Transaction
        add_column("transactions", "merchant_map_id INTEGER")
        add_column("transactions", "category_map_id INTEGER")
        
        conn.commit()
        print("Migrations complete.")

if __name__ == "__main__":
    run_migrations()
