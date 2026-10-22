# BoostableRebalancePool time-weighted boost with linearly interpolated ve (L16498-L16540, L16543-L16580)
# vs. the NatSpec definition (L15933-L15940: ve[u][w] = ve balance at the beginning of week w).
# No liquidation (product constant), single history entry, so _realBalance = balance.
# Run: python3 -I boost_interp.py
PREC = 10**18
WEEK = 7 * 86400


def ratio_at(bal, ve, veS, S):                 # _boostRatioAt core L16565-L16579
    if bal == 0:
        return PREC * 4 // 10
    b = bal * 4 // 10
    if veS > 0:
        b += ((ve * S) // veS) * 6 // 10
    b = min(b, bal)
    return b * PREC // bal


def impl(bal, S, ck_ve, ck_veS, upd, now, cur_ve, cur_veS):   # L16498-L16540
    cur = ratio_at(bal, ck_ve, ck_veS, S)
    if upd == now:
        return cur
    dve, dS, dur = cur_ve - ck_ve, cur_veS - ck_veS, now - upd
    prev = upd
    nxt = ((prev + WEEK - 1) // WEEK) * WEEK
    acc = 0
    for _ in range(256):
        if nxt > now:
            nxt = now
        acc += cur * (nxt - prev)
        if nxt == now:
            break
        dt = nxt - upd
        ve = int((dve * dt) / dur) if False else (dve * dt) // dur if dve >= 0 else -((-dve * dt) // dur)  # int256 division truncates toward 0
        ve += ck_ve
        vS = (dS * dt) // dur if dS >= 0 else -((-dS * dt) // dur)
        vS += ck_veS
        cur = ratio_at(bal, ve, vS, S)
        prev = nxt
        nxt += WEEK
    return acc // dur


def spec(bal, S, ve_fn, veS_fn, upd, now):     # NatSpec: weekly ve at the beginning of each week
    prev = upd
    nxt = ((prev + WEEK - 1) // WEEK) * WEEK
    acc = 0
    cur = ratio_at(bal, ve_fn(upd), veS_fn(upd), S)
    while True:
        nxt = min(nxt, now)
        acc += cur * (nxt - prev)
        if nxt == now:
            break
        cur = ratio_at(bal, ve_fn(nxt), veS_fn(nxt), S)
        prev = nxt
        nxt += WEEK
    return acc // (now - upd)


bal, S = 100 * PREC, 1000 * PREC
V = 10**6 * PREC
t0 = 10 * WEEK + 3600                                   # last checkpoint
t1 = 14 * WEEK + 3600 - 60                              # user locks at t1, checkpoints at t1+60
lock = 2 * 10**5 * PREC                                 # 20% of ve supply -> full boost once held
ve_fn = lambda t: 0 if t < t1 else lock
veS_fn = lambda t: V if t < t1 else V + lock
r_impl = impl(bal, S, 0, V, t0, t1 + 60, lock, V + lock)
r_spec = spec(bal, S, ve_fn, veS_fn, t0, t1 + 60)
print("user stake 100/1000, no ve for 4 weeks, locks 20% of ve supply 60 s before checkpoint:")
print("  implementation time-weighted boost = %.4f ; NatSpec definition = %.4f ; FXN for the 4 weeks inflated by %.1f%%"
      % (r_impl / 1e18, r_spec / 1e18, 100 * (r_impl - r_spec) / r_spec))
r_impl2 = impl(bal, S, lock, V + lock, t0, t1 + 60, 0, V)
r_spec2 = spec(bal, S, lambda t: lock if t < t1 else 0, lambda t: V + lock if t < t1 else V, t0, t1 + 60)
print("reverse (full ve for 4 weeks, lock ends/transferred just before checkpoint): impl = %.4f ; spec = %.4f"
      % (r_impl2 / 1e18, r_spec2 / 1e18))
