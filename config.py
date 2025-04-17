from __future__ import annotations
import psycopg2
from typing import Final
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN: Final = os.getenv("TOKEN")

HOST: Final[str] = os.getenv("host")
PASSWORD: Final[str] = os.getenv("password")
NAME: Final[str] = os.getenv("dbname")
PORT: Final[int] = os.getenv("port")
USER: Final[str] = os.getenv("user")

# # Fetch variables
# USER = os.getenv("user")
# PASSWORD = os.getenv("password")
# HOST = os.getenv("host")
# PORT = os.getenv("port")
# DBNAME = os.getenv("dbname")

# # Connect to the database
# try:
#     connection = psycopg2.connect(
#         user=USER,
#         password=PASSWORD,
#         host=HOST,
#         port=PORT,
#         dbname=DBNAME
#     )
#     print("Connection successful!")
    
#     # Create a cursor to execute SQL queries
#     cursor = connection.cursor()
    
#     # Example query
#     cursor.execute("SELECT NOW();")
#     result = cursor.fetchone()
#     print("Current Time:", result)

#     # Close the cursor and connection
#     cursor.close()
#     connection.close()
#     print("Connection closed.")

# except Exception as e:
#     print(f"Failed to connect: {e}")