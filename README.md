# Quilting-Tools
A GUI Python application for quilting tools and utilities designed for Windows 11
Python + SQLite (stdlib only; Tkinter GUI) fabric inventory and panel cutting planner.

Run: `python app.py` · Test: `python -m unittest discover tests`

- Navigation buttons switch between Fabric, Panel, Dropdown and Helptext forms.
- DROPDOWN drives all dropdown lists (USE=0 hides a value; DEF=1 is the default; several defaults show an error and the last one wins).
- HELPTEXT gives hover text and full help (type `?` or press F1 in a field). Buttons use the screen name as RECORDNAME and button label as FIELDNAME.
- Panel: working size = dimension - 2*SEAMALLOWANCE. The planner splits the panel into equal (symmetric) cells, choosing the fewest seams, lists the cuts and draws the panel with FABRIC IDs. Approving a saved plan reduces the inventory.
