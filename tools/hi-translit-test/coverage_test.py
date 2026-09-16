#!/usr/bin/env python3
"""Coverage test: can the transliteration dict *produce* the words of a real
Hindi dictionary?

Method: reverse index hi_translit.json (every pattern output or rule output ->
roman spelling). For each dictionary word, find a segmentation whose outputs
all exist in the reverse index. Words that fail cannot be typed by the scheme
as it stands -> candidate dict gaps.

NOTE: this is a static *typing-scheme* test (which graphemes exist), not a
simulation of the dynamic engine (context rules can choose between variants at
runtime, e.g. 'a' -> '' after consonant vs 'अ' initially; both variants are
indexed).
"""
import json, sys, collections

DICT = "/tmp/hi_wordlist.combined"
DOC = "app/src/main/assets/hi_translit.json"

doc = json.load(open(DOC, encoding="utf-8"))
pats = doc["patterns"]

# ---- collect every (roman, devanagari) pair the scheme can emit ----
def add(idx, roman, dev):
    idx.setdefault(dev, set()).add(roman)

idx = collections.defaultdict(set)
for p in pats:
    f, r = p["find"], p["replace"]
    add(idx, f, r)
    for rule in p.get("rules") or []:
        rr = rule.get("replace")
        if rr:
            add(idx, f, rr)

# nukta combos are typed via explicit nukta-key sequences: z=ज+nukta etc.
NUKTA = {"क": "क़", "ख": "ख़", "ग": "ग़", "ज": "ज़", "फ": "फ़", "ड": "ड़", "ढ": "ढ़", "य": "य़"}
for base, nukta in list(NUKTA.items()):
    add(idx, "q", nukta)  # any roman works as label; presence is what matters

dev_keys = set(idx.keys())
print(f"distinct devanagari graphemes producible: {len(dev_keys)}")

# ---- load dictionary, sort by frequency desc ----
words = []  # (word, freq)
for line in open(DICT, encoding="utf-8"):
    line = line.strip()
    if not line.startswith("word="):
        continue
    w = line.split("word=", 1)[1].split(",f=")
    if len(w) != 2:
        continue
    words.append((w[0], int(w[1])))
print(f"dictionary words: {len(words)}")

# ---- segmentation check over reverse index ----
def segmentable(word, memo={}):
    if word in memo:
        return memo[word]
    if not word:
        return True
    res = False
    for i in range(1, len(word) + 1):
        if word[:i] in dev_keys and segmentable(word[i:]):
            res = True
            break
    memo[word] = res
    return res

sys.setrecursionlimit(10000)
memo = {}
fails = []
for w, f in words:
    if not segmentable(w, memo):
        fails.append((w, f))
fails.sort(key=lambda x: -x[1])
print(f"\ncannot be typed: {len(fails)} / {len(words)} ({100*len(fails)/len(words):.2f}%)")

# frequency-weighted: how much of real typing does this affect?
total_f = sum(f for _, f in words)
fail_f = sum(f for _, f in fails)
print(f"frequency mass missed: {100*fail_f/total_f:.2f}%")

# ---- which graphemes cause failures? ----
missing = collections.Counter()
for w, f in fails:
    # find longest unknown prefix repeatedly (approximate culprit graphemes)
    i = 0
    while i < len(w):
        matched = False
        for j in range(len(w), i, -1):
            if w[i:j] in dev_keys:
                i = j
                matched = True
                break
        if not matched:
            # single char that has no key
            missing[w[i]] += 1
            i += 1
print("\ntop missing graphemes:")
for ch, n in missing.most_common(20):
    print(f"  {ch!r} U+{ord(ch):04X} in {n} words")

with open("tools/hi-translit-test/coverage_fails.tsv", "w", encoding="utf-8") as out:
    for w, f in fails:
        out.write(f"{w}\t{f}\n")
print("\nwrote tools/hi-translit-test/coverage_fails.tsv")
