# import sqlite3
# import os

# db_path = os.path.join(os.path.dirname(__file__), 'stocksense.db')
# if not os.path.exists(db_path):
#     print(f"Database not found at {db_path}")
#     exit(1)

# try:
#     conn = sqlite3.connect(db_path)
#     cursor = conn.cursor()
#     # Check if column already exists
#     cursor.execute("PRAGMA table_info(prediction_logs)")
#     columns = [info[1] for info in cursor.fetchall()]
    
#     if "source" not in columns:
#         print("Adding 'source' column to prediction_logs...")
#         cursor.execute("ALTER TABLE prediction_logs ADD COLUMN source VARCHAR DEFAULT 'ensemble'")
#         conn.commit()
#         print("Successfully added 'source' column.")
#     else:
#         print("'source' column already exists.")
        
#     conn.close()
# except Exception as e:
#     print(f"Error updating database: {e}")
