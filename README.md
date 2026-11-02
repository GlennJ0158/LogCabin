# Quilting-Tools
A GUI Python application for quilting tools and utilities designed for Windows 11
Python + SQLite (stdlib only; Tkinter GUI) fabric inventory and panel cutting planner.

Run: `python app.py` · Test: `python -m unittest discover tests`

- Navigation buttons switch between Fabric, Panel, Dropdown and Helptext forms.
- DROPDOWN drives all dropdown lists (USE=0 hides a value; DEF=1 is the default; several defaults show an error and the last one wins).
- HELPTEXT gives hover text and full help (press F1 in a field). Buttons use the screen name as RECORDNAME and button label as FIELDNAME.
- Panel: working size = dimension - 2*SEAMALLOWANCE. The planner splits the panel into equal (symmetric) cells, choosing the fewest seams, lists the cuts and draws the panel with FABRIC IDs. Approving a saved plan reduces the inventory.
- Log Cabin: the "Log Cabin" button opens a separate window to define, save, load and delete patterns (dimensions in inches). Patterns hold a centre square, a block size (BlockWidth x BlockLength, finished inches) and ordered strips (Side, Color, Width) that must close exactly to that size; "Fill Strips" generates Classic, Reverse Classic or Courthouse Steps rings. A non-square block asks for confirmation on save, with a "Don't ask me again" option. Cut List gives finished and cut sizes (seam allowance added to every edge); Quilt Summary totals a grid of identical blocks (Blocks across x Blocks down) and gives the finished quilt size. "Classic Log Cabin" (2.5 in centre, 4 rings of 1.25 in) is stored as an example.
