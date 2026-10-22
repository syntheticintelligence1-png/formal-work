import os, re, sys
src, out = sys.argv[1], sys.argv[2]
lines = open(src, encoding='utf-8').read().split('\n')
files = []
i = 0
hdr = re.compile(r'^FILE: (\S.*?)\s+\((\d+) lines\)\s*$')
while i < len(lines):
    m = hdr.match(lines[i])
    if m and i > 0 and lines[i-1].startswith('====') and lines[i+1].startswith('===='):
        files.append((m.group(1), int(m.group(2)), i+2))  # content starts at index i+2 (0-based)
    i += 1
for path, n, start in files:
    body = lines[start:start+n]
    dst = os.path.join(out, path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write('\n'.join(body) + '\n')
    # sanity: next line after body should be blank or separator
    nxt = lines[start+n] if start+n < len(lines) else ''
    if nxt.strip() not in ('',) and not nxt.startswith('===='):
        print('WARN boundary', path, repr(nxt[:60]))
print(len(files), 'files extracted')
