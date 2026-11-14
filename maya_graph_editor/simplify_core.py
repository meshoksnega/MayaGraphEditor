"""Curve simplification maths (numpy only, no bpy).

Idea
----
Keys are removed one at a time, always the one whose removal changes the curve
least, measured against the *original* curve with a model of how Blender
evaluates the reduced curve (auto-handles included).  Because the removal
order doesn't depend on the tolerance, it is computed once; the live slider
then only chooses how long a prefix of that order to apply, which is instant.

`cum_error[j]` is the worst deviation after removing the first j+1 keys, so
"tolerance t" == "remove while cum_error <= t".

Handle model (validated against Blender, see tests/test_simplify_model.py)
-------------------------------------------------------------------------
* auto smoothing "None": Blender's local formula, reproduced exactly.
* auto smoothing "Continuous Acceleration" (Blender's default): handles at
  1/3 of the neighbouring segments, y chosen so the curve has continuous
  second derivative (a natural cubic spline).  End keys and clamped extremes
  are flat; clamped handles may not pass the neighbouring key value.  The
  global solve is approximated by a small window around the removed key (the
  influence of a key decays geometrically along the curve).
"""

import heapq

import numpy as np

# handle types
FREE, ALIGNED, VECTOR, AUTO, AUTO_CLAMPED = range(5)
HANDLE_CODES = {'FREE': FREE, 'ALIGNED': ALIGNED, 'VECTOR': VECTOR,
                'AUTO': AUTO, 'AUTO_CLAMPED': AUTO_CLAMPED}
# interpolation
BEZIER, LINEAR, CONSTANT = range(3)
_T = np.linspace(0.0, 1.0, 49)
WINDOW = 2  # keys on each side of the removed key that are re-solved


class Curve:
    """Array view of the keys of one F-Curve."""

    def __init__(self, co, hl, hr, hl_type, hr_type, ipo, flat_ends=True,
                 smoothing='CONT_ACCEL'):
        self.x, self.y = co[:, 0], co[:, 1]
        self.hlx, self.hly = hl[:, 0], hl[:, 1]
        self.hrx, self.hry = hr[:, 0], hr[:, 1]
        self.lt = hl_type
        self.rt = hr_type
        self.ipo = ipo
        self.flat_ends = flat_ends
        self.smoothing = 'NONE' if smoothing == 'NONE' else 'CONT_ACCEL'
        self.n = len(self.x)

    def is_auto(self, k):
        return self.lt[k] in (AUTO, AUTO_CLAMPED) and self.rt[k] in (AUTO, AUTO_CLAMPED)


# --------------------------------------------------------------------------
# Auto smoothing "None": Blender's local handle formula
# --------------------------------------------------------------------------

def key_handles(c, k, p, n):
    """Handles (hlx, hly, hrx, hry) of key k whose neighbours are p, n (-1: none).

    Mimics Blender's BKE_nurb_handle_calc for F-Curves; handles of FREE /
    ALIGNED keys are kept as stored.
    """
    lt, rt = c.lt[k], c.rt[k]
    hlx, hly, hrx, hry = c.hlx[k], c.hly[k], c.hrx[k], c.hry[k]
    auto_l = lt in (AUTO, AUTO_CLAMPED)
    auto_r = rt in (AUTO, AUTO_CLAMPED)
    px, py = c.x[k], c.y[k]
    if (not auto_l and not auto_r and lt != VECTOR and rt != VECTOR) or (p < 0 and n < 0):
        return hlx, hly, hrx, hry

    if lt == VECTOR and p >= 0:
        hlx, hly = px + (c.x[p] - px) / 3.0, py + (c.y[p] - py) / 3.0
    if rt == VECTOR and n >= 0:
        hrx, hry = px + (c.x[n] - px) / 3.0, py + (c.y[n] - py) / 3.0

    if auto_l or auto_r:
        if p < 0:
            qx, qy = 2 * px - c.x[n], 2 * py - c.y[n]
        else:
            qx, qy = c.x[p], c.y[p]
        if n < 0:
            rx, ry = 2 * px - qx, 2 * py - qy
        else:
            rx, ry = c.x[n], c.y[n]
        dax, day = px - qx, py - qy
        dbx, dby = rx - px, ry - py
        len_a = dax if dax != 0 else 1.0
        len_b = dbx if dbx != 0 else 1.0
        tx = dbx / len_b + dax / len_a
        ty = dby / len_b + day / len_a
        length = tx * 2.5614
        if length != 0.0:
            if len_a > 5.0 * len_b:
                len_a = 5.0 * len_b
            if len_b > 5.0 * len_a:
                len_b = 5.0 * len_a
            lviol = rviol = False
            both = p >= 0 and n >= 0
            yd1 = c.y[p] - py if p >= 0 else 0.0
            yd2 = c.y[n] - py if n >= 0 else 0.0
            extremum = (yd1 <= 0 and yd2 <= 0) or (yd1 >= 0 and yd2 >= 0)
            if auto_l:
                f = len_a / length
                hlx, hly = px - tx * f, py - ty * f
                if lt == AUTO_CLAMPED and both:
                    if extremum:
                        hly, lviol = py, True
                    elif yd1 <= 0:
                        if c.y[p] > hly:
                            hly, lviol = c.y[p], True
                    elif c.y[p] < hly:
                        hly, lviol = c.y[p], True
            if auto_r:
                f = len_b / length
                hrx, hry = px + tx * f, py + ty * f
                if rt == AUTO_CLAMPED and both:
                    if extremum:
                        hry, rviol = py, True
                    elif yd2 <= 0:
                        if c.y[n] > hry:
                            hry, rviol = c.y[n], True
                    elif c.y[n] < hry:
                        hry, rviol = c.y[n], True
            if lviol != rviol:  # keep the handle pair collinear
                if lviol and hlx != px:
                    hry = py + (py - hly) * (hrx - px) / (px - hlx)
                elif rviol and hrx != px:
                    hly = py + (py - hry) * (hlx - px) / (px - hrx)
        # first / last auto key: flat when extrapolation is constant
        if c.flat_ends and (p < 0 or n < 0) and (auto_l or auto_r):
            hly = hry = py
    return hlx, hly, hrx, hry


# --------------------------------------------------------------------------
# Segment evaluation
# --------------------------------------------------------------------------

def _eval_segment(x0, y0, x1, y1, h_r, h_l, ipo, xs):
    """Evaluate one segment at sample positions xs (x0 <= xs < x1)."""
    if ipo == CONSTANT:
        return np.full_like(xs, y0)
    if ipo == LINEAR or x1 - x0 < 1e-9:
        return y0 + (y1 - y0) * (xs - x0) / max(x1 - x0, 1e-9)
    # Blender's handle correction: handles may not overlap on x
    a = max(h_r[0] - x0, 0.0)
    b = max(x1 - h_l[0], 0.0)
    span = x1 - x0
    if a + b > span:
        f = span / (a + b)
        a, b = a * f, b * f
        h_r = (x0 + a, y0 + (h_r[1] - y0) * f)
        h_l = (x1 - b, y1 + (h_l[1] - y1) * f)
    else:
        h_r = (x0 + a, h_r[1])
        h_l = (x1 - b, h_l[1])
    t = _T
    u = 1.0 - t
    b0, b1, b2, b3 = u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3
    bx = b0 * x0 + b1 * h_r[0] + b2 * h_l[0] + b3 * x1
    by = b0 * y0 + b1 * h_r[1] + b2 * h_l[1] + b3 * y1
    return np.interp(xs, bx, by)


# --------------------------------------------------------------------------
# Planner
# --------------------------------------------------------------------------

class Planner:
    def __init__(self, curve, removable, xs, ys):
        self.c = curve
        self.removable = removable
        self.xs, self.ys = xs, ys  # dense samples of the original curve
        n = curve.n
        self.prev = list(range(-1, n - 1))
        self.next = list(range(1, n)) + [-1]
        # current handle slopes (dy/dx), read from Blender's own handles
        dxl = curve.x - curve.hlx
        dxr = curve.hrx - curve.x
        with np.errstate(divide='ignore', invalid='ignore'):
            self.sl = np.where(dxl > 1e-9, (curve.y - curve.hly) / dxl, 0.0)
            self.sr = np.where(dxr > 1e-9, (curve.hry - curve.y) / dxr, 0.0)

    # ---- handles of the keys of a chain ------------------------------------
    def _chain_around(self, p, n):
        left, k = [p], p
        for _ in range(WINDOW):
            k = self.prev[k]
            if k < 0:
                break
            left.append(k)
        right, k = [n], n
        for _ in range(WINDOW):
            k = self.next[k]
            if k < 0:
                break
            right.append(k)
        return left[::-1] + right

    def _chain_handles(self, chain):
        c = self.c
        m = len(chain)
        if c.smoothing == 'NONE':
            out = {}
            for j, k in enumerate(chain):
                pp = chain[j - 1] if j > 0 else self.prev[k]
                nn = chain[j + 1] if j < m - 1 else self.next[k]
                out[k] = key_handles(c, k, pp, nn)
            return out

        x = c.x[chain]
        y = c.y[chain]
        fixed = np.zeros(m, bool)
        sl = np.zeros(m)
        sr = np.zeros(m)
        out = {}
        for j, k in enumerate(chain):
            at_end = self.prev[k] < 0 or self.next[k] < 0
            if j == 0 or j == m - 1 or not c.is_auto(k):
                fixed[j] = True
                sl[j], sr[j] = self.sl[k], self.sr[k]
                if c.is_auto(k) and at_end and c.flat_ends:
                    sl[j] = sr[j] = 0.0
            elif at_end:
                fixed[j] = True
                if c.flat_ends:
                    sl[j] = sr[j] = 0.0
                else:
                    sl[j], sr[j] = self.sl[k], self.sr[k]
            elif c.lt[k] == AUTO_CLAMPED or c.rt[k] == AUTO_CLAMPED:
                a, b = y[j - 1] - y[j], y[j + 1] - y[j]
                if (a <= 0 and b <= 0) or (a >= 0 and b >= 0):
                    fixed[j] = True  # clamped extremum: flat

        unknown = [j for j in range(m) if not fixed[j]]
        if unknown:
            idx = {j: i for i, j in enumerate(unknown)}
            A = np.zeros((len(unknown), len(unknown)))
            r = np.zeros(len(unknown))
            for j in unknown:
                i = idx[j]
                h0, h1 = x[j] - x[j - 1], x[j + 1] - x[j]
                d0, d1 = (y[j] - y[j - 1]) / h0, (y[j + 1] - y[j]) / h1
                A[i, i] = 2.0 * (h0 + h1)
                r[i] = 3.0 * (h1 * d0 + h0 * d1)
                if (j - 1) in idx:
                    A[i, idx[j - 1]] = h1
                else:
                    r[i] -= h1 * sr[j - 1]
                if (j + 1) in idx:
                    A[i, idx[j + 1]] = h0
                else:
                    r[i] -= h0 * sl[j + 1]
            sol = np.linalg.solve(A, r)
            for j in unknown:
                sl[j] = sr[j] = sol[idx[j]]

        for j, k in enumerate(chain):
            pk = chain[j - 1] if j > 0 else self.prev[k]
            nk = chain[j + 1] if j < m - 1 else self.next[k]
            if not c.is_auto(k):
                out[k] = self._stored_or_vector(k, pk, nk)
                continue
            # auto handles always span a third of the *current* neighbours
            h0 = c.x[k] - c.x[pk] if pk >= 0 else (c.x[nk] - c.x[k] if nk >= 0 else 1.0)
            h1 = c.x[nk] - c.x[k] if nk >= 0 else h0
            kx, ky = c.x[k], c.y[k]
            hlx_, hrx_ = kx - h0 / 3.0, kx + h1 / 3.0
            hly_ = ky - sl[j] * h0 / 3.0
            hry_ = ky + sr[j] * h1 / 3.0
            if (not fixed[j]) and (c.lt[k] == AUTO_CLAMPED or c.rt[k] == AUTO_CLAMPED):
                lv = rv = False
                yd1, yd2 = c.y[pk] - ky, c.y[nk] - ky
                if yd1 <= 0:
                    if c.y[pk] > hly_:
                        hly_, lv = c.y[pk], True
                elif c.y[pk] < hly_:
                    hly_, lv = c.y[pk], True
                if yd2 <= 0:
                    if c.y[nk] > hry_:
                        hry_, rv = c.y[nk], True
                elif c.y[nk] < hry_:
                    hry_, rv = c.y[nk], True
                if lv != rv:
                    if lv and hlx_ != kx:
                        hry_ = ky + (ky - hly_) * (hrx_ - kx) / (kx - hlx_)
                    elif rv and hrx_ != kx:
                        hly_ = ky + (ky - hry_) * (hlx_ - kx) / (kx - hrx_)
            out[k] = (hlx_, hly_, hrx_, hry_)
        return out

    def _stored_or_vector(self, k, pk, nk):
        c = self.c
        hlx, hly, hrx, hry = c.hlx[k], c.hly[k], c.hrx[k], c.hry[k]
        if c.lt[k] == VECTOR and pk >= 0:
            hlx, hly = c.x[k] + (c.x[pk] - c.x[k]) / 3.0, c.y[k] + (c.y[pk] - c.y[k]) / 3.0
        if c.rt[k] == VECTOR and nk >= 0:
            hrx, hry = c.x[k] + (c.x[nk] - c.x[k]) / 3.0, c.y[k] + (c.y[nk] - c.y[k]) / 3.0
        return hlx, hly, hrx, hry

    # ---- cost of removing a key ---------------------------------------------
    def _window_error(self, i):
        c = self.c
        p1, n1 = self.prev[i], self.next[i]
        chain = self._chain_around(p1, n1)
        H = self._chain_handles(chain)
        ip = chain.index(p1)
        lo, hi = max(ip - 1, 0), min(ip + 2, len(chain) - 1)
        worst = 0.0
        for a, b in zip(chain[lo:hi], chain[lo + 1:hi + 1]):
            s0 = np.searchsorted(self.xs, c.x[a], 'left')
            s1 = np.searchsorted(self.xs, c.x[b], 'left')
            if s1 <= s0:
                continue
            xs = self.xs[s0:s1]
            ys = _eval_segment(c.x[a], c.y[a], c.x[b], c.y[b],
                               (H[a][2], H[a][3]), (H[b][0], H[b][1]), c.ipo[a], xs)
            worst = max(worst, float(np.max(np.abs(ys - self.ys[s0:s1]))))
        last = chain[hi]
        j = np.searchsorted(self.xs, c.x[last], 'left')
        if j < len(self.xs) and abs(self.xs[j] - c.x[last]) < 1e-7:
            worst = max(worst, abs(float(self.ys[j]) - float(c.y[last])))
        return worst

    def _commit_slopes(self, p, n):
        """After unlinking a key, refresh the solved slopes around (p, n)."""
        if self.c.smoothing == 'NONE':
            return
        chain = self._chain_around(p, n)
        H = self._chain_handles(chain)
        c = self.c
        for k in chain[1:-1]:
            if not c.is_auto(k):
                continue
            hlx, hly, hrx, hry = H[k]
            if c.x[k] - hlx > 1e-9:
                self.sl[k] = (c.y[k] - hly) / (c.x[k] - hlx)
            if hrx - c.x[k] > 1e-9:
                self.sr[k] = (hry - c.y[k]) / (hrx - c.x[k])

    # ---- greedy removal order ---------------------------------------------
    def plan(self):
        """Returns (order, cum_error): key indices in removal order and the
        non-decreasing worst-case deviation after each removal."""
        for _progress in self.plan_iter():
            pass
        return self.result

    def plan_iter(self, every=25):
        """Generator version of plan(): yields progress (0..1) every `every`
        removals so a modal operator can spread the work over several ticks.
        The result is left in self.result."""
        n_keys = self.c.n
        total = max(sum(1 for r in self.removable if r), 1)
        version = [0] * n_keys
        gone = [False] * n_keys
        heap = []

        def push(i):
            if self.removable[i] and not gone[i] and self.prev[i] >= 0 and self.next[i] >= 0:
                version[i] += 1
                heapq.heappush(heap, (self._window_error(i), version[i], i))

        for i in range(n_keys):
            push(i)
            if i % (every * 4) == 0 and i:
                yield 0.0
        order, cum = [], []
        running = 0.0
        while heap:
            cost, ver, i = heapq.heappop(heap)
            if gone[i] or ver != version[i]:
                continue
            p, n = self.prev[i], self.next[i]
            gone[i] = True
            self.next[p] = n
            self.prev[n] = p
            self._commit_slopes(p, n)
            running = max(running, cost)
            order.append(i)
            cum.append(running)
            # re-score keys whose neighbourhood changed
            near = [p, n]
            k = p
            for _ in range(WINDOW):
                k = self.prev[k] if k >= 0 else -1
                near.append(k)
            k = n
            for _ in range(WINDOW):
                k = self.next[k] if k >= 0 else -1
                near.append(k)
            for k in near:
                if k >= 0:
                    push(k)
            if len(order) % every == 0:
                yield len(order) / total
        self.result = (np.array(order, dtype=int), np.array(cum, dtype=np.float64))
        yield 1.0


def make_planner(co, hl, hr, hl_types, hr_types, interpolation, removable,
                 xs, ys, flat_ends=True, smoothing='CONT_ACCEL'):
    """Planner for one curve (see build_plan for the arguments)."""
    ipo_map = {'BEZIER': BEZIER, 'LINEAR': LINEAR, 'CONSTANT': CONSTANT}
    curve = Curve(
        co, hl, hr,
        [HANDLE_CODES[t] for t in hl_types],
        [HANDLE_CODES[t] for t in hr_types],
        [ipo_map.get(t, BEZIER) for t in interpolation],
        flat_ends, smoothing,
    )
    return Planner(curve, list(map(bool, removable)), xs, ys)


def build_plan(co, hl, hr, hl_types, hr_types, interpolation, removable,
               xs, ys, flat_ends=True, smoothing='CONT_ACCEL'):
    """Compute the removal order for one curve.

    co/hl/hr: (n, 2) arrays; *_types: lists of Blender enum strings;
    removable: bool array; xs/ys: dense samples of the original curve.
    Returns (order, cum_error).
    """
    return make_planner(co, hl, hr, hl_types, hr_types, interpolation, removable,
                        xs, ys, flat_ends, smoothing).plan()


def removal_count(cum_error, tolerance):
    """How many keys (of the removal order) to drop for a given tolerance."""
    return int(np.searchsorted(cum_error, tolerance, side='right'))
