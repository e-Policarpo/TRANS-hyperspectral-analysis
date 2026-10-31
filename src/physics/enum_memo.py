"""What an enumeration computed that the next one can use unchanged.

:meth:`~src.physics.designer.Designer.enumerate_solutions` does two kinds of
work, and neither depends on the search RANGE:

* a lattice node's score is ``objective(node, p)``, and the objective reads
  only the targets, the mass and the model settings — never ``Lmin``,
  ``Lmax``, the per-dimension box or the tolerance;
* a refinement is L-BFGS-B from the node inside its own one-step cell
  (:meth:`~src.physics.designer.Designer.refinement_box`), deterministic, a
  function of the node, the cell and the same settings.

So when the range changes, every node and every cell that is the same as
before has the same answer as before, bit for bit, and only the new ones need
computing. Raising ``Lmax`` keeps every node (the lattice is anchored at the
bottom of the range and each node is computed from its index, so ``k`` gives
the same float at any ceiling); only the nodes whose cell the old ceiling
clipped are refined again, because their cell is different. Changing ``Lmin``
moves every node, and nothing is reused — not a special case, just a cache
that misses.

The sampled search (:meth:`find_solutions`) is NOT memoised and cannot be:
differential evolution spreads its population over the whole box and the
analytical starts descend inside it, so every one of its results depends on
the range.

Keys are the content, never a name: the settings the objective could read
(:func:`objective_key`), the node, the cell. A memo can therefore never hand
back an answer to a different question — different peaks or a different
model are a different key and simply miss.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Optional, Tuple

import numpy as np

#: Settings that decide which nodes exist, which are refined and which
#: results are kept — but not what any one node or refinement computes.
#: Everything NOT listed here is part of the key, so a setting added later
#: is safe by default (it can only cost hits, never give a wrong answer).
#: Verified against every field the objective path reads: Et, meff, ndim,
#: coords, sym, fixed, match, priority, assign.
RANGE_ONLY = frozenset({
    'Lmin', 'Lmax', 'box', 'tol', 'maxsol', 'enum_polish', 'enum_max_nodes',
    'dup_rel', 'reject_unresolvable', 'resolution_meV', 'temperature_K',
    'seed_aspect', 'share_mass_search', 'label',
})

UNKNOWN, OK, FAILED = 0, 1, 2


def _canon(value):
    """A hashable, exact stand-in for a parameter value."""
    if isinstance(value, np.ndarray):
        return ('array', value.dtype.str, value.shape,
                tuple(value.ravel().tolist()))
    if isinstance(value, dict):
        return ('dict', tuple(sorted((str(k), _canon(v))
                                     for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return ('seq', tuple(_canon(v) for v in value))
    if isinstance(value, np.generic):
        return value.item()
    return value


def objective_key(p: dict):
    """Everything in ``p`` an objective evaluation could depend on."""
    return tuple(sorted((k, _canon(v)) for k, v in p.items()
                        if k not in RANGE_ONLY))


class _Grid:
    """Scores of one geometric lattice, indexed by node number per axis."""

    def __init__(self, shape):
        self.value = np.zeros(shape)
        self.state = np.zeros(shape, dtype=np.int8)

    def grow(self, shape) -> None:
        if all(n <= m for n, m in zip(shape, self.value.shape)):
            return
        new = tuple(max(n, m) for n, m in zip(shape, self.value.shape))
        value, state = np.zeros(new), np.zeros(new, dtype=np.int8)
        old = tuple(slice(0, m) for m in self.value.shape)
        value[old], state[old] = self.value, self.state
        self.value, self.state = value, state


class EnumerationMemo:
    """Node scores and refinements, kept across runs, keyed by content.

    Bounded: at most ``max_keys`` distinct searches (targets x mass x model)
    are kept, least recently used dropped first. One search at the default
    lattice is ~9 kB of scores plus its few dozen refinements.
    """

    def __init__(self, max_keys: int = 256):
        self.max_keys = int(max_keys)
        self._store: "OrderedDict[tuple, dict]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._store)

    def _entry(self, key) -> dict:
        entry = self._store.get(key)
        if entry is None:
            entry = {'grids': {}, 'refine': {}}
            self._store[key] = entry
            while len(self._store) > self.max_keys:
                self._store.popitem(last=False)
        else:
            self._store.move_to_end(key)
        return entry

    def grid(self, key, anchor: Tuple, shape: Tuple[int, ...]) -> _Grid:
        """The score grid for lattices starting at ``anchor``, at least ``shape``.

        ``anchor`` is ``(lows per axis, nodes per octave)`` — the two things
        that fix where node ``k`` is.
        """
        grids: Dict = self._entry(key)['grids']
        grid = grids.get(anchor)
        if grid is None:
            grid = grids[anchor] = _Grid(shape)
        else:
            grid.grow(shape)
        return grid

    def refinement(self, key, node, box) -> Tuple[bool, Optional[tuple]]:
        """``(found, (fun, x) or None)`` for a node refined in ``box``."""
        refine = self._entry(key)['refine']
        rkey = (tuple(node), tuple(map(tuple, box)))
        if rkey in refine:
            self.hits += 1
            return True, refine[rkey]
        self.misses += 1
        return False, None

    def store_refinement(self, key, node, box, out) -> None:
        if out is not None:
            out = (out[0], np.array(out[1], copy=True))
        self._entry(key)['refine'][(tuple(node), tuple(map(tuple, box)))] = out
