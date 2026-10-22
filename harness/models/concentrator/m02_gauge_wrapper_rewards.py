"""
m02 - ConcentratorSdCrvGaugeWrapper (L3763-L3953) reward accounting:
  LinearReward (K1, L315-L400) + LinearMultipleRewardDistributor (K2, L3549-L3759)
  + MultipleRewardAccumulator (K3, L1995-L2305) + wrapper actions (L490-L762, L3869-L3900).
Solidity 0.8.20 semantics: checked + - * (revert on overflow/underflow), SafeCast toUint80/toUint96 revert,
explicit uint96()/uint128()/uint40()/uint192() casts truncate, `unchecked` blocks wrap.
External venues (locker, bribe claimer, gauge) are abstracted: harvestBribes credits exactly `claims[i].amount`
of SDT to the wrapper (assumption A-LOCK in the report). periodLength = 7 days (L3827).
Run: python3 -I m02_gauge_wrapper_rewards.py
"""
from collections import defaultdict
import copy


def tx(obj, fn, *a):
    """Execute a top-level call with Solidity revert semantics: on Revert, restore the full pre-state."""
    saved = copy.deepcopy(obj.__dict__)
    try:
        return fn(*a)
    except Exception:
        obj.__dict__.clear()
        obj.__dict__.update(saved)
        raise


class Revert(Exception):
    pass


def req(c, msg):
    if not c:
        raise Revert(msg)


M256 = 1 << 256


def ck(x, bits=256):  # checked result
    req(0 <= x < (1 << bits), "panic(0x11) arithmetic over/underflow")
    return x


def toU(x, bits):  # SafeCast
    req(x < (1 << bits), f"SafeCast: value doesn't fit in {bits} bits")
    return x


def tr(x, bits):  # truncating cast
    return x % (1 << bits)


E18 = 10 ** 18
DAY = 86400
P = 7 * DAY
REWARD_PRECISION = 10 ** 18
T0 = 1_700_000_000
SDT = "SDT"


class RewardData:
    def __init__(self):
        self.queued = 0  # uint96
        self.rate = 0  # uint80
        self.lastUpdate = 0  # uint40
        self.finishAt = 0  # uint40

    def __repr__(self):
        return (f"RD(queued={self.queued}, rate={self.rate}, lastUpdate=+{(self.lastUpdate - T0) / DAY:.2f}d, "
                f"finishAt=+{(self.finishAt - T0) / DAY:.2f}d)")


class Wrapper:
    def __init__(self, now):
        self.now = now
        self.totalSupply = 0
        self.balanceOf = defaultdict(int)
        self.active = []  # EnumerableSet (insertion order)
        self.historical = []
        self.rewardData = defaultdict(RewardData)
        self.integral = defaultdict(int)  # rewardSnapshot[token].integral (uint192)
        self.user_pending = defaultdict(int)  # [user][token] -> uint128
        self.user_integral = defaultdict(int)
        self.bal = defaultdict(int)  # custody: token balance of wrapper
        self.gauge_reward_tokens = [SDT]
        self.expense = 0
        self.booster = 0

    # ---- K1 LinearReward ----
    def increase(self, d, amount):  # L350-L379
        amount = ck(amount + d.queued)
        d.queued = 0
        if self.now >= d.finishAt:
            d.rate = toU(amount // P, 80)
            d.queued = tr(ck(amount - ck(d.rate * P)), 96)
            d.lastUpdate = tr(self.now, 40)
            d.finishAt = tr(self.now + P, 40)
            return "period-finished-branch"
        elapsed = ck(self.now - ck(d.finishAt - P))
        distributed = ck(d.rate * elapsed)
        if ck(distributed * 9) <= ck(amount * 10):
            amount = ck(amount + ck(d.rate * ck(d.finishAt - d.lastUpdate, 40)))
            d.rate = toU(amount // P, 80)
            d.queued = tr(ck(amount - ck(d.rate * P)), 96)
            d.lastUpdate = tr(self.now, 40)
            d.finishAt = tr(self.now + P, 40)
            return "re-extend-branch"
        d.queued = toU(amount, 96)
        return "queue-branch"

    def pending(self, d):  # L382-L399
        left = 0
        if self.now > d.finishAt:
            elapsed = d.finishAt - d.lastUpdate if d.finishAt >= d.lastUpdate else 0
        else:
            elapsed = (self.now - d.lastUpdate) % M256  # unchecked
            left = (d.finishAt - self.now) % M256
        return d.rate * elapsed, d.rate * left

    # ---- K2 distributor ----
    def _notifyReward(self, token, amount):  # L3728-L3736 (periodLength != 0)
        return self.increase(self.rewardData[token], amount)

    def _distributePendingReward(self):  # L3739-L3752
        if len(self.active) == 0:
            return
        for t in list(self.active):
            pend, _ = self.pending(self.rewardData[t])
            self.rewardData[t].lastUpdate = tr(self.now, 40)
            if pend > 0:
                self._accumulateReward(t, pend)

    # ---- K3 accumulator ----
    def _accumulateReward(self, token, amount):  # L2282-L2296
        if amount == 0:
            return
        if self.totalSupply == 0:
            self.rewardData[token].queued = ck(self.rewardData[token].queued + tr(amount, 96), 96)
            return
        self.integral[token] = tr(self.integral[token] + (amount * REWARD_PRECISION) // self.totalSupply, 192)

    def claimable(self, user, token):  # L2124-L2131
        return ck(self.user_pending[(user, token)] +
                  ck(ck(self.integral[token] - self.user_integral[(user, token)]) * self.balanceOf[user]) // REWARD_PRECISION)

    def _updateSnapshot(self, user, token):  # L2231-L2237
        self.user_pending[(user, token)] = tr(self.claimable(user, token), 128)
        self.user_integral[(user, token)] = self.integral[token]

    def _checkpoint(self, user):  # L2210-L2226
        self._distributePendingReward()
        if user is not None:
            for t in list(self.active):
                self._updateSnapshot(user, t)
            for t in list(self.historical):
                self._updateSnapshot(user, t)

    def _claimSingle(self, user, token, receiver):  # L2262-L2279
        amt = self.user_pending[(user, token)]
        if amt > 0:
            self.user_pending[(user, token)] = 0
            req(self.bal[token] >= amt, f"SafeERC20: transfer amount exceeds balance ({token})")
            self.bal[token] -= amt
        return amt

    def claim(self, user):  # L2168-L2175 + _claim L2243-L2254
        self._checkpoint(user)
        got = {}
        for t in list(self.active):
            got[t] = self._claimSingle(user, t, user)
        return got

    def claimHistorical(self, user, tokens):  # L2191-L2200
        self._checkpoint(user)
        return {t: self._claimSingle(user, t, user) for t in tokens}

    # ---- wrapper actions ----
    def deposit(self, receiver, amount):  # L600-L608 / _deposit L730-L751
        req(amount != 0, "ErrorDepositZeroAssets")
        self._checkpoint(receiver)
        self.balanceOf[receiver] += amount
        self.totalSupply += amount

    def withdraw(self, owner, amount):  # L622-L641
        req(amount != 0 and amount <= self.balanceOf[owner], "withdraw guard")
        self._checkpoint(owner)
        self.balanceOf[owner] -= amount
        self.totalSupply -= amount

    def checkpoint(self, user):  # L2152-L2154
        self._checkpoint(user)

    def harvestBribes(self, claims):  # L3869-L3900 (NO _checkpoint / _distributePendingReward)
        branch = None
        for token, amount in claims:
            self.bal[token] += amount  # A-LOCK: locker forwards exactly `amount`
            assets = amount
            perf = assets * self.expense // 10 ** 9
            boost = assets * self.booster // 10 ** 9
            if token == SDT:
                self.bal[token] -= perf + boost
                branch = self._notifyReward(token, ck(ck(assets - perf) - boost))
            else:
                raise Revert("ErrorInvalidBribeToken / burner path not modelled")
        return branch

    def unregisterRewardToken(self, token):  # L3703-L3718 (REWARD_MANAGER_ROLE)
        req(token in self.active, "NotActiveRewardToken")
        d = self.rewardData[token]
        dist, undist = self.pending(d)
        q = d.queued if d.queued >= P else 0
        req(q + dist + undist == 0, "RewardDistributionNotFinished")
        self.active.remove(token)
        self.historical.append(token)

    def syncActiveRewardTokens(self):  # L685-L700 (permissionless)
        for t in self.gauge_reward_tokens:
            if t not in self.active:
                self.active.append(t)  # NOTE: not removed from historical
                b = self.bal[t]
                if b > 0:
                    self._notifyReward(t, b)


def setup():
    w = Wrapper(T0)
    w.active.append("sdCRV")  # stakingToken registered as reward token (L3844)
    w.active.append(SDT)  # via syncActiveRewardTokens in __init (L581)
    w.balanceOf["asdCRV"] = 1000 * E18  # L3851
    w.totalSupply = 1000 * E18  # L3852 (assume legacy total == asdCRV balance)
    w.deposit("alice", 1000 * E18)
    return w


def liabilities(w, token, users):
    total = sum(w.claimable(u, token) for u in users)
    d = w.rewardData[token]
    dist, undist = w.pending(d)
    return total, dist + undist + d.queued


def scenario_harvestBribes_caseA():
    print("== harvestBribes without checkpoint, case A (now >= finishAt): un-accumulated stream destroyed ==")
    for control in (False, True):
        w = setup()
        w.harvestBribes([(SDT, 70 * E18)])
        r1 = repr(w.rewardData[SDT])
        w.now = T0 + 8 * DAY
        if control:
            w.checkpoint("bob_any")  # any permissionless checkpoint before the bribe harvest
        br = w.harvestBribes([(SDT, 70 * E18)])
        w.now = T0 + 15 * DAY + 1
        cla = w.claim("alice")[SDT]
        cls = w.claim("asdCRV")[SDT]
        print(f"  control_checkpoint={control}: after 1st bribe {r1}; 2nd bribe branch={br}")
        print(f"    claimed alice={cla} asdCRV={cls} total={cla + cls}; SDT custody left={w.bal[SDT]} "
              f"(orphaned = custody - outstanding = {w.bal[SDT] - sum(liabilities(w, SDT, ['alice', 'asdCRV']))})")


def scenario_harvestBribes_caseB():
    print("== harvestBribes without checkpoint, case B (now < finishAt, 10% rule passes): vested part re-streamed ==")
    for control in (False, True):
        w = setup()
        w.harvestBribes([(SDT, 70 * E18)])
        w.now = T0 + 3 * DAY
        if control:
            w.checkpoint("bob_any")
        br = w.harvestBribes([(SDT, 40 * E18)])
        w.withdraw("alice", 1000 * E18)  # alice exits right after the bribe harvest
        ca = w.claim("alice")[SDT]
        w.now = T0 + 11 * DAY
        cs = w.claim("asdCRV")[SDT]
        print(f"  control_checkpoint={control}: branch={br}; alice (exits at +3d) claims {ca}; asdCRV claims {cs} at +11d")


def scenario_sync_double_count():
    print("== unregisterRewardToken (R3) + syncActiveRewardTokens (R1): custody re-notified -> insolvency ==")
    w = setup()
    w.harvestBribes([(SDT, 70 * E18)])
    w.now = T0 + 8 * DAY
    w.checkpoint("asdCRV")
    w.unregisterRewardToken(SDT)
    out = sum(w.claimable(u, SDT) for u in ("alice", "asdCRV"))
    print(f"  t=+8d after unregister: active={w.active} historical={w.historical} SDT custody={w.bal[SDT]} "
          f"outstanding claims={out}")
    w.syncActiveRewardTokens()
    print(f"  after syncActiveRewardTokens(): active={w.active} historical={w.historical} rewardData={w.rewardData[SDT]}")
    w.now = T0 + 16 * DAY
    w.checkpoint(None)
    out = sum(w.claimable(u, SDT) for u in ("alice", "asdCRV"))
    print(f"  t=+16d outstanding claims={out} vs SDT custody={w.bal[SDT]} (deficit {out - w.bal[SDT]})")
    print(f"  alice claim -> {tx(w, w.claim, 'alice')}")
    try:
        print(f"  asdCRV claim -> {tx(w, w.claim, 'asdCRV')}")
    except Revert as e:
        print(f"  asdCRV claim -> REVERT('{e}') [state rolled back]")
    try:
        print(f"  asdCRV claimHistorical([SDT]) -> {tx(w, w.claimHistorical, 'asdCRV', [SDT])}")
    except Revert as e:
        print(f"  asdCRV claimHistorical([SDT]) -> REVERT('{e}') [state rolled back]")
    print(f"  asdCRV still owed {w.claimable('asdCRV', SDT)} SDT; custody {w.bal[SDT]}")


if __name__ == "__main__":
    scenario_harvestBribes_caseA()
    print()
    scenario_harvestBribes_caseB()
    print()
    scenario_sync_double_count()
