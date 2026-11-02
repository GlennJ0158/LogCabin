"""Database connection and schema. Every table has an automatic, required ID."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS HelpText (
    ID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    TableName TEXT NOT NULL, FieldName TEXT NOT NULL,
    HoverText TEXT NOT NULL DEFAULT 'No Tool Tip',
    FullText TEXT NOT NULL DEFAULT 'No help yet',
    RT INTEGER NOT NULL DEFAULT 0, Use INTEGER NOT NULL DEFAULT 1,
    UNIQUE (TableName, FieldName));
CREATE TABLE IF NOT EXISTS DropDown (
    ID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    TableName TEXT NOT NULL, FieldName TEXT NOT NULL, ListItem TEXT NOT NULL,
    Def INTEGER NOT NULL DEFAULT 0, Use INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS Fabric (
    ID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    FabricName TEXT NOT NULL, Color TEXT, Shade TEXT, Pattern TEXT, Type TEXT,
    Grain TEXT, Length REAL NOT NULL DEFAULT 0 CHECK (Length >= 0),
    Width REAL NOT NULL DEFAULT 0 CHECK (Width >= 0), SqIn REAL NOT NULL DEFAULT 0,
    Use INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS Selection (
    ID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    SelectionName TEXT NOT NULL UNIQUE, TableName TEXT NOT NULL,
    RowCount INTEGER NOT NULL DEFAULT 0,
    Created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS SelectedRows (
    ID INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    SelectionID INTEGER NOT NULL REFERENCES Selection(ID) ON DELETE CASCADE,
    RowID INTEGER NOT NULL, UNIQUE (SelectionID, RowID));
"""


def connect(path=":memory:"):
    """Open a connection, enable foreign keys and create the schema."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def table_fields(conn, table):
    """Return field names of a table (hierarchical choice: only fields in that table)."""
    if table not in tables(conn):
        raise ValueError(f"TableName: unknown table '{table}'")
    return [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def tables(conn):
    """Return user table names."""
    return [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
