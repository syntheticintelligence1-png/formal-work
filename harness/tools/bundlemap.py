"""Map extracted-file line numbers back to gigabundle.txt line numbers (FILE header + 1 + k)."""
import re


def header_lines(bundle_path):
    m = {}
    hdr = re.compile(r"^FILE: (\S.*?)\s+\((\d+) lines\)\s*$")
    for i, line in enumerate(open(bundle_path, encoding="utf-8"), start=1):
        g = hdr.match(line.rstrip("\n"))
        if g:
            m[g.group(1)] = i
    return m


def to_bundle(where, hdrs):
    path, k = where.rsplit(":", 1)
    return hdrs[path] + 1 + int(k) if path in hdrs else None
