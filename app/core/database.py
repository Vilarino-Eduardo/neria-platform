from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_FILE = DATA_DIR / "whatsapp.db"


class Database:

    def __init__(self):

        DATA_DIR.mkdir(exist_ok=True)

        self.connection = sqlite3.connect(
            DATABASE_FILE,
            check_same_thread=False,
            timeout=30
        )

        self.connection.row_factory = sqlite3.Row

        self.enable_foreign_keys()

        self.create_tables()


    def enable_foreign_keys(self):

        cursor = self.connection.cursor()

        cursor.execute(
            "PRAGMA foreign_keys = ON;"
        )

        self.connection.commit()


    def create_tables(self):

        cursor = self.connection.cursor()

        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL,

                slug TEXT UNIQUE,

                active INTEGER DEFAULT 1,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            );


            CREATE TABLE IF NOT EXISTS client_settings (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                client_id INTEGER NOT NULL,

                company_name TEXT,

                welcome_message TEXT,

                phone TEXT,

                email TEXT,

                address TEXT,

                opening_hours TEXT,

                primary_color TEXT,

                secondary_color TEXT,

                logo TEXT,

                ai_enabled INTEGER DEFAULT 0,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP,

                FOREIGN KEY(client_id)
                    REFERENCES clients(id)

            );


            CREATE TABLE IF NOT EXISTS categories (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                client_id INTEGER,

                name TEXT,

                active INTEGER DEFAULT 1,

                sort_order INTEGER DEFAULT 0,

                FOREIGN KEY(client_id)
                    REFERENCES clients(id)

            );


            CREATE TABLE IF NOT EXISTS products (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                client_id INTEGER,

                category_id INTEGER,

                name TEXT,

                description TEXT,

                price REAL,

                stock INTEGER,

                active INTEGER DEFAULT 1,

                FOREIGN KEY(client_id)
                    REFERENCES clients(id),

                FOREIGN KEY(category_id)
                    REFERENCES categories(id)

            );


            CREATE TABLE IF NOT EXISTS conversations (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                client_id INTEGER,

                phone TEXT,

                user_message TEXT,

                bot_response TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            );


            CREATE TABLE IF NOT EXISTS sessions (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                client_id INTEGER,

                phone TEXT UNIQUE,

                state TEXT,

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            );


            CREATE TABLE IF NOT EXISTS tickets (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                client_id INTEGER,

                protocol TEXT UNIQUE,

                phone TEXT,

                status TEXT,

                assigned_to TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP,

                closed_at TIMESTAMP

            );


            CREATE TABLE IF NOT EXISTS faq (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                client_id INTEGER,

                question TEXT,

                answer TEXT,

                keywords TEXT,

                active INTEGER DEFAULT 1

            );


            CREATE TABLE IF NOT EXISTS plugins (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT UNIQUE,

                description TEXT

            );


            CREATE TABLE IF NOT EXISTS client_plugins (

                client_id INTEGER,

                plugin_id INTEGER,

                PRIMARY KEY(client_id, plugin_id),

                FOREIGN KEY(client_id)
                    REFERENCES clients(id),

                FOREIGN KEY(plugin_id)
                    REFERENCES plugins(id)

            );
            """
        )

        self.connection.commit()


    def get_connection(self):

        return self.connection


    def close(self):

        if self.connection:

            self.connection.close()



database = Database()