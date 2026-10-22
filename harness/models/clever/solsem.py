"""Solidity integer-semantics helpers (exact mirrors, no floating point).

pragma 0.7.6 everywhere in the CLever scope:
  * plain + - * on uintN wrap modulo 2^N (no overflow check)
  * SafeMath .add/.sub/.mul/.div revert
  * explicit casts uintM(x) truncate to the low M bits
  * division by zero reverts (0.7: INVALID opcode)
"""
import copy

U64 = 2**64
U112 = 2**112
U128 = 2**128
U192 = 2**192
U256 = 2**256
E128 = 2**128


class Revert(Exception):
    pass


def require(cond, msg):
    if not cond:
        raise Revert(msg)


# ---- casts (truncate) ----
def u64(x):
    return x % U64


def u112(x):
    return x % U112


def u128(x):
    return x % U128


def u192(x):
    return x % U192


def u256(x):
    return x % U256


# ---- unchecked uint256 ops (0.7 plain operators) ----
def add256(a, b):
    return (a + b) % U256


def sub256(a, b):
    return (a - b) % U256


def mul256(a, b):
    return (a * b) % U256


def div(a, b):
    if b == 0:
        raise Revert("division by zero (0.7 INVALID)")
    return a // b


# ---- SafeMath (OZ 3.4) ----
def s_add(a, b):
    c = a + b
    require(c < U256, "SafeMath: addition overflow")
    return c


def s_sub(a, b):
    require(b <= a, "SafeMath: subtraction overflow")
    return a - b


def s_mul(a, b):
    c = a * b
    require(c < U256, "SafeMath: multiplication overflow")
    return c


def s_div(a, b):
    require(b > 0, "SafeMath: division by zero")
    return a // b


# ---- SafeCast (OZ 3.4) ----
def sc_u128(x):
    require(x < U128, "SafeCast: value doesn't fit in 128 bits")
    return x


def atomic(obj, fn, *args, **kw):
    """Run fn(*args) as one transaction on obj: on Revert restore the pre-state (EVM atomicity)."""
    snap = copy.deepcopy(obj.__dict__)
    try:
        return ("ok", fn(*args, **kw))
    except Revert as e:
        obj.__dict__.clear()
        obj.__dict__.update(snap)
        return ("revert", str(e))
