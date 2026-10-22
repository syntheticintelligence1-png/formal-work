# Solidity-faithful integer model of kernel K4 as instantiated in the f(x) rebalance pools.
# Sources (bundle line numbers):
#   DecrementalFloatingPoint.encode/epoch/exponent/magnitude/mul   L16611-L16679
#   BoostableRebalancePool._notifyLoss                             L16381-L16408 (Shareable: L15496-L15522, identical arithmetic)
#   BoostableRebalancePool._getCompoundedBalance                   L16430-L16475 (Shareable: L15544-L15589, identical)
#   MultipleRewardCompoundingAccumulator._accumulateReward         L17133-L17153
#   MultipleRewardCompoundingAccumulator._claimable                L17032-L17052
# Semantics: Python ints, floor division for '/', explicit checks where solc 0.8 checks,
# explicit wrap where the code is `unchecked` or uses assembly, explicit truncation on casts.

PREC = 10**18
HALF = 10**9
U24 = (1 << 24) - 1
U64 = (1 << 64) - 1
U96 = (1 << 96) - 1
U104 = (1 << 104) - 1
U112 = (1 << 112) - 1
U192 = (1 << 192) - 1


class Revert(Exception):
    pass


def chk(v, maxv, what):
    """checked arithmetic result in [0, maxv]; otherwise Panic(0x11)."""
    if v < 0 or v > maxv:
        raise Revert("Panic(0x11) overflow/underflow in " + what)
    return v


def div(a, b, what):
    if b == 0:
        raise Revert("Panic(0x12) division by zero in " + what)
    return a // b


# ---- DecrementalFloatingPoint (L16611-L16679) ----
def encode(ep, ex, mag):
    # assembly: prod := add(_magnitude, add(shl(64, _exponent), shl(88, _epoch)))  (no masking)
    return mag + (ex << 64) + (ep << 88)


def epoch(p):
    return (p >> 88) & U24          # shr(88, prod) on a uint112 value


def exponent(p):
    return (p >> 64) & 0xFFFFFF     # and(shr(64, prod), 0xffffff)


def epoch_exponent(p):
    return p >> 64                  # shr(64, prod)


def magnitude(p):
    return p & U64                  # and(prod, 0xffffffffffffffff)


def dfp_mul(prod, scale):
    ep, ex, mag = epoch(prod), exponent(prod), magnitude(prod)
    # unchecked block L16664-L16675
    if scale == 0:
        ep = (ep + 1) & U24
        ex = 0
        mag = PREC
    elif (scale * mag) // PREC < HALF:
        ex = (ex + 1) & U24
        mag = (mag * scale) // HALF
    else:
        mag = (mag * scale) // PREC
    return encode(ep, ex, mag & U64)  # uint64(_magnitude) cast


def fmt(p):
    return "(epoch %d, exp %d, mag %d)" % (epoch(p), exponent(p), magnitude(p))


# ---- pool state + _notifyLoss (L16381-L16408) ----
class Pool:
    def __init__(self):
        self.S = 0                       # _totalSupply.amount (uint104)
        self.prod = encode(0, 0, PREC)   # _totalSupply.product, initialize() L16088
        self.err = 0                     # lastAssetLossError
        self.bal = {}                    # user -> (amount, product)
        self.integral = {}               # epochExponent -> integral (uint192), one reward token
        self.usnap = {}                  # user -> integral snapshot
        self.pending = {}                # user -> pending (uint128)
        self.queued = 0

    # -- reward accumulation, one token (L17133-L17153) --
    def accumulate(self, amount):
        if amount == 0:
            return
        S = self.S
        if S == 0:
            self.queued = (self.queued + (amount & U96))  # queued += uint96(_amount) (checked add on uint96)
            chk(self.queued, U96, "queued")
            return
        key = epoch_exponent(self.prod)
        mag = magnitude(self.prod)
        inc = ((amount * PREC) // S) & U192          # uint192(...) explicit cast truncates
        inc = chk(inc * mag, U192, "uint192 mul L17151")  # uint192 * uint192, checked
        self.integral[key] = chk(self.integral.get(key, 0) + inc, U192, "integral += L17151")

    # -- _claimable (L17032-L17052) --
    def claimable(self, u):
        amt, p = self.bal.get(u, (0, encode(0, 0, PREC)))
        pend = self.pending.get(u, 0)
        if amt == 0:
            return pend
        key = epoch_exponent(p)
        mag = magnitude(p)
        first = chk(self.integral.get(key, 0) - self.usnap.get(u, 0), U192, "first portion")
        second = self.integral.get(key + 1, 0) // HALF
        return pend + div(amt * (first + second), mag * PREC, "_claimable L17051")

    # -- _getCompoundedBalance (L16430-L16475) --
    @staticmethod
    def compounded(b, pu, pc):
        if b == 0:
            return 0
        if epoch(pu) < epoch(pc):
            return 0
        d = chk(exponent(pc) - exponent(pu), U24, "uint24 exponent diff L16445")
        if d == 0:
            c = div(b * magnitude(pc), magnitude(pu), "_getCompoundedBalance L16452")
        elif d == 1:
            c = div(b * magnitude(pc), magnitude(pu), "_getCompoundedBalance L16456") // HALF
        else:
            c = 0
        if c < b // 10**9:
            c = 0
        return c

    # -- user checkpoint (Boostable _checkpoint L16298-L16331 without gauge/boost) --
    def checkpoint(self, u):
        pend = self.claimable(u)
        self.pending[u] = pend & ((1 << 128) - 1)    # uint128 cast
        self.usnap[u] = self.integral.get(epoch_exponent(self.prod), 0)
        amt, p = self.bal.get(u, (0, self.prod))
        self.bal[u] = (self.compounded(amt, p, self.prod), self.prod)

    def deposit(self, u, d):
        self.checkpoint(u)
        amt, p = self.bal[u]
        self.S = chk(self.S + d, U104, "supply")
        self.bal[u] = (amt + d, p)

    def withdraw(self, u, d):
        self.checkpoint(u)
        amt, p = self.bal[u]
        d = min(d, amt)
        if d == 0:
            raise Revert("WithdrawZeroAmount")
        self.S -= d
        self.bal[u] = (amt - d, p)
        return d

    def notify_loss(self, loss):
        S = self.S
        if loss >= S:
            x = PREC
            self.err = 0
            S = 0
        else:
            num = chk(loss * PREC - self.err, (1 << 256) - 1, "_lossNumerator L16392")
            x = num // S + 1
            self.err = x * S - num
            S = S - (loss & U104)
        f = chk(PREC - x, (1 << 256) - 1, "_newProductFactor L16402")
        self.prod = dfp_mul(self.prod, f & U64)
        self.S = S
        return x, f

    def liquidate(self, L, base_out=0):
        # liquidate(): _checkpoint(0) [no time passes in the model], redeem, _accumulateReward(base), _notifyLoss
        if base_out:
            self.accumulate(base_out)
        return self.notify_loss(L)
