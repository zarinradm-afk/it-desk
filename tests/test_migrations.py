from sqlalchemy import create_engine, inspect, text

from app.migrations import migrate_schema


def test_legacy_schema_gets_new_columns_without_losing_data():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50))"))
        connection.execute(text("CREATE TABLE tickets (id INTEGER PRIMARY KEY, title VARCHAR(200))"))
        connection.execute(text("INSERT INTO users (id, username) VALUES (1, 'ali')"))
        connection.execute(text("INSERT INTO tickets (id, title) VALUES (1, 'Printer')"))
    migrate_schema(engine)
    columns = {table: {c["name"] for c in inspect(engine).get_columns(table)} for table in ("users", "tickets")}
    assert "is_active" in columns["users"]
    assert "asset_id" in columns["tickets"]
    assert "due_at" in columns["tickets"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT username FROM users WHERE id=1")).scalar_one() == "ali"
        assert connection.execute(text("SELECT title FROM tickets WHERE id=1")).scalar_one() == "Printer"
