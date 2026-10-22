"""
m01 - AladdinCompounder (L2748-L3144, pragma 0.7.6) instantiated by SdCrvCompounder (L1182-L1587).

Integer semantics mirrored exactly:
  * 0.7.6: plain + - * WRAP mod 2^256 (no checked arithmetic); `/` by zero reverts (invalid opcode).
  * SafeMathUpgradeable .add/.sub/.mul/.div revert on overflow / underflow / div-by-zero.
  * casts uint128()/uint48() truncate.
The wrapper (ConcentratorSdCrvGaugeWrapper) is abstracted as a custody counter W = wrapper.balanceOf[compounder]
with its zero-amount guards (L628, L735) and the insufficient-balance guard (L629).
Run: python3 -I m01_aladdin_compounder.py
"""
from collections import defaultdict
import copy

M256 = 1 << 256
MAX = M256 - 1


class Revert(Exception):
    pass


def req(c, msg):
    if not c:
        raise Revert(msg)


def add7(a, b):  # 0.7.6 unchecked +
    return (a + b) % M256


def sub7(a, b):  # 0.7.6 unchecked -
    return (a - b) % M256


def mul7(a, b):  # 0.7.6 unchecked *
    return (a * b) % M256


def div7(a, b):  # plain `/`: reverts on zero divisor in every solc version
    if b == 0:
        raise Revert("division by zero (0.7.6 invalid opcode)")
    return a // b


def sadd(a, b):
    c = a + b
    req(c < M256, "SafeMath: addition overflow")
    return c


def ssub(a, b, msg="SafeMath: subtraction overflow"):
    req(b <= a, msg)
    return a - b


def smul(a, b):
    c = a * b
    req(c < M256, "SafeMath: multiplication overflow")
    return c


def sdiv(a, b):
    req(b > 0, "SafeMath: division by zero")
    return a // b


def u(x, bits):  # truncating cast
    return x % (1 << bits)


E18 = 10 ** 18
DAY = 86400
FEE_PRECISION = 10 ** 9


class SdCrvCompounder:
    def __init__(self, now):
        self.now = now
        # ERC20 ledger (L)
        self.TS = 0
        self.bal = defaultdict(int)
        self.allow = defaultdict(int)
        # L / T strata
        self.TAS = 0  # totalAssetsStored L2837
        self.rate = 0  # uint128 L2822
        self.P = 0  # periodLength uint32 L2825
        self.lastUpdate = 0  # uint48 L2826
        self.finishAt = 0  # uint48 L2827
        # P stratum
        self.platformPct = 0
        self.bountyPct = 0
        self.withdrawPct = 0
        self.custom = {}  # FeeCustomization (L4018-L4025)
        self.stash = "stash"
        # custody (C): sdCRV credited to the compounder inside the wrapper, and EOAs' sdCRV
        self.W = 0
        self.ext = defaultdict(int)

    # ---------------- views ----------------
    def _period(self):
        if self.now > self.finishAt:
            return self.finishAt - self.lastUpdate if self.finishAt >= self.lastUpdate else 0
        return sub7(self.now, self.lastUpdate)

    def totalAssets(self):  # L2849-L2859
        return add7(self.TAS, mul7(self._period(), self.rate))

    def convertToShares(self, a):  # L2862-L2868
        ta = self.totalAssets()
        if ta == 0:
            return a
        return div7(smul(self.TS, a), ta)

    def convertToAssets(self, s):  # L2871-L2877
        if self.TS == 0:
            return s
        return div7(smul(self.totalAssets(), s), self.TS)

    def previewDeposit(self, a):
        return self.convertToShares(a)

    def previewMint(self, s):
        return self.convertToAssets(s)

    def previewWithdraw(self, a):  # L2905-L2915
        ta = self.totalAssets()
        req(a <= ta, "exceed total assets")
        s = self.convertToShares(a)
        if a == ta:
            return s
        return sdiv(smul(s, FEE_PRECISION), sub7(FEE_PRECISION, self.withdrawPct))

    def previewRedeem(self, s):  # L2923-L2935
        req(s <= self.TS, "exceed total supply")
        a = self.convertToAssets(s)
        if s == self.TS:
            return a
        fee = div7(smul(a, self.withdrawPct), FEE_PRECISION)
        return sub7(a, fee)

    def getFeeRate(self, user):  # L4018-L4025
        return self.custom.get(user, self.withdrawPct)

    # ---------------- ERC20 internals (OZ 3.4) ----------------
    def _mint(self, to, amt):
        self.TS = sadd(self.TS, amt)
        self.bal[to] = sadd(self.bal[to], amt)

    def _burn(self, frm, amt):
        self.bal[frm] = ssub(self.bal[frm], amt, "ERC20: burn amount exceeds balance")
        self.TS = ssub(self.TS, amt)

    # ---------------- wrapper abstraction ----------------
    def _wrapper_deposit(self, amt):  # wrapper._deposit guard L735
        req(amt != 0, "wrapper: ErrorDepositZeroAssets")
        self.W += amt

    def _wrapper_withdraw(self, amt, receiver):  # L628-L629
        req(amt != 0, "wrapper: ErrorWithdrawZeroAssets")
        req(amt <= self.W, "wrapper: ErrorInsufficientStakedToken")
        self.W -= amt
        self.ext[receiver] += amt

    # ---------------- AladdinCompounder internals ----------------
    def _distributePendingReward(self):  # L3090-L3113
        if self.P == 0:
            return
        period = self._period()
        if self.TAS == 0:
            pass  # L3103-L3108: nothing, lastUpdate NOT advanced
        else:
            self.TAS = add7(self.TAS, mul7(period, self.rate))
            self.lastUpdate = u(self.now, 48)

    def _notifyHarvestedReward(self, amount):  # L3118-L3138
        if self.P == 0:
            self.TAS = sadd(self.TAS, amount)
        else:
            req(amount < (1 << 128) - 1, "amount overflow")
            if self.now >= self.finishAt:
                rate = u(amount // self.P, 128)
            else:
                remaining = self.finishAt - self.now
                leftover = mul7(remaining, self.rate)
                rate = u(add7(amount, leftover) // self.P, 128)
            self.rate = rate
            self.lastUpdate = u(self.now, 48)
            self.finishAt = u(self.now + self.P, 48)

    # ---------------- SdCrvCompounder internals ----------------
    def _mintShare(self, a, receiver):  # L1527-L1543
        req(a > 0, "asdCRV: deposit zero amount")
        ta = self.TAS
        s_tot = self.TS
        if ta == 0:
            shares = a
        else:
            shares = div7(smul(a, s_tot), ta)
        self._mint(receiver, shares)
        self.TAS = add7(ta, a)
        return shares

    def _deposit(self, a, receiver):  # L1517-L1521
        self._wrapper_deposit(a)
        return self._mintShare(a, receiver)

    def _withdraw(self, shares, receiver, owner):  # L1546-L1568 (no withdraw fee)
        req(shares > 0, "asdCRV: withdraw zero share")
        req(shares <= self.bal[owner], "asdCRV: insufficient owner shares")
        ta = self.TAS
        s_tot = self.TS
        amount = div7(smul(shares, ta), s_tot)
        self._burn(owner, shares)
        self.TAS = sub7(ta, amount)
        self._wrapper_withdraw(amount, receiver)
        return amount

    # ---------------- external actions ----------------
    def deposit(self, sender, a, receiver):  # L2940-L2950
        if a == MAX:
            a = self.ext[sender]
        self._distributePendingReward()
        req(self.ext[sender] >= a, "ERC20: transfer amount exceeds balance")
        self.ext[sender] -= a
        return self._deposit(a, receiver)

    def mint(self, sender, s, receiver):  # L2953-L2961
        self._distributePendingReward()
        a = self.convertToAssets(s)
        req(self.ext[sender] >= a, "ERC20: transfer amount exceeds balance")
        self.ext[sender] -= a
        minted = self._deposit(a, receiver)
        return a, minted

    def withdraw(self, sender, a, receiver, owner):  # L2964-L2994
        self._distributePendingReward()
        if a == MAX:
            a = self.convertToAssets(self.bal[owner])
        ta = self.totalAssets()
        req(a <= ta, "exceed total assets")
        s = self.convertToShares(a)
        if a < ta:
            pct = self.getFeeRate(owner)
            s = sdiv(smul(s, FEE_PRECISION), sub7(FEE_PRECISION, pct))
        if sender != owner:
            al = self.allow[(owner, sender)]
            req(al >= s, "withdraw exceeds allowance")
        before = self.ext[receiver]
        self._withdraw(s, receiver, owner)
        return s, self.ext[receiver] - before

    def redeem(self, sender, s, receiver, owner):  # L2997-L3017
        if s == MAX:
            s = self.bal[owner]
        self._distributePendingReward()
        return self._withdraw(s, receiver, owner)

    def checkpoint(self):  # L3020-L3022
        self._distributePendingReward()

    def depositReward(self, sender, amount):  # L1482-L1491
        req(sender == self.stash, "asdCRV: caller not stash")
        self._distributePendingReward()
        self._wrapper_deposit(amount)  # transferFrom(stash) + wrapper.deposit(amount)
        self._notifyHarvestedReward(amount)

    def harvest_fee_part(self, assets, platform, recipient):  # L1458-L1477 (after rewards are deposited)
        self._distributePendingReward()
        self._wrapper_deposit(assets)
        ta = self.TAS
        s_tot = self.TS
        pf = self.platformPct
        if pf > 0:
            pf = (pf * assets) // FEE_PRECISION
            self._mint(platform, div7(smul(pf, s_tot), ta))
        hb = self.bountyPct
        if hb > 0:
            hb = (hb * assets) // FEE_PRECISION
            self._mint(recipient, div7(smul(hb, s_tot), ta))
        self.TAS = sadd(sadd(ta, pf), hb)
        self._notifyHarvestedReward(sub7(sub7(assets, pf), hb))

    def updateRewardPeriodLength(self, length):  # L3049-L3053 (owner)
        self.P = u(length, 32)

    def updateFeeInfo(self, platformPct, bountyPct, withdrawPct):  # L3031-L3045 (owner)
        req(platformPct <= 2 * 10 ** 8, "platform fee too large")
        req(bountyPct <= 10 ** 8, "bounty fee too large")
        req(withdrawPct <= 10 ** 8, "withdraw fee too large")
        self.platformPct, self.bountyPct, self.withdrawPct = platformPct, bountyPct, withdrawPct

    # gluing slack for B5: custody in wrapper minus (credited ledger + not-yet-vested stream)
    def unvested(self):
        if self.now >= self.finishAt:
            return 0
        return (self.finishAt - max(self.now, self.lastUpdate)) * self.rate

    def snapshot(self, tag):
        print(f"    [{tag}] t=+{(self.now - T0) / DAY:.2f}d TS={self.TS} TAS={self.TAS} totalAssets()={self.totalAssets()} "
              f"rate={self.rate} P={self.P} lastUpdate=+{(self.lastUpdate - T0) / DAY if self.lastUpdate else 0:.2f}d "
              f"finishAt=+{(self.finishAt - T0) / DAY if self.finishAt else 0:.2f}d W={self.W}")


T0 = 1_700_000_000


def attempt(label, fn, obj=None):
    """Top-level call with Solidity revert semantics (full state rollback on Revert when obj is given)."""
    saved = copy.deepcopy(obj.__dict__) if obj is not None else None
    try:
        r = fn()
        print(f"    {label} -> OK {r}")
        return r
    except Revert as e:
        if obj is not None:
            obj.__dict__.clear()
            obj.__dict__.update(saved)
        print(f"    {label} -> REVERT('{e}')")
        return None


def scenario_S2():
    print("== S2: SdCrvCompounder._withdraw charges no fee; preview/execute divergence (withdraw fee f = 5%) ==")
    c = SdCrvCompounder(T0)
    c.updateFeeInfo(0, 0, 5 * 10 ** 7)
    c.ext["alice"] = 100 * E18
    c.ext["bob"] = 100 * E18
    c.deposit("alice", 100 * E18, "alice")
    c.deposit("bob", 100 * E18, "bob")
    c.depositReward("stash", 10 * E18)  # P == 0 -> TAS += 10e18 immediately
    c.snapshot("state")
    s = 10 * E18
    pr = c.previewRedeem(s)
    got = c.redeem("alice", s, "alice_rx", "alice")
    print(f"  previewRedeem({s}) = {pr}; redeem({s}) transferred = {got}; difference = {got - pr}")
    a = 10 * E18
    pw = c.previewWithdraw(a)
    shares, received = c.withdraw("bob", a, "bob_rx", "bob")
    print(f"  previewWithdraw({a}) = {pw}; withdraw({a}) burned = {shares} shares, receiver got = {received} "
          f"(requested {a}; excess {received - a})")
    print("  withdraw(type(uint256).max) by alice (non-last holder):")
    attempt("withdraw(MAX, alice, alice)", obj=c, fn=lambda: c.withdraw("alice", MAX, "alice", "alice"))
    attempt("redeem(MAX, alice, alice)  [alternative exit]", obj=c, fn=lambda: c.redeem("alice", MAX, "alice", "alice"))

    print("  f = 0 (exactness of withdraw with floor rounding): TS=2, TAS=3")
    d = SdCrvCompounder(T0)
    d.ext["x"] = 2
    d.deposit("x", 2, "x")
    d.depositReward("stash", 1)
    d.snapshot("state")
    pw = d.previewWithdraw(2)
    attempt("withdraw(2) [preview shares=%d]" % pw, obj=d, fn=lambda: d.withdraw("x", 2, "x_rx", "x"))

    print("  mint rounding: TS=2, TAS=3, mint(1)")
    m = SdCrvCompounder(T0)
    m.ext["x"] = 2
    m.deposit("x", 2, "x")
    m.depositReward("stash", 1)
    m.ext["y"] = 10
    pm = m.previewMint(1)
    a_paid, minted = m.mint("y", 1, "y")
    print(f"    previewMint(1) = {pm}; mint(1): assets pulled = {a_paid}, shares minted = {minted}, bal[y] = {m.bal['y']}")


def scenario_S3():
    print("== S3: empty-interval accrual (lastUpdate not advanced while TAS == 0) ==")
    c = SdCrvCompounder(T0)
    c.updateRewardPeriodLength(7 * DAY)
    c.ext["alice"] = 1000 * E18
    c.deposit("alice", 1000 * E18, "alice")
    c.depositReward("stash", 700 * E18)
    c.snapshot("after reward 700e18 streamed over 7d")
    c.now = T0 + 1 * DAY
    got = c.redeem("alice", MAX, "alice", "alice")
    print(f"  t=+1d alice redeems all -> {got}")
    c.snapshot("vault empty")
    c.now = T0 + 3 * DAY
    print(f"  t=+3d previewDeposit(150e18) = {c.previewDeposit(150 * E18)}  (deposit would mint 150e18 shares: TAS==0 branch)")
    c.ext["mallory"] = 1
    sm = c.deposit("mallory", 1, "mallory")
    print(f"  t=+3d mallory deposit(1) -> shares {sm}")
    c.snapshot("after mallory")
    c.ext["victim"] = 150 * E18
    pv = c.previewDeposit(150 * E18)
    sv = c.deposit("victim", 150 * E18, "victim")
    print(f"  t=+3d victim previewDeposit(150e18) = {pv}; deposit(150e18) -> shares {sv}")
    c.snapshot("after victim")
    got = c.redeem("mallory", MAX, "mallory", "mallory")
    print(f"  mallory redeems her 1 share -> receives {got} (= {got / E18:.6f} sdCRV); victim shares = {c.bal['victim']}")
    attempt("victim redeem(MAX)", obj=c, fn=lambda: c.redeem("victim", MAX, "victim", "victim"))

    print("  variant: reward deposit DURING the empty interval orphans the vested-but-uncredited part")
    v = SdCrvCompounder(T0)
    v.updateRewardPeriodLength(7 * DAY)
    v.ext["alice"] = 1000 * E18
    v.deposit("alice", 1000 * E18, "alice")
    v.depositReward("stash", 700 * E18)
    v.now = T0 + 1 * DAY
    v.redeem("alice", MAX, "alice", "alice")
    v.now = T0 + 2 * DAY
    owed_before = v.TAS + v._period() * v.rate + v.unvested()
    v.depositReward("stash", 70 * E18)
    owed_after = v.TAS + v._period() * v.rate + v.unvested()
    print(f"    custody W = {v.W}; ledger+stream before = {owed_before + 70 * E18} ; after = {owed_after}; "
          f"orphaned = {v.W - owed_after} (= rate*1d = {v.rate and (owed_before + 70 * E18 - owed_after)})")


def scenario_P0_brick():
    print("== P == 0 and empty vault: TAS > 0 with TS == 0 -> every later deposit mints 0 shares ==")
    c = SdCrvCompounder(T0)
    c.updateRewardPeriodLength(0)
    c.depositReward("stash", 10 * E18)
    c.snapshot("after stash depositReward(10e18) on empty vault")
    c.ext["alice"] = 100 * E18
    s = c.deposit("alice", 100 * E18, "alice")
    print(f"  alice deposit(100e18) -> shares {s}; bal[alice]={c.bal['alice']} TS={c.TS} TAS={c.TAS}")
    attempt("alice redeem(MAX)", obj=c, fn=lambda: c.redeem("alice", MAX, "alice", "alice"))
    attempt("alice withdraw(100e18)", obj=c, fn=lambda: c.withdraw("alice", 100 * E18, "alice", "alice"))
    print("  harvest with platform fee on an empty vault (TAS == 0):")
    h = SdCrvCompounder(T0)
    h.updateFeeInfo(10 ** 8, 0, 0)
    attempt("harvest(assets=5e18)", obj=h, fn=lambda: h.harvest_fee_part(5 * E18, "platform", "keeper"))


def scenario_S4():
    print("== S4: updateRewardPeriodLength(0) mid-stream (owner) ==")
    for settle in (False, True):
        c = SdCrvCompounder(T0)
        c.updateRewardPeriodLength(7 * DAY)
        c.ext["alice"] = 1000 * E18
        c.ext["bob"] = 1000 * E18
        c.deposit("alice", 1000 * E18, "alice")
        c.deposit("bob", 1000 * E18, "bob")
        c.depositReward("stash", 700 * E18)
        c.now = T0 + 1 * DAY
        if settle:
            c.checkpoint()  # settle* before the policy write
        c.updateRewardPeriodLength(0)
        c.now = T0 + 2 * DAY
        pr = c.previewRedeem(c.bal["bob"])
        got = c.redeem("bob", MAX, "bob", "bob")
        print(f"  settle*={settle}: t=+2d bob previewRedeem={pr} redeem={got} (preview - actual = {pr - got})")
        c.now = T0 + 10 * DAY
        c.updateRewardPeriodLength(7 * DAY)
        c.checkpoint()
        got_a = c.redeem("alice", MAX, "alice", "alice")
        print(f"  settle*={settle}: t=+10d P restored, alice redeem={got_a}; W left={c.W}")


if __name__ == "__main__":
    scenario_S2()
    print()
    scenario_S3()
    print()
    scenario_P0_brick()
    print()
    scenario_S4()
