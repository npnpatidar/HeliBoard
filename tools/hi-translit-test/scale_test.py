#!/usr/bin/env python3
"""
Scale-test for the Hindi transliteration dictionary (hi_translit.json).

Reimplements the EXACT algorithm of
app/src/main/java/helium314/keyboard/event/HindiTranslitCombiner.kt:
  - patterns scanned in file order, first match wins
  - rules evaluated with prefix/suffix scopes, "!" negative, exact values
  - fallback: passthrough of the original char
"""
import json
import sys

ROOT = "app/src/main/assets/hi_translit.json"
WORDS = "tools/hi-translit-test/words_1000.txt"

doc = json.load(open(ROOT, encoding="utf-8"))
pats = doc["patterns"]
VOW = set(doc["vowel"])
CON = set(doc["consonant"])


def cls(c):
    l = c.lower()
    if l in VOW:
        return "vowel"
    if l in CON:
        return "consonant"
    return "punctuation"


def ev_rule(rule, s, start, end):
    for m in rule["matches"]:
        chk = end if m["type"] == "suffix" else start - 1
        scope = m["scope"]
        neg = scope.startswith("!")
        core = scope[1:] if neg else scope
        if core == "punctuation":
            base = chk < 0 or chk >= len(s) or cls(s[chk]) == "punctuation"
        elif core == "vowel":
            base = 0 <= chk < len(s) and s[chk].lower() in VOW
        elif core == "consonant":
            base = 0 <= chk < len(s) and s[chk].lower() in CON
        elif core == "exact":
            if m["type"] == "suffix":
                seg = s[end:end + len(m["value"])]
            else:
                seg = s[max(0, start - len(m["value"])):start]
            base = seg == m["value"]
        else:
            base = False
        if base == neg:
            return None
    return rule["replace"]


def convert(word):
    out = []
    pos = 0
    n = len(word)
    while pos < n:
        rep = None
        flen = 1
        for p in pats:
            f = p["find"]
            if word[pos:pos + len(f)] != f:
                continue
            flen = len(f)
            if p.get("rules"):
                for r in p["rules"]:
                    rep = ev_rule(r, word, pos, pos + len(f))
                    if rep is not None:
                        break
                if rep is None:
                    rep = p["replace"]
            else:
                rep = p["replace"]
            break
        if rep is None:
            rep = word[pos]
        out.append(rep)
        pos += flen
    return "".join(out)


def main():
    words = [w.strip() for w in open(WORDS, encoding="utf-8") if w.strip()]
    print(f"loaded {len(words)} words, {len(pats)} patterns")

    # ---- golden set: hand-verified conversions (word, expected) ----
    golden = [
        ("namaste", "नमस्ते"), ("nam", "नम"), ("kya", "क्या"),
        ("hai", "है"), ("aur", "और"), ("kaun", "कौन"),
        ("kaa", "का"), ("ab", "अब"), ("soona", "सून"),
        ("itihas", "इतिहस"), ("om", "ओम"), ("ek", "एक"),
        ("aam", "आम"), ("aap", "आप"),        ("diidhaar", "दीधार"),  # ii = long ई
        ("shankar", "शंकर"), ("rang", "रंग"),
        ("sangeet", "संगीत"),
        ("kshetra", "क्षेत्र"), ("shyam", "श्याम"),
        ("diya", "दिया"),
        ("waqt", "वक़्त"),    # adjacent consonants = cluster (q+t is a cluster pair)
        ("waq^t", "वक़्त"),   # ^ = explicit virama, same result
        ("pranam", "प्रनम"), ("krishna", "क्रिश्न"),
        ("bharat", "भरत"), ("vidya", "विद्या"),        ("ashok", "अशोक"), ("upar", "उपर"),
        # composite marks composed with ^ (no plain-typing collisions)
        ("maa^^", "माँ"),      # ^^ = chandrabindu
        ("do^kaan", "दॉकान"),  # o^ = candra-o (ॉ/ऑ); typed as a unit after the consonant
        ("ke^", "कॅ"),        # e^ = candra-e (ॅ/ऍ)
        ("Lok", "ळोक"),       # L = ळ
        ("rri", "ऋ"),
        ("shrii", "श्री"),     # shr = full cluster श्र; ृ needs the explicit virama
        ("shr^rri", "श्र्ऋ"),   # post-virama rri is standalone ऋ (engine semantics)
        ("bhraataa", "भ्राता"),  # Bhr = full cluster भ्र
        ("gart", "गर्त"), ("gar^t", "गर्त"),           # direct + explicit forms
        ("ThaakarDaa", "ठाकरडा"), ("tumhaaraa", "तुम्हारा"), ("tum^haaraa", "तुम्हारा"),
        # long vowels are written doubled in this scheme
        ("gangaa", "गंगा"), ("bhaarat", "भारत"), ("raam", "राम"),
        ("namas^kaar", "नमस्कार"),  # sk reserved bare (uske); ^ = the exception
        ("usne", "उसने"), ("uske", "उसके"), ("karte", "करते"), ("kamraa", "कमरा"),
        ("zindagii", "ज़िन्दगी"), ("chhoTaa", "छोटा"),  # nd is a legal cluster; anusvara only for ng/nk/nch
        ("vishwaas", "विश्वास"), ("duaa", "दुआ"), ("Admii", "आदमी"),
        # word-initial capital vowels -> independent vowels
        ("Upar", "ऊपर"),    ("Itihas", "ईतिहस"),
        # capital retroflex combos
        ("Dhola", "ढोल"), ("Thola", "ठोल"),
    ]

    # ---- shift / case checks (engine is case-sensitive for these) ----
    shift = [
        ("d", "द"), ("D", "ड"), ("t", "त"), ("T", "ट"),
        ("n", "न"), ("N", "ण"), ("y", "य"), ("Y", "य"),
        ("z", "ज़"), ("Z", "झ"),
        ("g", "ग"), ("G", "ग़"), ("s", "स"), ("S", "श"),
        ("b", "ब"), ("B", "ब"), ("bh", "भ"), ("Bh", "भ"),
    ]

    # ---- pattern coverage sanity ----
    finds = [p["find"] for p in pats]
    dupes = {f for f in finds if finds.count(f) > 1}
    empty_rep = [p["find"] for p in pats if p.get("replace", "") == "" and not p.get("rules")]
    print(f"patterns: {len(pats)} | duplicate finds: {sorted(dupes) or 'none'} "
          f"| plain-empty replacements: {empty_rep or 'none'}")

    print("\n--- golden set ---")
    fails = 0
    for w, exp in golden:
        got = convert(w)
        mark = "OK " if got == exp else "FAIL"
        if got != exp:
            fails += 1
            print(f"  {mark} {w}: got {got!r} expected {exp!r}")
        else:
            print(f"  {mark} {w} -> {got}")
    print(f"golden: {len(golden) - fails}/{len(golden)} pass")

    print("\n--- shift/case set ---")
    sfails = 0
    for w, exp in shift:
        got = convert(w)
        mark = "OK " if got == exp else "FAIL"
        if got != exp:
            sfails += 1
        print(f"  {mark} {w} -> {got} (expected {exp})")
    print(f"shift: {len(shift) - sfails}/{len(shift)} pass")

    print("\n--- 1000-word scale run ---")
    out_lines = []
    anomalies = []
    for w in words:
        got = convert(w)
        out_lines.append(f"{w}\t{got}")
        # anomaly heuristics on the OUTPUT Devanagari:
        # 1. stray Latin chars surviving inside output (unmapped chars)
        if any(ch.isascii() and ch.isalpha() for ch in got):
            anomalies.append((w, got, "latin residue"))
        # 2. matra (vowel sign) at word start — impossible in valid Devanagari
        elif got and got[0] in "ािीुूृेैोौंः्":
            anomalies.append((w, got, "leading matra"))
        # 3. bare virama at word end (dangling half-form)
        elif got.endswith("्"):
            anomalies.append((w, got, "trailing virama"))
        # 4. doubled matra sequences (e.g. ाा)
        elif any(got[i] == got[i + 1] and got[i] in "ािीुूृेैोौ" for i in range(len(got) - 1)):
            anomalies.append((w, got, "doubled matra"))
        # 5. virama followed by independent vowel (invalid cluster)
        elif any(got[i] == "्" and got[i + 1] in "अइउएओऔआईऊऋ" for i in range(len(got) - 1)):
            anomalies.append((w, got, "virama+independent vowel"))

    with open("tools/hi-translit-test/results.tsv", "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"converted {len(words)} words -> results.tsv")
    print(f"anomalies: {len(anomalies)}")
    for w, got, why in anomalies[:40]:
        print(f"  [{why}] {w} -> {got}")
    if len(anomalies) > 40:
        print(f"  ... and {len(anomalies) - 40} more")

    total_fail = fails + sfails + len(anomalies)
    print(f"\nTOTAL: {'PASS' if total_fail == 0 else 'FAIL'} "
          f"(golden {len(golden) - fails}/{len(golden)}, shift {len(shift) - sfails}/{len(shift)}, "
          f"anomalies {len(anomalies)}/{len(words)})")
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
