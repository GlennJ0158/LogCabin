"""Program startup: create schema, seed DropDown and HelpText."""
from . import dropdown, helptext
from .db import connect


def startup(path=":memory:"):
    conn = connect(path)
    dropdown.seed(conn)
    helptext.seed(conn)
    return conn
