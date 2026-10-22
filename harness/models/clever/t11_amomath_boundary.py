"""T11  AMOMath (L9990-L10170) vs its documented derivation / the Curve plain pool it mirrors
(L10001, L10090: "See function get_D / add_liquidity in 0xf9078...").  Random + boundary inputs.
"""
import os, sys, random, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import Revert, U256
import amo_model as M

random.seed(11)
E18 = 10**18

def try_(f, *a):
    try:
        return ("ok", f(*a))
    except Revert as e:
        return ("revert", str(e))

print("=== T11a: random agreement with the Curve reference (A in {10,50,100,1000}, fee 0.04%) ===")
mx_mint = mx_x = mx_swap = 0
mx_rel = 0.0
for _ in range(400):
    b0 = random.randint(10**20, 10**25); b1 = random.randint(10**20, 10**25)
    A = random.choice([10, 50, 100, 1000])
    pool = M.CurvePlain2(b0, b1, A=A)
    dx = random.randint(10**9, b0 // 5)
    nx, ny, mint = M.addLiquidity(pool.A_precise, pool.fee, pool.totalSupply, b0, b1, dx, 0)
    ref = copy.deepcopy(pool)
    rmint = ref.add_liquidity([dx, 0], 0)
    mx_mint = max(mx_mint, abs(mint - rmint)); mx_x = max(mx_x, abs(nx - ref.balances[0]) + abs(ny - ref.balances[1]))
    sdx = random.randint(10**9, b0 // 5)
    s = M.swap(pool.A_precise, pool.fee, ref.balances[0], ref.balances[1], sdx)
    rs = ref.get_dy(0, 1, sdx)
    mx_swap = max(mx_swap, abs(s - rs)); mx_rel = max(mx_rel, abs(s - rs) / max(rs, 1))
print("  max |mint_AMOMath - mint_Curve| = %d wei ; max |new balances diff| = %d wei ; max |swap diff| = %d wei (rel %.2e)" % (
    mx_mint, mx_x, mx_swap, mx_rel))

print()
print("=== T11b: boundary inputs ===")
pool = M.CurvePlain2(1_000_000 * E18, 1_500_000 * E18, A=100)
amp, fee = pool.A_precise, pool.fee
x, y = pool.balances
r = try_(M.swap, amp, fee, x, y, 0)
print("  AMOMath.swap(dx=0)            ->", r, " (wrapped? %s)" % (r[0] == "ok" and r[1] > U256 // 2))
print("  Curve exchange(dx=0)          ->", try_(copy.deepcopy(pool).exchange, 0, 1, 0, 0))
print("  AMOMath.swap(dx=1)            ->", try_(M.swap, amp, fee, x, y, 1))
print("  Curve exchange(dx=1)          ->", try_(copy.deepcopy(pool).exchange, 0, 1, 1, 0))
print("  AMOMath.getInvariant(x=0,y)   ->", try_(M.getInvariant, amp, 0, y))
print("  AMOMath.addLiquidity(dx=0)    ->", try_(M.addLiquidity, amp, fee, pool.totalSupply, x, y, 0, 0))
print("  Curve add_liquidity([0,0])    ->", try_(copy.deepcopy(pool).add_liquidity, [0, 0], 0))

print()
print("=== T11c: _searchSplit boundary behaviour (num/den = AMO lp/debt balances, L9050) ===")
for dx, num, den, why in [
        (5 * 10**8, 60_000 * E18, 50_000 * E18, "dx < UNIT (e.g. donate(1)+dust)"),
        (1000 * E18, 60_000 * E18, 0, "den = 0 (AMO debt balance 0), dx multiple of 1e9"),
        (1000 * E18 + 123, 60_000 * E18, 0, "den = 0, dx not multiple of 1e9"),
        (1000 * E18, 0, 50_000 * E18, "num = 0 (AMO lp balance 0)"),
        (1000 * E18, 60_000 * E18, 50_000 * E18, "regular")]:
    p = copy.deepcopy(pool)
    add = M.searchSplit(p, dx, num, den)
    lp = try_(p.add_liquidity, [add, 0], 0)
    ex = try_(p.exchange, 0, 1, dx - add, 0) if lp[0] == "ok" else ("skipped", None)
    print("  %-48s add=%-26d swap=%-14d add_liquidity=%s exchange=%s" % (why, add, dx - add, lp, ex))

print()
print("=== T11d: monotonicity of add_out/swap_out in the split (binary-search precondition) ===")
dx = 1000 * E18
prev = -1.0; mono = True
for k in range(1, 1000, 37):
    mid = k * dx // 1000 // M.UNIT
    nx, ny, add_out = M.addLiquidity(amp, fee, pool.totalSupply, x, y, mid * M.UNIT, 0)
    so = M.swap(amp, fee, nx, ny, dx - mid * M.UNIT)
    ratio = add_out / so if so else float("inf")
    mono &= ratio >= prev
    prev = ratio
print("  add_out/swap_out non-decreasing over the grid:", mono)

print()
print("=== T11e: random search: does AMOMath.swap(dx in {0,1}) ever wrap (y - getTokenOut(x+dx) - 1 < 0)? ===")
random.seed(99)
wrap = {0: 0, 1: 0}; curve_rev = {0: 0, 1: 0}; n = 3000; example = None
for _ in range(n):
    b0 = random.randint(10**18, 10**26); b1 = random.randint(10**18, 10**26)
    A = random.choice([1, 10, 50, 100, 1000, 5000])
    p = M.CurvePlain2(b0, b1, A=A)
    for dx in (0, 1):
        r = try_(M.swap, p.A_precise, p.fee, b0, b1, dx)
        if r[0] == "ok" and r[1] > U256 // 2:
            wrap[dx] += 1
            example = example or (b0, b1, A, dx, r[1])
        if try_(copy.deepcopy(p).exchange, 0, 1, dx, 0)[0] == "revert":
            curve_rev[dx] += 1
print("  states=%d  AMOMath wraps: dx=0 -> %d, dx=1 -> %d ; Curve exchange reverts: dx=0 -> %d, dx=1 -> %d" % (
    n, wrap[0], wrap[1], curve_rev[0], curve_rev[1]))
print("  example wrap:", example)
