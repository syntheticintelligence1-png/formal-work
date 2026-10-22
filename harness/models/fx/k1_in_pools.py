# K1 precondition discharge inside the rebalance pools' _checkpoint override.
#   Boostable  L16298-L16309: gauge mint -> _notifyReward(fxn, minted) [L16306] -> MRCA._checkpoint -> _distributePendingReward
#   Shareable  L15262-L15276: same order (L15269 then L15276)
#   K2 depositReward L3650-L3661 distributes first (compliant), the pools' gauge path does not.
#   LinearReward.increase L350-L380, pending L385-L399; K2 _distributePendingReward L3739-L3752.
# Run: python3 -I k1_in_pools.py
DAY, WEEK = 86400, 7 * 86400


class RD:  # LinearReward.RewardData
    def __init__(s):
        s.queued = 0; s.rate = 0; s.last = 0; s.finish = 0


def increase(d, P, amt, now):
    amt = amt + d.queued
    d.queued = 0
    if now >= d.finish:
        d.rate = amt // P
        d.queued = amt - d.rate * P
        d.last = now
        d.finish = now + P
    else:
        elapsed = now - (d.finish - P)
        distributed = d.rate * elapsed
        if distributed * 9 <= amt * 10:
            amt = amt + d.rate * (d.finish - d.last)
            d.rate = amt // P
            d.queued = amt - d.rate * P
            d.last = now
            d.finish = now + P
        else:
            d.queued = amt


def pending(d, now):
    if now > d.finish:
        el = d.finish - d.last if d.finish >= d.last else 0
    else:
        el = now - d.last
    return d.rate * el


def distribute(d, now):  # _distributePendingReward for one token: returns accumulated amount
    x = pending(d, now)
    d.last = now
    return x


def run(order, gap_days, minted_after):
    """notify 7000 FXN at t=0 (gauge claim), then the next interaction happens gap_days later."""
    d = RD()
    acc = 0
    increase(d, WEEK, 7000 * 10**18, 0)          # gauge claim at t=0 (pool did distribute first: nothing pending)
    acc += distribute(d, 0)
    now = int(gap_days * DAY)
    if order == "pool":                          # L16306 then L16309
        increase(d, WEEK, minted_after, now)
        acc += distribute(d, now)
    else:                                        # K2-compliant: distribute then notify
        acc += distribute(d, now)
        increase(d, WEEK, minted_after, now)
        acc += distribute(d, now)
    # let everything that is still scheduled run out
    acc += distribute(d, now + 30 * DAY)
    return acc, d.queued


for gap in [2, 6.9, 8, 14]:
    a_pool, q1 = run("pool", gap, 1000 * 10**18)
    a_k2, q2 = run("k2", gap, 1000 * 10**18)
    print("next interaction after %4.1f days: accumulated(+queued)  pool-order=%.1f(+%.1f) FXN  K2-order=%.1f(+%.1f) FXN  of 8000 notified; destroyed=%.1f FXN"
          % (gap, a_pool / 1e18, q1 / 1e18, a_k2 / 1e18, q2 / 1e18, ((a_k2 + q2) - (a_pool + q1)) / 1e18))

# time shift in the now < finishAt branch (daily gauge claims of 1000 FXN = one day of emission)
d1, d2 = RD(), RD()
for d in (d1, d2):
    increase(d, WEEK, 1000 * 10**18, 0); distribute(d, 0)
t = DAY + 1
increase(d1, WEEK, 1000 * 10**18, t); got_pool = distribute(d1, t)
got_k2 = distribute(d2, t); increase(d2, WEEK, 1000 * 10**18, t); got_k2 += distribute(d2, t)
print("\ndaily claims of 1000 FXN, next gauge claim at t=1d+1s (no checkpoint in between):")
print("  distributed to stakers of [0,1d] at that claim: pool-order=%.4f FXN, K2-order=%.4f FXN -> %.4f FXN re-streamed over [1d, 8d]"
      % (got_pool / 1e18, got_k2 / 1e18, (got_k2 - got_pool) / 1e18))
print("  new rate: pool-order=%d wei/s, K2-order=%d wei/s" % (d1.rate, d2.rate))
