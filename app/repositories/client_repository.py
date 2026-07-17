from app.core.database import database


class ClientRepository:

    def __init__(self):

        self.connection = database.get_connection()


    def create(
        self,
        name,
        slug
    ):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO clients (
                name,
                slug
            )
            VALUES (?, ?)
            """,
            (
                name,
                slug
            )
        )

        self.connection.commit()

        return cursor.lastrowid


    def get_by_slug(
        self,
        slug
    ):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM clients
            WHERE slug = ?
            """,
            (
                slug,
            )
        )

        return cursor.fetchone()


    def get_all(self):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM clients
            ORDER BY id
            """
        )

        return cursor.fetchall()


    def exists(
        self,
        slug
    ):

        client = self.get_by_slug(slug)

        return client is not None


client_repository = ClientRepository()