"""AMOMath (bundle L9990-L10170, pragma 0.7.6, NO SafeMath -> wrapping uint256 arithmetic),
the AladdinCVX split search (L9148-L9182), and a reference Curve factory plain 2-pool written
with Vyper semantics (checked arithmetic, `assert D1 > D0`), used as the environment
(assumption A-CRV1..3 in the REPORT).  Rates are 1e18 for both coins (18-decimal CVX/clevCVX).
"""
from solsem import Revert, require, U256

A_PRECISION = 100
FEE_DENOMINATOR = 10**10
UNIT = 10**9

# ---------------------------------------------------------------- AMOMath (unchecked)
def w(x):
    return x % U256

def d(a, b):
    if b == 0:
        raise Revert("AMOMath: division by zero (0.7 INVALID)")
    return a // b

def getInvariant(amp, x, y):  # L10005-L10045
    s = w(x + y)
    if s == 0:
        return 0
    inv = s
    amp = w(amp * 2)
    for _ in range(255):
        dp = d(d(w(d(w(inv * inv), x) * inv), y), 4)
        prev = inv
        num = w(w(d(w(amp * s), A_PRECISION) + w(dp * 2)) * inv)
        den = w(d(w(w(amp - A_PRECISION) * inv), A_PRECISION) + w(3 * dp))
        inv = d(num, den)
        if inv > prev:
            if inv - prev <= 1:
                return inv
        else:
            if prev - inv <= 1:
                return inv
    raise Revert("invariant not converging")

def getTokenOut(amp, inv, x):  # L10051-L10087
    amp = w(amp * 2)
    b = w(x + d(w(inv * A_PRECISION), amp))
    c = d(w(inv * inv), w(x * 2))
    c = d(w(w(c * inv) * A_PRECISION), w(amp * 2))
    y = inv
    for _ in range(255):
        prev = y
        y = d(w(w(y * y) + c), w(w(w(2 * y) + b) - inv))
        if y > prev:
            if y - prev <= 1:
                return y
        else:
            if prev - y <= 1:
                return y
    raise Revert("y not converging")

def addLiquidity(amp, fee, supply, x, y, dx, dy):  # L10098-L10151
    fee = fee // 2
    inv0 = getInvariant(amp, x, y)
    dx = w(dx + x)
    dy = w(dy + y)
    inv1 = getInvariant(amp, dx, dy)
    diff_x = d(w(inv1 * x), inv0)
    diff_y = d(w(inv1 * y), inv0)
    diff_x = w(diff_x - dx) if diff_x > dx else w(dx - diff_x)
    diff_y = w(diff_y - dy) if diff_y > dy else w(dy - diff_y)
    diff_x = d(w(diff_x * fee), FEE_DENOMINATOR)
    diff_y = d(w(diff_y * fee), FEE_DENOMINATOR)
    nx = w(dx - diff_x // 2)
    ny = w(dy - diff_y // 2)
    dx = w(dx - diff_x)
    dy = w(dy - diff_y)
    inv1 = getInvariant(amp, dx, dy)
    supply = d(w(supply * w(inv1 - inv0)), inv0)
    return (nx, ny, supply)

def swap(amp, fee, x, y, dx):  # L10159-L10169
    inv = getInvariant(amp, x, y)
    dy = w(w(y - getTokenOut(amp, inv, w(x + dx))) - 1)
    return w(dy - d(w(dy * fee), FEE_DENOMINATOR))

def searchSplit(pool, dx, num, den, baseIndex=0, debtIndex=1):  # AladdinCVX L9148-L9182
    fee = pool.fee
    amp = pool.A_precise
    supply = pool.totalSupply
    x = pool.balances[baseIndex]
    y = pool.balances[debtIndex]
    left, right = 0, dx // UNIT
    while left < right:
        mid = (left + right + 1) // 2
        swap_out = w(dx - mid * UNIT)
        new_x, new_y, add_out = addLiquidity(amp, fee, supply, x, y, w(mid * UNIT), 0)
        swap_out = swap(amp, fee, new_x, new_y, swap_out)
        if w(add_out * den) <= w(num * swap_out):
            left = mid
        else:
            right = mid - 1
    return left * UNIT

# ---------------------------------------------------------------- Curve reference (Vyper, checked)
def cs(a, b):
    require(a >= b, "vyper: uint256 underflow")
    return a - b

def cd(a, b):
    require(b != 0, "vyper: division by zero")
    return a // b

class CurvePlain2:
    N = 2
    ADMIN_FEE = 5 * 10**9

    def __init__(self, b0, b1, A=50, fee=4 * 10**6, supply=None):
        self.balances = [b0, b1]
        self.A_precise = A * A_PRECISION
        self.fee = fee
        self.totalSupply = supply if supply is not None else self.get_D(self.balances)

    def get_D(self, xp, amp=None):
        amp = self.A_precise if amp is None else amp
        S = sum(xp)
        if S == 0:
            return 0
        D = S
        Ann = amp * self.N
        for _ in range(255):
            D_P = D
            for x in xp:
                D_P = cd(D_P * D, x * self.N)
            Dprev = D
            D = cd((cd(Ann * S, A_PRECISION) + D_P * self.N) * D,
                   cd((Ann - A_PRECISION) * D, A_PRECISION) + (self.N + 1) * D_P)
            if abs(D - Dprev) <= 1:
                return D
        raise Revert("curve: get_D no convergence")

    def get_y(self, i, j, x, xp):
        amp = self.A_precise
        D = self.get_D(xp)
        c = D
        S_ = 0
        Ann = amp * self.N
        for k in range(self.N):
            if k == i:
                _x = x
            elif k != j:
                _x = xp[k]
            else:
                continue
            S_ += _x
            c = cd(c * D, _x * self.N)
        c = cd(c * D * A_PRECISION, Ann * self.N)
        b = S_ + cd(D * A_PRECISION, Ann)
        y = D
        for _ in range(255):
            yp = y
            y = cd(y * y + c, cs(2 * y + b, D))
            if abs(y - yp) <= 1:
                return y
        raise Revert("curve: get_y no convergence")

    def add_liquidity(self, amounts, min_mint):
        old = list(self.balances)
        D0 = self.get_D(old)
        new = [old[k] + amounts[k] for k in range(2)]
        if self.totalSupply == 0:
            require(all(a > 0 for a in amounts), "curve: initial deposit requires all coins")
        D1 = self.get_D(new)
        require(D1 > D0, "curve: assert D1 > D0")
        if self.totalSupply > 0:
            base_fee = self.fee * self.N // (4 * (self.N - 1))
            for k in range(2):
                ideal = D1 * old[k] // D0
                diff = ideal - new[k] if ideal > new[k] else new[k] - ideal
                f = base_fee * diff // FEE_DENOMINATOR
                self.balances[k] = new[k] - f * self.ADMIN_FEE // FEE_DENOMINATOR
                new[k] -= f
            D2 = self.get_D(new)
            mint = self.totalSupply * (D2 - D0) // D0
        else:
            self.balances = new
            mint = D1
        require(mint >= min_mint, "curve: Slippage screwed you")
        self.totalSupply += mint
        return mint

    def get_dy(self, i, j, dx):
        xp = list(self.balances)
        y = self.get_y(i, j, xp[i] + dx, xp)
        dy = cs(cs(xp[j], y), 1)
        return dy - dy * self.fee // FEE_DENOMINATOR

    def exchange(self, i, j, dx, min_dy):
        old = list(self.balances)
        y = self.get_y(i, j, old[i] + dx, old)
        dy = cs(cs(old[j], y), 1)
        dy_fee = dy * self.fee // FEE_DENOMINATOR
        dy = dy - dy_fee
        require(dy >= min_dy, "curve: Exchange resulted in fewer coins than expected")
        admin = dy_fee * self.ADMIN_FEE // FEE_DENOMINATOR
        self.balances[i] = old[i] + dx
        self.balances[j] = cs(cs(old[j], dy), admin)
        return dy
