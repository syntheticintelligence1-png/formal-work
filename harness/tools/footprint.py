"""Mechanized SBD action footprints from solc compact-JSON ASTs (Hardhat build-info).

For every external/public entry function of every concrete bundle contract this emits the ordered event trace of
its inlined call tree (modifiers, internal/library/super calls resolved against the contract's C3 linearization):

  ('R', var)               storage read          ('W', var)        storage write
  ('T',)                   block.timestamp read  ('L', lock)       nonReentrant entry
  ('X', label, cls, static, member, path)        external call; cls in {Y0, YP, YU, Yext, self, ?}; static = view/pure
  ('B', token, cls)        balanceOf(address(this)) read (balance-differential read site)
  ('G', why)               sender-gating evidence (msg.sender compared against storage / role check)

Approximations (stated so the atlas is read correctly): branches are concatenated (an over-approximation of the
path set), loops are walked once, and calls through function-typed variables are not resolved. Storage roots are
followed through member/index chains, local `storage` pointers and library `storage` parameters.
"""

import json
import re
import sys
from collections import defaultdict

BUILTIN_FUNCS = {
    "require", "assert", "revert", "keccak256", "sha256", "ripemd160", "ecrecover", "addmod", "mulmod", "gasleft",
    "blockhash", "selfdestruct", "type",
}
GATE_MODIFIER = re.compile(r"only|Only|auth|Auth|whitelist|Whitelist|Role|initializer|reinitializer")
INIT_MODIFIER = re.compile(r"^(initializer|reinitializer|onlyInitializing)$")


class Ctx:
    def __init__(self, contract, defining, alias=None, pcls=None, entry=False, stack=()):
        self.C = contract          # concrete contract node (dispatch context)
        self.D = defining          # contract that defines the code being walked
        self.alias = alias or {}   # local/param declaration id -> storage root name
        self.pcls = pcls or {}     # local/param declaration id -> (cls, label) of the value it holds
        self.entry = entry
        self.stack = stack


class Job:
    def __init__(self, path):
        d = json.load(open(path))
        self.version = d["solcVersion"]
        self.ids = {}
        self.src_of = {}
        self.owner = {}
        self.line_starts = {}
        sources_in = d["input"]["sources"]
        for src, s in d["output"]["sources"].items():
            self._index(s["ast"], src, None)
            text = sources_in.get(src, {}).get("content", "")
            starts = [0]
            for i, ch in enumerate(text.encode("utf-8")):
                if ch == 10:
                    starts.append(i + 1)
            self.line_starts[src] = starts
        self.events = []
        self.overflow = False

    def _index(self, n, src, owner):
        if isinstance(n, dict):
            if "nodeType" in n and "id" in n:
                self.ids[n["id"]] = n
                self.src_of[n["id"]] = src
                if n["nodeType"] == "ContractDefinition":
                    owner = n["id"]
                self.owner[n["id"]] = owner
            for k, v in n.items():
                self._index(v, src, owner)
        elif isinstance(n, list):
            for v in n:
                self._index(v, src, owner)

    def scope(self, node):
        return node.get("scope") if node.get("nodeType") == "FunctionDefinition" and "scope" in node else self.owner.get(node["id"])

    # ------------------------------------------------------------------ helpers
    def line(self, node):
        src = self.src_of.get(node["id"])
        off = int(node["src"].split(":")[0])
        starts = self.line_starts.get(src, [0])
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def where(self, node):
        src = self.src_of.get(node["id"], "")
        return f"{src.replace('contracts/bundle/', '')}:{self.line(node)}"

    def cname(self, cid):
        n = self.ids.get(cid)
        return n["name"] if n else "?"

    def varname(self, decl):
        return f"{self.cname(decl.get('scope'))}.{decl['name']}"

    def is_state(self, decl):
        return decl is not None and decl["nodeType"] == "VariableDeclaration" and decl.get("stateVariable")

    def sig(self, fn):
        return (fn.get("name"), fn.get("kind"),
                tuple(p["typeDescriptions"].get("typeString", "") for p in fn["parameters"]["parameters"]))

    def resolve_virtual(self, fn, C, after=None):
        """Most-derived implementation of `fn` in C's linearization (optionally strictly after contract `after`)."""
        lin = C["linearizedBaseContracts"]
        if after is not None and after in lin:
            lin = lin[lin.index(after) + 1:]
        s = self.sig(fn)
        for cid in lin:
            cn = self.ids.get(cid)
            if not cn:
                continue
            for n in cn.get("nodes", []):
                if n.get("nodeType") == "FunctionDefinition" and self.sig(n) == s and n.get("implemented", True) and n.get("body"):
                    return n
        return fn if fn.get("body") else None

    def resolve_modifier(self, mdef, C):
        for cid in C["linearizedBaseContracts"]:
            cn = self.ids.get(cid)
            if not cn:
                continue
            for n in cn.get("nodes", []):
                if n.get("nodeType") == "ModifierDefinition" and n["name"] == mdef["name"] and n.get("body"):
                    return n
        return mdef

    def emit(self, ev, ctx):
        if len(self.events) > 60000:
            self.overflow = True
            return
        self.events.append(ev + (ctx.stack,))

    # ------------------------------------------------------------------ classification of address-valued expressions
    def classify(self, e, ctx):
        t = e["nodeType"]
        if t == "Literal":
            return ("Y0", e.get("value", "lit"))
        if t == "Identifier":
            d = self.ids.get(e.get("referencedDeclaration"))
            if e.get("name") == "this":
                return ("self", "this")
            if d is None:
                return ("?", e.get("name", "?"))
            if d["id"] in ctx.pcls:
                return ctx.pcls[d["id"]]
            if self.is_state(d):
                if d.get("constant") or d.get("mutability") == "immutable":
                    return ("Y0", self.varname(d))
                return ("YP", self.varname(d))
            if d["nodeType"] == "VariableDeclaration":
                return ("YU", d["name"]) if ctx.entry and self.is_param_of_entry(d, ctx) else ("?", d["name"])
            return ("?", e.get("name", "?"))
        if t == "MemberAccess":
            base = e["expression"]
            if base.get("nodeType") == "Identifier" and base.get("name") == "msg" and e["memberName"] == "sender":
                return ("YU", "msg.sender")
            if base.get("nodeType") == "Identifier" and base.get("name") == "tx" and e["memberName"] == "origin":
                return ("YU", "tx.origin")
            r = self.root_state(e, ctx)
            if r:
                return ("YP", r + "." + e["memberName"])
            return ("?", e["memberName"])
        if t == "IndexAccess":
            r = self.root_state(e, ctx)
            if r:
                return ("YP", r + "[]")
            return ("?", "index")
        if t == "FunctionCall":
            if e.get("kind") == "typeConversion" and e["arguments"]:
                return self.classify(e["arguments"][0], ctx)
            ce = e["expression"]
            if ce.get("nodeType") == "Identifier" and ce.get("name") == "_msgSender":
                return ("YU", "msg.sender")
            ts = ce.get("typeDescriptions", {}).get("typeString", "")
            if " external" in ts:
                return ("Yext", ce.get("memberName", "call()"))
            return ("?", "call")
        if t == "TupleExpression" and len(e.get("components") or []) == 1 and e["components"][0]:
            return self.classify(e["components"][0], ctx)
        return ("?", t)

    def is_param_of_entry(self, d, ctx):
        return d["id"] in getattr(ctx, "entry_params", set())

    def root_state(self, e, ctx):
        while True:
            t = e["nodeType"]
            if t == "MemberAccess":
                e = e["expression"]
            elif t == "IndexAccess":
                e = e["baseExpression"]
            elif t == "FunctionCall" and e.get("kind") == "typeConversion":
                e = e["arguments"][0]
            elif t == "Identifier":
                d = self.ids.get(e.get("referencedDeclaration"))
                if d is None:
                    return None
                if d["id"] in ctx.alias:
                    return ctx.alias[d["id"]]
                if self.is_state(d) and not d.get("constant"):
                    return self.varname(d)
                return None
            else:
                return None

    # ------------------------------------------------------------------ statements
    def stmt(self, s, ctx, placeholder=None):
        if s is None:
            return
        t = s["nodeType"]
        if t in ("Block", "UncheckedBlock"):
            for x in s["statements"]:
                self.stmt(x, ctx, placeholder)
        elif t == "ExpressionStatement":
            self.expr(s["expression"], ctx)
        elif t == "VariableDeclarationStatement":
            init = s.get("initialValue")
            if init is not None:
                self.expr(init, ctx)
                decls = s["declarations"]
                if len(decls) == 1 and decls[0] is not None:
                    d = decls[0]
                    if d.get("storageLocation") == "storage":
                        r = self.root_state(init, ctx)
                        if r:
                            ctx.alias[d["id"]] = r
                    ts = d.get("typeDescriptions", {}).get("typeString", "")
                    if ts.startswith("address") or ts.startswith("contract"):
                        ctx.pcls[d["id"]] = self.classify(init, ctx)
        elif t == "IfStatement":
            self.expr(s["condition"], ctx)
            self.stmt(s["trueBody"], ctx, placeholder)
            self.stmt(s.get("falseBody"), ctx, placeholder)
        elif t == "ForStatement":
            self.stmt(s.get("initializationExpression"), ctx, placeholder)
            if s.get("condition"):
                self.expr(s["condition"], ctx)
            self.stmt(s["body"], ctx, placeholder)
            self.stmt(s.get("loopExpression"), ctx, placeholder)
        elif t in ("WhileStatement", "DoWhileStatement"):
            self.expr(s["condition"], ctx)
            self.stmt(s["body"], ctx, placeholder)
        elif t == "Return":
            if s.get("expression"):
                self.expr(s["expression"], ctx)
        elif t in ("EmitStatement",):
            for a in s["eventCall"].get("arguments", []):
                self.expr(a, ctx)
        elif t == "RevertStatement":
            for a in s["errorCall"].get("arguments", []):
                self.expr(a, ctx)
        elif t == "PlaceholderStatement":
            if placeholder:
                placeholder()
        elif t == "InlineAssembly":
            ops = json.dumps(s.get("AST", {}))
            if '"sstore"' in ops:
                self.emit(("W", f"{self.cname(ctx.D)}.<assembly-slot>"), ctx)
            if '"sload"' in ops:
                self.emit(("R", f"{self.cname(ctx.D)}.<assembly-slot>"), ctx)
            if '"timestamp"' in ops:
                self.emit(("T",), ctx)
            for ref in s.get("externalReferences", []):
                d = self.ids.get(ref.get("declaration"))
                if self.is_state(d) and not d.get("constant"):
                    self.emit(("R", self.varname(d)), ctx)
        elif t == "TryStatement":
            self.expr(s["externalCall"], ctx)
            for c in s["clauses"]:
                self.stmt(c["block"], ctx, placeholder)
        # Break / Continue / others: no footprint

    # ------------------------------------------------------------------ expressions
    def write_target(self, e, ctx):
        if e["nodeType"] == "TupleExpression":
            for c in e.get("components") or []:
                if c is not None:
                    self.write_target(c, ctx)
            return
        # evaluate index expressions (reads)
        x = e
        while x["nodeType"] in ("MemberAccess", "IndexAccess"):
            if x["nodeType"] == "IndexAccess":
                if x.get("indexExpression"):
                    self.expr(x["indexExpression"], ctx)
                x = x["baseExpression"]
            else:
                x = x["expression"]
        r = self.root_state(e, ctx)
        if r:
            self.emit(("W", r), ctx)

    def expr(self, e, ctx):
        if e is None:
            return
        t = e["nodeType"]
        if t == "Identifier":
            d = self.ids.get(e.get("referencedDeclaration"))
            if d is not None:
                if d["id"] in ctx.alias:
                    self.emit(("R", ctx.alias[d["id"]]), ctx)
                elif self.is_state(d) and not d.get("constant"):
                    self.emit(("R", self.varname(d)), ctx)
        elif t == "MemberAccess":
            b = e["expression"]
            if b.get("nodeType") == "Identifier" and b.get("name") == "block" and e["memberName"] == "timestamp":
                self.emit(("T",), ctx)
                return
            self.expr(b, ctx)
        elif t == "IndexAccess":
            self.expr(e["baseExpression"], ctx)
            self.expr(e.get("indexExpression"), ctx)
            ie = e.get("indexExpression")
            if ie is not None and e.get("typeDescriptions", {}).get("typeString") == "bool" and self.is_sender(ie, ctx) and self.root_state(e, ctx):
                self.emit(("G", "bool storage mapping indexed by msg.sender"), ctx)
        elif t == "IndexRangeAccess":
            self.expr(e["baseExpression"], ctx)
            self.expr(e.get("startExpression"), ctx)
            self.expr(e.get("endExpression"), ctx)
        elif t == "Assignment":
            self.expr(e["rightHandSide"], ctx)
            if e["operator"] != "=":
                self.expr(e["leftHandSide"], ctx)
            self.write_target(e["leftHandSide"], ctx)
        elif t == "UnaryOperation":
            self.expr(e["subExpression"], ctx)
            if e["operator"] in ("++", "--", "delete"):
                self.write_target(e["subExpression"], ctx)
        elif t == "BinaryOperation":
            self.expr(e["leftExpression"], ctx)
            self.expr(e["rightExpression"], ctx)
            if e["operator"] in ("==", "!="):
                self.sender_gate(e, ctx)
        elif t == "Conditional":
            self.expr(e["condition"], ctx)
            self.expr(e["trueExpression"], ctx)
            self.expr(e["falseExpression"], ctx)
        elif t == "TupleExpression":
            for c in e.get("components") or []:
                self.expr(c, ctx)
        elif t == "FunctionCall":
            self.call(e, ctx)
        elif t == "FunctionCallOptions":
            self.expr(e["expression"], ctx)
            for o in e.get("options", []):
                self.expr(o, ctx)
        elif t == "NewExpression":
            tn = e.get("typeName", {})
            if tn.get("nodeType") == "UserDefinedTypeName":
                self.emit(("X", "new " + tn.get("pathNode", {}).get("name", tn.get("name", "?")), "?", False, "new", ""), ctx)

    def is_sender(self, e, ctx):
        c = self.classify(e, ctx)
        return c == ("YU", "msg.sender")

    def has_state_read(self, e, ctx):
        found = []

        def rec(x):
            if isinstance(x, dict):
                if x.get("nodeType") == "Identifier":
                    d = self.ids.get(x.get("referencedDeclaration"))
                    if self.is_state(d) or (d is not None and d["id"] in ctx.alias):
                        found.append(1)
                    if x.get("name") == "owner":
                        found.append(1)
                if x.get("nodeType") == "FunctionCall":
                    ce = x.get("expression", {})
                    if ce.get("name") in ("owner",) or ce.get("memberName") in ("owner",):
                        found.append(1)
                for v in x.values():
                    rec(v)
            elif isinstance(x, list):
                for v in x:
                    rec(v)

        rec(e)
        return bool(found)

    def sender_gate(self, e, ctx):
        l, r = e["leftExpression"], e["rightExpression"]
        if (self.is_sender(l, ctx) and self.has_state_read(r, ctx)) or (self.is_sender(r, ctx) and self.has_state_read(l, ctx)):
            self.emit(("G", "msg.sender compared with storage"), ctx)

    def call(self, e, ctx):
        kind = e.get("kind")
        args = e.get("arguments", [])
        if kind == "typeConversion":
            for a in args:
                self.expr(a, ctx)
            return
        if kind == "structConstructorCall":
            for a in args:
                self.expr(a, ctx)
            return
        ce = e["expression"]
        value_opt = False
        if ce["nodeType"] == "FunctionCallOptions":
            names = ce.get("names", [])
            value_opt = "value" in names
            for o in ce.get("options", []):
                self.expr(o, ctx)
            ce = ce["expression"]
        ts = ce.get("typeDescriptions", {}).get("typeString", "")
        if ce["nodeType"] == "Identifier":
            name = ce.get("name")
            d = self.ids.get(ce.get("referencedDeclaration"))
            for a in args:
                self.expr(a, ctx)
            if name in BUILTIN_FUNCS or d is None:
                if name in ("hasRole", "_checkRole"):
                    self.emit(("G", name), ctx)
                return
            if d["nodeType"] == "FunctionDefinition":
                if d["name"] in ("hasRole", "_checkRole", "_checkOwner"):
                    self.emit(("G", d["name"]), ctx)
                if d["name"] == "ensureCallerIsHarvester":
                    self.emit(("G", "cond:harvester-or-unset"), ctx)
                callee = d if self.ids[d["scope"]].get("contractKind") == "library" else self.resolve_virtual(d, ctx.C)
                self.inline(callee, args, None, ctx)
            return
        if ce["nodeType"] == "MemberAccess":
            member = ce["memberName"]
            base = ce["expression"]
            if member in ("push", "pop") and "storage" in base.get("typeDescriptions", {}).get("typeString", ""):
                for a in args:
                    self.expr(a, ctx)
                r = self.root_state(base, ctx)
                if r:
                    self.emit(("W", r), ctx)
                return
            if base.get("nodeType") == "Identifier" and base.get("name") == "abi":
                for a in args:
                    self.expr(a, ctx)
                return
            if " external" in ts:
                self.expr(base, ctx)
                for a in args:
                    self.expr(a, ctx)
                cls, label = self.classify(base, ctx)
                static = bool(re.search(r"\) (view|pure) external", ts))
                self.emit(("X", label, cls, static, member, ts, self.where(e)), ctx)
                if member == "balanceOf" and args and self.classify(args[0], ctx)[0] == "self":
                    self.emit(("B", label, cls, self.where(e)), ctx)
                return
            btype = base.get("typeDescriptions", {}).get("typeString", "")
            if member in ("call", "delegatecall", "staticcall", "send", "transfer") and btype.startswith("address"):
                self.expr(base, ctx)
                for a in args:
                    self.expr(a, ctx)
                cls, label = self.classify(base, ctx)
                via = [f for _, f in ctx.stack if f.split(".")[0].startswith("SafeERC20")]
                mlabel = via[0].split(".", 1)[1] if via else member + ("{value}" if value_opt or member in ("send", "transfer") else "")
                if not via and any(f.endswith("Address.sendValue") for _, f in ctx.stack):
                    mlabel = "sendValue"
                self.emit(("X", label, cls, member == "staticcall", mlabel, ts, self.where(e)), ctx)
                return
            d = self.ids.get(ce.get("referencedDeclaration"))
            if d is not None and d["nodeType"] == "FunctionDefinition":
                if d["name"] in ("hasRole", "_checkRole"):
                    self.emit(("G", d["name"]), ctx)
                scope = self.ids.get(d["scope"], {})
                if base.get("nodeType") == "Identifier" and base.get("name") == "super":
                    callee = self.resolve_virtual(d, ctx.C, after=ctx.D)
                    for a in args:
                        self.expr(a, ctx)
                    self.inline(callee, args, None, ctx)
                    return
                if scope.get("contractKind") == "library":
                    bound = None
                    bdecl = self.ids.get(base.get("referencedDeclaration")) if base.get("nodeType") == "Identifier" else None
                    if not (bdecl is not None and bdecl.get("nodeType") == "ContractDefinition"):
                        bound = base  # using-for: first parameter is the bound expression
                        self.expr(base, ctx)
                    for a in args:
                        self.expr(a, ctx)
                    self.inline(d, args, bound, ctx)
                    return
                # contract-qualified internal call, e.g. Base.f(...)
                self.expr(base, ctx)
                for a in args:
                    self.expr(a, ctx)
                self.inline(d if d.get("body") else self.resolve_virtual(d, ctx.C), args, None, ctx)
                return
            self.expr(base, ctx)
            for a in args:
                self.expr(a, ctx)
            return
        # call on an arbitrary expression (e.g. function-typed value)
        self.expr(ce, ctx)
        for a in args:
            self.expr(a, ctx)

    def inline(self, fn, args, bound, ctx):
        if fn is None or not fn.get("body"):
            return
        if fn["id"] in [s[0] for s in ctx.stack] or len(ctx.stack) > 30:
            return
        params = fn["parameters"]["parameters"]
        actuals = ([bound] if bound is not None else []) + list(args)
        alias, pcls = {}, {}
        for p, a in zip(params, actuals):
            if a is None:
                continue
            if p.get("storageLocation") == "storage":
                r = self.root_state(a, ctx)
                if r:
                    alias[p["id"]] = r
            pcls[p["id"]] = self.classify(a, ctx)
        child = Ctx(ctx.C, fn["scope"], alias, pcls, False, ctx.stack + ((fn["id"], f"{self.cname(fn['scope'])}.{fn['name'] or fn['kind']}"),))
        self.run_modifiers(fn, child, 0)

    def run_modifiers(self, fn, ctx, i):
        mods = [m for m in fn.get("modifiers", []) if self.ids.get(m["modifierName"].get("referencedDeclaration"), {}).get("nodeType") == "ModifierDefinition"]
        if i == len(mods):
            self.stmt(fn["body"], ctx)
            return
        m = mods[i]
        mdef = self.resolve_modifier(self.ids[m["modifierName"]["referencedDeclaration"]], ctx.C)
        if mdef["name"] == "nonReentrant":
            self.emit(("L", f"nonReentrant@{self.cname(self.scope(mdef))}"), ctx)
        for a in m.get("arguments") or []:
            self.expr(a, ctx)
        mctx = Ctx(ctx.C, self.scope(mdef), dict(ctx.alias), dict(ctx.pcls), ctx.entry, ctx.stack)
        if hasattr(ctx, "entry_params"):
            mctx.entry_params = ctx.entry_params
        for p, a in zip(mdef["parameters"]["parameters"], m.get("arguments") or []):
            mctx.pcls[p["id"]] = self.classify(a, ctx)
        self.stmt(mdef["body"], mctx, placeholder=lambda: self.run_modifiers(fn, ctx, i + 1))

    # ------------------------------------------------------------------ entry points
    def entry_functions(self, C):
        seen = {}
        for cid in C["linearizedBaseContracts"]:
            cn = self.ids.get(cid)
            if not cn:
                continue
            for n in cn.get("nodes", []):
                if n.get("nodeType") != "FunctionDefinition" or not n.get("body"):
                    continue
                if n.get("kind") not in ("function", "receive", "fallback"):
                    continue
                if n.get("visibility") not in ("external", "public"):
                    continue
                s = self.sig(n)
                if s not in seen:
                    seen[s] = n
        return list(seen.values())

    def trace(self, C, fn):
        self.events = []
        self.overflow = False
        ctx = Ctx(C, fn["scope"], entry=True, stack=((fn["id"], f"{self.cname(fn['scope'])}.{fn['name']}"),))
        ctx.entry_params = {p["id"] for p in fn["parameters"]["parameters"]}
        mods = [self.ids.get(m["modifierName"].get("referencedDeclaration"), {}).get("name", "?") for m in fn.get("modifiers", [])]
        self.run_modifiers(fn, ctx, 0)
        return mods, list(self.events)


def analyse(build_infos):
    rows = []
    for path in build_infos:
        job = Job(path)
        for nid, n in job.ids.items():
            if n["nodeType"] != "ContractDefinition" or n.get("contractKind") != "contract" or n.get("abstract"):
                continue
            src = job.src_of[nid]
            if "contracts/bundle/" not in src:
                continue
            for fn in job.entry_functions(n):
                mods, evs = job.trace(n, fn)
                rows.append(dict(
                    job=job.version, contract=n["name"], file=src.replace("contracts/bundle/", ""),
                    function=fn["name"] or fn["kind"], defined_in=job.cname(fn["scope"]), line=job.line(fn),
                    mutability=fn.get("stateMutability"), modifiers=mods, events=evs, truncated=job.overflow,
                ))
    return rows


RANK = {"Y0": 0, "self": 0, "YP": 1, "Yext": 2, "?": 3, "YU": 4}


def summarise(r):
    evs = r["events"]
    gate_ev = sorted({e[1] for e in evs if e[0] == "G"})
    init = any(INIT_MODIFIER.match(m) for m in r["modifiers"])
    gated_mod = [m for m in r["modifiers"] if GATE_MODIFIER.search(m)]
    hard = [g for g in gate_ev if not g.startswith("cond:")]
    access = "init" if init else ("gated[" + ",".join(gated_mod or ["body"]) + "]" if hard else ("cond[harvester]" if gate_ev else "open"))
    locks = sorted({e[1] for e in evs if e[0] == "L"})
    yields = [e for e in evs if e[0] == "X" and not e[3]]
    statics = [e for e in evs if e[0] == "X" and e[3]]
    writes = [e[1] for e in evs if e[0] == "W"]
    reads = [e[1] for e in evs if e[0] == "R"]
    clock = any(e[0] == "T" for e in evs)
    bdr = sorted({(e[1], e[2]) for e in evs if e[0] == "B"})
    post_yield_writes, worst = [], None
    for e in evs:
        if e[0] == "X" and not e[3]:
            worst = e[2] if worst is None or RANK.get(e[2], 3) > RANK.get(worst, 3) else worst
        elif e[0] == "W" and worst is not None and not e[1].endswith("._status"):
            post_yield_writes.append((worst, e[1]))
    return dict(
        access=access, locks=locks, n_yield=len(yields), yield_cls=sorted({(y[2], y[1], y[4]) for y in yields}),
        n_static=len(statics), clock=clock, writes=sorted(set(writes)), reads=sorted(set(reads)), bdr=bdr,
        post_yield_writes=sorted(set(post_yield_writes)), gate_evidence=gate_ev,
    )


if __name__ == "__main__":
    out = sys.argv[1]
    rows = analyse(sys.argv[2:])
    for r in rows:
        r["summary"] = summarise(r)
        r["events"] = [list(e[:-1]) + [[s[1] for s in e[-1]]] for e in r["events"]]
    json.dump(rows, open(out, "w"), indent=1, default=str)
    print(len(rows), "entry functions written to", out)
