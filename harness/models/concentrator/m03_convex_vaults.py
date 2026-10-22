"""
m03 - ConcentratorConvexVault (L10833-L11574, 0.7.6) as instantiated by AladdinFXSConvexVault (L17736-L17877),
plus the harvest of AladdinCRVConvexVault (L12270-L12327).

Custody (C) is modelled per (token, holder) cell. External venues are abstracted as environment actions with
stated contracts (assumptions in the report):
  * Convex BaseRewardPool: getReward() pays `earned[pool]` CRV to msg.sender; getReward(account, claimExtras) is
    callable by ANYONE for ANY account (A-CVX-PERM).
  * zap: converts at fixed mock prices and pays msg.sender (A-ZAP).
  * aFXS (an AladdinCompounder): depositWithFXS/deposit mint shares at price 1 share = KC asset units,
    redeem(shares) pays shares*KC cvxFXS (real token, distinct address) to `receiver` (A-AFXS).
Integer semantics: SafeMath where the code uses .add/.mul/.sub/.div, plain 0.7.6 ops otherwise (wrap), `/` by 0 reverts.
Run: python3 -I m03_convex_vaults.py
"""
import copy
from collections import defaultdict

M256 = 1 << 256


class Revert(Exception):
    pass


def req(c, msg):
    if not c:
        raise Revert(msg)


def smul(a, b):
    req(a * b < M256, "SafeMath: multiplication overflow")
    return a * b


def sadd(a, b):
    req(a + b < M256, "SafeMath: addition overflow")
    return a + b


def ssub(a, b):
    req(b <= a, "SafeMath: subtraction overflow")
    return a - b


def div(a, b):
    req(b != 0, "division by zero (0.7.6 invalid opcode)")
    return a // b


def toU128(x):  # SafeCastUpgradeable.toUint128
    req(x < (1 << 128), "SafeCast: value doesn't fit in 128 bits")
    return x


E18 = 10 ** 18
DAY = 86400
T0 = 1_700_000_000
PRECISION = 10 ** 18
FEE = 10 ** 9

FXS_CONST = "0x3432..(FXS)"  # L17756
CVXFXS_CONST = FXS_CONST  # L17760: SAME address as FXS
CVXFXS_REAL = "0xFEEf..(cvxFXS)"  # the real cvxFXS token: a different address (A-AFXS: aFXS.asset())
CRV = "CRV"
AFXS = "aFXS"
ETH = "ETH"
USDC = "USDC"
KC = 12 * 10 ** 17  # aFXS: 1 share redeems 1.2 cvxFXS (mock price)
ZAP_PRICE = {  # out per 1e18 in
    (CRV, FXS_CONST): E18,
    (FXS_CONST, ETH): 10 ** 15,  # 0.001 ETH per FXS
    (FXS_CONST, USDC): 3 * 10 ** 6,  # 3 USDC (6 decimals) per FXS
    (FXS_CONST, CVXFXS_REAL): 13 * 10 ** 17,
    (CVXFXS_REAL, FXS_CONST): 7 * 10 ** 17,
}


def tx(obj, fn, *a, **k):
    """Top-level call with Solidity revert semantics: vault AND custody/environment state are restored in place."""
    env = obj.env
    saved_obj = copy.deepcopy({k2: v2 for k2, v2 in obj.__dict__.items() if k2 != "env"})
    saved_env = copy.deepcopy(env.__dict__)
    try:
        return fn(*a, **k)
    except Revert:
        for k2 in [k2 for k2 in obj.__dict__ if k2 != "env"]:
            del obj.__dict__[k2]
        obj.__dict__.update(saved_obj)
        env.__dict__.clear()
        env.__dict__.update(saved_env)
        raise


class Env:
    """custody cells + Convex reward pools + zap + aFXS"""

    def __init__(self):
        self.bal = defaultdict(int)  # (token, holder) -> amount
        self.earned = defaultdict(int)  # convex reward pool -> CRV earned by the vault
        self.earned_fxs = defaultdict(int)  # extra reward (FXS) earned by the vault in a pool

    def transfer(self, token, frm, to, amt):
        req(self.bal[(token, frm)] >= amt, f"transfer amount exceeds balance [{token} of {frm}]")
        self.bal[(token, frm)] -= amt
        self.bal[(token, to)] += amt

    def convex_getReward(self, pool, account):  # A-CVX-PERM: anyone may call for any account
        a = self.earned[pool]
        self.earned[pool] = 0
        self.bal[(CRV, "pool:" + pool)] -= 0
        self.bal[(CRV, account)] += a
        f = self.earned_fxs[pool]
        self.earned_fxs[pool] = 0
        self.bal[(FXS_CONST, account)] += f

    def zap(self, caller, frm, amt, to):  # A-ZAP: tokens already sent to zap; output to caller
        out = amt * ZAP_PRICE[(frm, to)] // E18
        self.bal[(frm, "zap")] -= amt
        self.bal[(to, caller)] += out
        return out

    def afxs_depositWithFXS(self, caller, amt):  # pulls FXS, mints shares 1:1/KC
        self.transfer(FXS_CONST, caller, "aFXS", amt)
        sh = amt * E18 // KC
        self.bal[(AFXS, caller)] += sh
        return sh

    def afxs_redeem(self, caller, shares, receiver):
        req(self.bal[(AFXS, caller)] >= shares and shares > 0, "aFXS redeem")
        self.bal[(AFXS, caller)] -= shares
        out = shares * KC // E18
        self.bal[(CVXFXS_REAL, receiver)] += out
        return out


class FXSVault:
    def __init__(self, env, now):
        self.env = env
        self.now = now
        self.pools = []

    def addPool(self, name, rewardTokens, withdrawFee=0):
        self.pools.append(dict(name=name, totalUnderlying=0, totalShare=0, acc=0, tokens=list(rewardTokens),
                               wfee=withdrawFee, pfee=0, bounty=0, rate=0, P=0, lastUpdate=0, finishAt=0,
                               users=defaultdict(lambda: dict(shares=0, rewards=0, paid=0))))
        return len(self.pools) - 1

    # L11393-L11426
    def _updateRewards(self, pid, account):
        p = self.pools[pid]
        acc = p["acc"]
        if p["P"] > 0:
            cur = p["finishAt"]
            if cur > self.now:
                cur = self.now
            dur = cur - p["lastUpdate"] if cur >= p["lastUpdate"] else 0
            if dur > 0:
                p["lastUpdate"] = self.now % (1 << 48)
                if p["totalShare"] > 0:
                    acc = sadd(acc, div(smul(smul(dur, p["rate"]), PRECISION), p["totalShare"]))
                p["acc"] = acc
        if account is not None:
            u = p["users"][account]
            u["rewards"] = toU128(sadd(u["rewards"], div(smul(ssub(acc, u["paid"]), u["shares"]), PRECISION)))
            u["paid"] = acc

    def pendingReward(self, pid, account):  # L11018-L11034 (view)
        p = self.pools[pid]
        acc = p["acc"]
        if p["P"] > 0:
            cur = min(p["finishAt"], self.now)
            dur = cur - p["lastUpdate"] if cur >= p["lastUpdate"] else 0
            if dur > 0 and p["totalShare"] > 0:
                acc = sadd(acc, div(smul(smul(dur, p["rate"]), PRECISION), p["totalShare"]))
        u = p["users"][account]
        return sadd(u["rewards"], div(smul(ssub(acc, u["paid"]), u["shares"]), PRECISION))

    def deposit(self, pid, user, amt):  # L11087-L11112 + _deposit L11433-L11463 (LP custody abstracted)
        req(amt > 0, "deposit zero amount")
        self._updateRewards(pid, user)
        p = self.pools[pid]
        S, U = p["totalShare"], p["totalUnderlying"]
        out = amt if S == 0 else div(smul(amt, S), U)
        p["totalShare"] = toU128(sadd(S, out))
        p["totalUnderlying"] = toU128(sadd(U, amt))
        p["users"][user]["shares"] += out
        return out

    def withdraw(self, pid, user, shares):  # L11115-L11143 + _withdraw L11471-L11508
        self._updateRewards(pid, user)
        p = self.pools[pid]
        u = p["users"][user]
        req(shares <= u["shares"], "shares not enough")
        S, U = p["totalShare"], p["totalUnderlying"]
        if shares == S:
            out = U
        else:
            out = div(smul(shares, U), S)
            out = out - div(smul(out, p["wfee"]), FEE)
        p["totalShare"] = toU128(S - shares)
        p["totalUnderlying"] = toU128(U - out)
        u["shares"] -= shares
        return out

    def _notifyHarvestedReward(self, pid, amount):  # L11533-L11555
        p = self.pools[pid]
        if p["P"] == 0:
            p["acc"] = sadd(p["acc"], div(smul(amount, PRECISION), p["totalShare"]))
        else:
            req(amount < (1 << 128) - 1, "harvested amount overflow")
            if self.now >= p["finishAt"]:
                p["rate"] = (amount // p["P"]) % (1 << 128)
            else:
                rem = p["finishAt"] - self.now
                p["rate"] = ((amount + rem * p["rate"]) // p["P"]) % (1 << 128)
            p["lastUpdate"] = self.now % (1 << 48)
            p["finishAt"] = (self.now + p["P"]) % (1 << 48)

    def _zapAsRewardToken(self, tokens, amounts):  # L17837-L17876
        aFXS_out = 0
        amountFXS = 0
        amountCvx = 0
        branches = []
        for t, a in zip(tokens, amounts):
            if t == FXS_CONST:
                amountFXS = sadd(amountFXS, a)
                branches.append("FXS-branch")
            elif t == CVXFXS_CONST:  # unreachable: CVXFXS_CONST == FXS_CONST
                amountCvx = sadd(amountCvx, a)
                branches.append("cvxFXS-branch")
            elif a > 0:
                self.env.transfer(t, "vault", "zap", a)
                amountFXS = sadd(amountFXS, self.env.zap("vault", t, a, FXS_CONST))
                branches.append("zap-branch")
        if amountCvx > 0:
            raise AssertionError("cvxFXS branch reached")
        if amountFXS > 0:
            aFXS_out = sadd(aFXS_out, self.env.afxs_depositWithFXS("vault", amountFXS))
        return aFXS_out, branches

    def harvest(self, pid, minOut=0):  # L11195-L11237
        p = self.pools[pid]
        self._updateRewards(pid, None)
        self.env.convex_getReward(p["name"], "vault")
        balances = [self.env.bal[(t, "vault")] for t in p["tokens"]]  # BDR: whole vault balance
        rewards, branches = self._zapAsRewardToken(p["tokens"], balances)
        req(rewards >= minOut, "insufficient rewards")
        self._notifyHarvestedReward(pid, rewards)
        return rewards, branches

    def claim(self, pid, sender, recipient, minOut, claimAs):  # L11146-L11164
        self._updateRewards(pid, sender)
        u = self.pools[pid]["users"][sender]
        r = u["rewards"]
        u["rewards"] = 0
        return self._claim(r, minOut, sender, recipient, claimAs)

    def _claim(self, amount, minOut, sender, recipient, claimAs):  # L17804-L17834
        if claimAs == AFXS:
            out = amount
        else:
            out = self.env.afxs_redeem("vault", amount, "vault")
            if claimAs != CVXFXS_CONST:  # i.e. claimAs != FXS
                self.env.transfer(CVXFXS_CONST, "vault", "zap", out)  # moves FXS, not cvxFXS
                out = self.env.zap("vault", CVXFXS_CONST, out, claimAs)
        req(out >= minOut, "insufficient rewards")
        if claimAs == ETH:
            self.env.transfer(ETH, "vault", sender, amount)  # msg.sender.call{value: _amount}
        else:
            self.env.transfer(claimAs, "vault", recipient, out)
        return out


def show_cells(env, holders=("vault",), tokens=(CRV, FXS_CONST, CVXFXS_REAL, AFXS, ETH)):
    return {f"{t}@{h}": env.bal[(t, h)] for h in holders for t in tokens if env.bal[(t, h)]}


def scenario_cross_pool():
    print("== cross-pool absorption: harvest(A) reads whole-vault balances (L11209-L11213) ==")
    for push in (False, True):
        env = Env()
        v = FXSVault(env, T0)
        a = v.addPool("A", [CRV])
        b = v.addPool("B", [CRV])
        v.deposit(a, "alice", 100 * E18)
        v.deposit(b, "bob", 100 * E18)
        env.earned["A"] = 60 * E18  # 60 CRV -> 60 FXS -> 50e18 aFXS shares (KC = 1.2)
        env.earned["B"] = 60 * E18
        if push:
            env.convex_getReward("B", "vault")  # R1: BaseRewardPool(B).getReward(vault, true)
        rA, _ = v.harvest(a)
        rB, _ = v.harvest(b)
        print(f"  R1 push of B's rewards={push}: harvest(A) -> {rA} aFXS, harvest(B) -> {rB} aFXS; "
              f"pending alice={v.pendingReward(a, 'alice')} bob={v.pendingReward(b, 'bob')}")


def scenario_alias_claim():
    print("== FXS/cvxFXS type aliasing in _claim (L17816-L17830) ==")
    env = Env()
    v = FXSVault(env, T0)
    a = v.addPool("A", [CRV])
    c = v.addPool("C", [FXS_CONST])  # a pool whose convex rewards include FXS
    v.deposit(a, "alice", 100 * E18)
    v.deposit(c, "carol", 100 * E18)
    env.earned["A"] = 120 * E18
    v.harvest(a)
    print(f"  alice pending aFXS = {v.pendingReward(a, 'alice')}; vault cells = {show_cells(env)}")
    for claimAs in (FXS_CONST, CVXFXS_REAL, USDC, ETH):
        try:
            out = tx(v, v.claim, a, "alice", "alice_rx", 0, claimAs)
            print(f"  claim as {claimAs}: OK {out}")
        except Revert as e:
            print(f"  claim as {claimAs}: REVERT('{e}')  <- vault holds no FXS")
    print("  -- now some FXS (pool C's unharvested extra reward) sits in the vault (R1: getReward(vault) on C) --")
    env.earned_fxs["C"] = 150 * E18
    env.convex_getReward("C", "vault")
    print(f"  vault cells = {show_cells(env)}")
    env2 = copy.deepcopy(env)
    v2 = copy.deepcopy(v)
    v2.env = env2
    out = v.claim(a, "alice", "alice_rx", 0, FXS_CONST)
    print(f"  alice claim as FXS: received {env.bal[(FXS_CONST, 'alice_rx')]} FXS (= redeemed cvxFXS amount {out}); "
          f"vault cells now {show_cells(env)}")
    r, _ = v.harvest(c)
    print(f"  harvest(C) afterwards -> {r} aFXS for carol (should be {150 * E18 * E18 // KC} without the alias); "
          f"carol pending={v.pendingReward(c, 'carol')}")
    print("  -- ETH branch (L17825-L17828) sends `_amount` (aFXS shares) to msg.sender, not `_amountOut` to recipient --")
    try:
        tx(v2, v2.claim, a, "alice", "alice_rx", 0, ETH)
    except Revert as e:
        print(f"  claim as ETH with no ETH in vault: REVERT('{e}')")
    env2.bal[(ETH, "vault")] += 200 * E18  # donation / stranded ETH
    out = v2.claim(a, "alice", "alice_rx", 0, ETH)
    print(f"  claim as ETH with 200e18 wei in vault: returns _amountOut={out}; msg.sender(alice) got "
          f"{env2.bal[(ETH, 'alice')]} wei; recipient(alice_rx) got {env2.bal[(ETH, 'alice_rx')]}; "
          f"vault ETH left {env2.bal[(ETH, 'vault')]}")


def scenario_dead_branch():
    print("== _zapAsRewardToken branch reachability with FXS == cvxFXS ==")
    env = Env()
    v = FXSVault(env, T0)
    env.bal[(FXS_CONST, "vault")] = 10 * E18
    out, br = v._zapAsRewardToken([CVXFXS_CONST], [10 * E18])
    print(f"  tokens=[cvxFXS constant] -> branches {br}, aFXS out {out} (deposited via depositWithFXS, never aFXS.deposit)")
    env.bal[(FXS_CONST, "vault")] = 10 * E18
    try:
        tx(v, v._zapAsRewardToken, [FXS_CONST, CVXFXS_CONST], [10 * E18, 10 * E18])
    except Revert as e:
        print(f"  tokens=[FXS, cvxFXS] with balances read twice (L11211-L11213) -> REVERT('{e}') (double count)")


def scenario_period_zero():
    print("== updateRewardPeriod(pid, 0) mid-stream (owner, L11330-L11336) ==")
    for settle in (False, True):
        env = Env()
        v = FXSVault(env, T0)
        a = v.addPool("A", [CRV])
        v.pools[a]["P"] = 7 * DAY
        v.deposit(a, "alice", 100 * E18)
        v.deposit(a, "carol", 100 * E18)
        env.earned["A"] = 700 * E18 * KC // E18  # so that 700e18 aFXS shares are notified
        v.harvest(a)
        v.now = T0 + 1 * DAY
        if settle:
            v._updateRewards(a, None)
        v.pools[a]["P"] = 0
        v.now = T0 + 2 * DAY
        v.withdraw(a, "alice", 100 * E18)
        ra = v.pools[a]["users"]["alice"]["rewards"]
        v.now = T0 + 10 * DAY
        v.pools[a]["P"] = 7 * DAY
        v._updateRewards(a, "carol")
        rc = v.pools[a]["users"]["carol"]["rewards"]
        print(f"  settle*={settle}: alice (exits +2d) rewards={ra}; carol at +10d rewards={rc}")


def scenario_empty_interval():
    print("== ConcentratorConvexVault: stream during totalShare == 0 is skipped (L11406-L11415) ==")
    env = Env()
    v = FXSVault(env, T0)
    a = v.addPool("A", [CRV])
    v.pools[a]["P"] = 7 * DAY
    v.deposit(a, "alice", 100 * E18)
    env.earned["A"] = 700 * E18 * KC // E18
    v.harvest(a)
    v.now = T0 + 1 * DAY
    v.withdraw(a, "alice", 100 * E18)
    v.now = T0 + 3 * DAY
    v.deposit(a, "bob", 100 * E18)
    v.now = T0 + 8 * DAY
    v._updateRewards(a, "bob")
    ra = v.pools[a]["users"]["alice"]["rewards"]
    rb = v.pools[a]["users"]["bob"]["rewards"]
    print(f"  alice={ra} bob={rb} sum={ra + rb}; aFXS custody={env.bal[(AFXS, 'vault')]}; orphaned={env.bal[(AFXS, 'vault')] - ra - rb}")


def scenario_acrv_vault():
    print("== AladdinCRVConvexVault.harvest (L12279-L12305): ETH balance + whole CRV balance swept into harvested pool ==")
    # immediate distribution: acc += rewards*1e18/totalShare (L12322)
    bal = {"CRV": 0, "ETH": 0}
    earned = {"A": 50 * E18, "B": 50 * E18}
    acc = {"A": 0, "B": 0}
    S = {"A": 100 * E18, "B": 100 * E18}
    bal["CRV"] += earned["B"]
    earned["B"] = 0  # R1: getReward(vault) on B's BaseRewardPool
    for pid in ("A", "B"):
        bal["CRV"] += earned[pid]
        earned[pid] = 0
        amt = bal["CRV"]
        bal["CRV"] = 0
        acc[pid] += amt * PRECISION // S[pid] if amt else 0
    print(f"  pending A-holder={acc['A'] * S['A'] // PRECISION} B-holder={acc['B'] * S['B'] // PRECISION} (reference 50e18 each)")


if __name__ == "__main__":
    scenario_cross_pool()
    print()
    scenario_alias_claim()
    print()
    scenario_dead_branch()
    print()
    scenario_period_zero()
    print()
    scenario_empty_interval()
    print()
    scenario_acrv_vault()
