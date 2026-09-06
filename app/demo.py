"""Demo mode (GROCIOUS_DEMO=1): anonymised fixtures instead of Trumf/Rema tokens.

Same return shapes as trumf_data()/rema_data()/trumf_lines()/rema_lines() in webgui.py, so every
route and export renders without network or secrets. Offer activation flips the flag in memory.
"""

import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_state: dict = {}


def _load(name):
    if name not in _state:
        _state[name] = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    return _state[name]


def trumf_data():
    return copy.deepcopy(_load("trumf"))


_activated: set = set()


def rema_data():
    d = copy.deepcopy(_load("rema"))
    for o in d["offers"]:
        if o["code"] in _activated:
            o["activated"] = True
    return d


def trumf_lines(bid):
    p = FIXTURES / "lines" / f"trumf-{bid}.json"
    return json.loads(p.read_text("utf-8"))["lines"] if p.exists() else []


def rema_lines(tid):
    p = FIXTURES / "lines" / f"rema-{tid}.json"
    return json.loads(p.read_text("utf-8"))["lines"] if p.exists() else []


def rema_activate(code):
    _activated.add(code)


def clear():
    """Cache clear (what the routes call after an activation): reload fixtures, keep activations."""
    _state.clear()


def reset():
    """Tests: back to the pristine fixtures."""
    _state.clear()
    _activated.clear()


for _fn in (trumf_data, rema_data):
    _fn.clear = clear  # mirrors the @_cache API used by the routes
