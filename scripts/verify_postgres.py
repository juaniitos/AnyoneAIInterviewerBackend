from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.connect() as connection:
        dialect = connection.dialect.name
        print(f"dialect={dialect}")
        if dialect != "postgresql":
            print("warning=database is not PostgreSQL")
            return

        extension = connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        print(f"vector_extension={'enabled' if extension else 'missing'}")

        table_check = connection.execute(
            text(
                """
                SELECT data_type, udt_name
                FROM information_schema.columns
                WHERE table_name = 'questions' AND column_name = 'embedding'
                """
            )
        ).fetchone()
        if table_check:
            print(f"embedding_column={table_check[0]}/{table_check[1]}")
        else:
            print("embedding_column=missing")


if __name__ == "__main__":
    main()
