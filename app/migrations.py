from sqlalchemy import Engine, inspect, text


def _columns(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def migrate_schema(engine: Engine) -> None:
    """Apply additive SQLite changes needed by versions after the MVP.

    `create_all` creates missing tables but does not add columns to tables that
    already exist. These changes are deliberately additive and idempotent.
    """
    inspector = inspect(engine)
    with engine.begin() as connection:
        if "users" in inspector.get_table_names() and "is_active" not in _columns(engine, "users"):
            connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        if "tickets" in inspector.get_table_names() and "asset_id" not in _columns(engine, "tickets"):
            connection.execute(text("ALTER TABLE tickets ADD COLUMN asset_id INTEGER"))
        if "tickets" in inspector.get_table_names() and "due_at" not in _columns(engine, "tickets"):
            connection.execute(text("ALTER TABLE tickets ADD COLUMN due_at DATETIME"))
        if "tickets" in inspector.get_table_names():
            columns = {column["name"] for column in inspect(connection).get_columns("tickets")}
            if "category" not in columns:
                connection.execute(text("ALTER TABLE tickets ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'other'"))
            if "intake" not in columns:
                connection.execute(text("ALTER TABLE tickets ADD COLUMN intake VARCHAR(12) NOT NULL DEFAULT 'form'"))
            if "closed_at" not in columns:
                connection.execute(text("ALTER TABLE tickets ADD COLUMN closed_at DATETIME"))
        if "assets" in inspector.get_table_names() and "location" not in _columns(engine, "assets"):
            connection.execute(text("ALTER TABLE assets ADD COLUMN location VARCHAR(120)"))
