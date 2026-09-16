#!/usr/bin/env python3
"""Generate consonant-consonant conjunct patterns for hi_translit.json.

Scheme: adjacent consonant letters in the INPUT mean a cluster is intended
(gart -> गर्त, waqt -> वक़्त, chandra -> चन्द्र). A vowel letter between
consonants separates them (karte -> करते, dayaa -> दया, pariikshaa intact).

Per-pair decisions from the AOSP Hindi wordlist, counted in INPUT space:
  cluster votes : dev junction c1+्+c2 (user wants the cluster; types c1c2)
  bare votes    : dev bare junction c1|c2 that yields input adjacency —
                  only when c1 is non-initial, unmarked, and c2 carries a
                  matra (schwa deleted: karte/usne/kamraa), and c2 is not
                  य/व (schwa survives before semivowels: dayaa/savaal)
Full cluster when cv >= RATIO*bv (or manual), else bare-shape:
  cluster at word-end / before consonant / word-start, bare before vowels.
  (Ratio, not majority: करते/उसके-shape bare forms must survive when both
  usages are substantial, while प्र/क्र-type pairs where bare forms are
  negligible stay full-cluster so prem/prakaar/krodh work before vowels.)

Upstream patterns that are pure c1+c2 clusters (st->स्त, sk->स्क ...) are
removed and regenerated data-driven; single-consonant digraphs (Bh->भ,
kh->ख) and the nasal series (ng->ंग, nk->ंक) are kept untouched.
"""
import json, re, unicodedata, collections

WORDLIST = '/tmp/hi_wordlist.combined'
DICT = 'app/src/main/assets/hi_translit.json'

VIRAMA = '्'
NUKTA = '़'
DEV_CONS = set('कखगघङचछजझटठडढणतथदधनपफबभमयरलवशषसहळ')
DEV_VOWELFOLLOW = set('ािीुूृॄेैोौॉॅॉंँ')
NO_BARE_VOTE = {'य', 'व'}

RATIO = 3
MANUAL_CLUSTER = {('म', 'ह')}   # तुम्हारा/तुम्हें (explicit user request)
# sk must stay bare-shape: उसका/इसकी compounds are written as separate
# words so the wordlist undercounts them; स्क (school/risk) still types
# directly via word-start/end rules
MANUAL_BARE = {('स', 'क'), ('र', 'ड')}
# rD: ठाकरडा/सरडा-type names beat the अर्डर loanword (अर्डर = ar^Dar)
# ksh decomposes as k|sh -> (क,श) but क्ष is क+ष;
# shn -> श्न (कृष्ण is typed k-r-i-s-h-n but its dev cluster is ष्+ण, so
# the (श,न) pair has no wordlist evidence — शन-adjacency is untyped anyway)
FIND_OVERRIDES = {'ksh': 'क्ष', 'shn': 'श्न'}
MIN_WEIGHT = 100                # ignore pairs with less total wordlist evidence


def cons_at(w, i):
    """Consonant grapheme at w[i] (base + optional nukta), else None."""
    if i < len(w) and w[i] in DEV_CONS:
        if i + 1 < len(w) and w[i + 1] == NUKTA:
            return w[i] + NUKTA
        return w[i]
    return None


def tokenize(w):
    """-> list of ('C', graph) / ('V',) / ('O', char) tokens."""
    toks, j, n = [], 0, len(w)
    while j < n:
        c = cons_at(w, j)
        if c:
            toks.append(('C', c)); j += len(c); continue
        if w[j] == VIRAMA:
            toks.append(('V',)); j += 1; continue
        toks.append(('O', w[j])); j += 1
    return toks


def main():
    # ---------- 1. load dict, derive roman unit map ----------
    doc = json.load(open(DICT, encoding='utf-8'))
    pats = doc['patterns']

    def is_single_cons(rep):
        core = rep.replace(NUKTA, '')
        return len(rep) - len(core) <= 1 and len(core) == 1 and core in DEV_CONS

    # single-consonant finds become roman units (base replacement, even if
    # the pattern carries contextual rules)
    ROM2DEV = {p['find']: p['replace'] for p in pats
               if is_single_cons(p['replace']) and p['find'] != 'w'}
    UNITS = sorted(ROM2DEV, key=len, reverse=True)
    U2_SET = {u for u in UNITS if u not in ('y', 'v')}
    print(f'roman units: {len(ROM2DEV)} (u2 candidates: {len(U2_SET)})')

    # ---------- 2. classify upstream pure-pair cluster shortcuts ----------
    def classify(p):
        rep = p['replace']
        if VIRAMA not in rep:
            return 'keep'      # single cons (Bh->भ) or nasal series (ng->ंग)
        f = p['find']
        for i in range(1, len(f)):
            if f[:i] in ROM2DEV and f[i:] in U2_SET:
                return 'regen'
        return 'keep'

    removed = [p['find'] for p in pats if classify(p) == 'regen']
    block_at = next((i for i, p in enumerate(pats) if classify(p) == 'regen'), len(pats))
    pats = [p for p in pats if classify(p) == 'regen' and False] or \
           [p for p in doc['patterns'] if classify(p) != 'regen']
    print(f'regenerating {len(removed)} upstream shortcuts: {sorted(removed)}')
    existing = {p['find'] for p in pats}

    # ---------- 3. analyze wordlist in input space ----------
    stats = collections.defaultdict(lambda: {'cluster': 0, 'bare': 0})
    words = 0
    for line in open(WORDLIST, encoding='utf-8'):
        m = re.match(r' word=([^,]+),f=(\d+)', line)
        if not m:
            continue
        w, f = unicodedata.normalize('NFC', m.group(1)), int(m.group(2))
        words += 1
        toks = tokenize(w)
        for k in range(len(toks) - 1):
            if toks[k][0] != 'C':
                continue
            nxt = toks[k + 1]
            if nxt == ('V',) and k + 2 < len(toks) and toks[k + 2][0] == 'C':
                stats[(toks[k][1], toks[k + 2][1])]['cluster'] += f
            elif nxt[0] == 'C':
                # bare junction: c1 non-initial & unmarked, c2 not य/व,
                # c2 carries a matra sign
                if k == 0 or toks[k - 1][0] == 'V':
                    continue
                if nxt[1] in NO_BARE_VOTE:
                    continue
                after = toks[k + 2] if k + 2 < len(toks) else None
                if after and after[0] == 'O' and after[1] in DEV_VOWELFOLLOW:
                    stats[(toks[k][1], nxt[1])]['bare'] += f
    print(f'wordlist: {words} words, {len(stats)} dev pairs with evidence')

    # ---------- 4. build pair patterns ----------
    generated, seen, table = [], set(), []
    for u1 in UNITS:
        for u2 in sorted(U2_SET, key=len, reverse=True):
            find = u1 + u2
            if find in existing or find in seen:
                continue
            d1, d2 = ROM2DEV[u1], ROM2DEV[u2]
            s = stats.get((d1, d2))
            if not s:
                continue
            cv, bv = s['cluster'], s['bare']
            if cv + bv < MIN_WEIGHT:
                continue
            cluster_rep = d1 + VIRAMA + d2
            bare_rep = d1 + d2
            if find in FIND_OVERRIDES:
                generated.append({'find': find, 'replace': FIND_OVERRIDES[find]})
                seen.add(find)
                table.append((find, True, cv, bv))
                continue
            full_cluster = (((d1, d2) in MANUAL_CLUSTER) or (cv >= RATIO * bv)) \
                and (d1, d2) not in MANUAL_BARE
            if full_cluster:
                generated.append({'find': find, 'replace': cluster_rep})
            else:
                # cluster at end/consonant/word-start, bare before vowels
                rules = [
                    {'replace': cluster_rep, 'matches': [{'type': 'suffix', 'scope': '!vowel'}]},
                    {'replace': cluster_rep, 'matches': [{'type': 'prefix', 'scope': 'punctuation'}]},
                    {'replace': bare_rep, 'matches': [{'type': 'suffix', 'scope': 'vowel'}]},
                ]
                generated.append({'find': find, 'replace': cluster_rep, 'rules': rules})
            seen.add(find)
            table.append((find, full_cluster, cv, bv))

    # longest finds first so extensions (rri) land before their prefixes (rr)
    generated.sort(key=lambda p: (-len(p['find']), p['find']))
    # insert each pair AFTER the last kept/generated pattern whose find
    # extends it (rr must not shadow rri, shr must not shadow shrri),
    # else at the old shortcut block position (before single consonants,
    # so full-cluster pairs like pr still beat p+r)
    result = list(pats)
    for p in generated:
        pos = block_at
        for i, q in enumerate(result):
            if len(q['find']) > len(p['find']) and q['find'].startswith(p['find']):
                pos = i + 1
        result.insert(pos, p)
    doc['patterns'] = result

    letters = set(doc.get('casesensitive', ''))
    for p in doc['patterns']:
        letters.update(ch for ch in p['find'] if ch.isalpha())
    doc['casesensitive'] = ''.join(sorted(letters))

    json.dump(doc, open(DICT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    full = sum(1 for _, fc, _, _ in table if fc)
    print(f'generated {len(generated)} pair patterns '
          f'({full} full-cluster, {len(table) - full} bare-shape); dict now {len(doc["patterns"])} patterns')

    table.sort(key=lambda t: -(t[2] + t[3]))
    print(f"\n{'find':8} {'mode':13} {'cluster':>8} {'bare':>8}")
    for find, fc, cv, bv in table[:50]:
        print(f'{find:8} {"CLUSTER" if fc else "bare-shape":13} {cv:>8} {bv:>8}')


if __name__ == '__main__':
    main()
