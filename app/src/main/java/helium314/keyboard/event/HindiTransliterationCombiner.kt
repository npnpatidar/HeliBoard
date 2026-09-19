// SPDX-License-Identifier: GPL-3.0-only

package helium314.keyboard.event

import helium314.keyboard.keyboard.internal.keyboard_parser.floris.KeyCode
import helium314.keyboard.latin.common.Constants
import java.util.ArrayList

/** Hindi transliteration combiner: QWERTY input → Devanagari via ITRANS-style rules. */
class HindiTransliterationCombiner : Combiner {

    private val composingText = StringBuilder()

    override fun processEvent(previousEvents: ArrayList<Event>?, event: Event): Event {
        if (event.keyCode == KeyCode.SHIFT) return event

        if (event.keyCode == KeyCode.DELETE) {
            if (composingText.isNotEmpty()) {
                val cp = composingText.codePointBefore(composingText.length)
                composingText.delete(composingText.length - Character.charCount(cp), composingText.length)
                if (composingText.isEmpty()) {
                    reset()
                    return Event.createHardwareKeypressEvent(0x20, Constants.CODE_SPACE, 0, event, event.isKeyRepeat)
                }
                return Event.createConsumedEvent(event)
            }
            return event
        }

        val codePoint = event.codePoint
        val isValidCodePoint = codePoint != Integer.MAX_VALUE && Character.isValidCodePoint(codePoint)

        if (event.isFunctionalKeyEvent) return commitAndReset(event)

        if (!isValidCodePoint) return Event.createConsumedEvent(event)

        val isLatinLetter = (codePoint in 'a'.code..'z'.code) || (codePoint in 'A'.code..'Z'.code)
        val isExplicitSign = codePoint == '~'.code || codePoint == '_'.code
                || codePoint == '*'.code || codePoint == '^'.code || codePoint == '`'.code
        if (!isLatinLetter && !isExplicitSign) return commitAndReset(event)

        composingText.append(Character.toChars(codePoint))
        return Event.createConsumedEvent(event)
    }

    override val combiningStateFeedback: CharSequence
        get() = HindiDevanagariTransliterator.transliterate(composingText.toString())

    override fun reset() {
        composingText.setLength(0)
    }

    private fun commitAndReset(event: Event): Event {
        val converted = combiningStateFeedback
        reset()
        return Event.createSoftwareTextEvent(converted, KeyCode.MULTIPLE_CODE_POINTS, event)
    }

    companion object {
        const val SPEC = "hi_transliteration"
    }
}

/** ITRANS-style Devanagari transliterator. */
object HindiDevanagariTransliterator {
    const val VIRAMA = "\u094D"

    // Independent vowels; E/O are candra ऍ/ऑ (plain ए/ओ stay on e/o), so DO→डॉ.
    private val independentVowels = mapOf(
        "a" to "अ", "A" to "आ", "aa" to "आ", "i" to "इ", "I" to "ई", "ii" to "ई",
        "u" to "उ", "U" to "ऊ", "uu" to "ऊ", "Ri" to "ऋ", "r^i" to "ऋ",
        "e" to "ए", "E" to "ऍ", "ee" to "ई", "ai" to "ऐ", "o" to "ओ", "O" to "ऑ", "au" to "औ", "ou" to "औ"
    )
    // Matras ("" = inherent 'a').
    private val matras = mapOf(
        "a" to "", "A" to "ा", "aa" to "ा", "i" to "ि", "I" to "ी", "ii" to "ी",
        "u" to "ु", "U" to "ू", "uu" to "ू", "Ri" to "ृ", "r^i" to "ृ",
        "e" to "े", "E" to "ॅ", "ee" to "ी", "ai" to "ै", "o" to "ो", "O" to "ॉ", "au" to "ौ", "ou" to "ौ"
    )
    // Consonants: lowercase = dental, uppercase = retroflex/special. Uppercase aliases map to
    // the lowercase sound so a stray shift never leaks latin into the output.
    private val consonants = mapOf(
        "k" to "क", "K" to "क", "kh" to "ख", "g" to "ग", "G" to "ग", "gh" to "घ", "ng" to "ङ",
        "ch" to "च", "c" to "च", "chh" to "छ", "Ch" to "छ", "C" to "छ", "j" to "ज", "J" to "ज", "jh" to "झ", "ny" to "ञ",
        "T" to "ट", "Th" to "ठ", "D" to "ड", "Dh" to "ढ", "N" to "ण",
        "t" to "त", "th" to "थ", "d" to "द", "dh" to "ध", "n" to "न",
        "p" to "प", "P" to "प", "ph" to "फ", "b" to "ब", "B" to "ब", "bh" to "भ", "m" to "म",
        "y" to "य", "Y" to "य", "r" to "र", "l" to "ल", "v" to "व", "V" to "व", "w" to "व", "W" to "व",
        "h" to "ह", "sh" to "श", "Sh" to "ष", "S" to "ष", "s" to "स", "x" to "क्ष", "X" to "क्ष",
        "q" to "क़", "Q" to "क़", "z" to "ज़", "Z" to "ज़", "f" to "फ़", "F" to "फ़",
        "R" to "ड़", "Rh" to "ढ़", "L" to "ळ"
    )
    // Conjuncts the generic virama logic gets wrong (ksh→क्स्ह, jny→ज्ज्ञ, shr→श्हर).
    // ज्ञ needs long forms too: short `gya`/`jny` eat the first `a`, so `gyaan` would
    // otherwise end as ज्ञन instead of ज्ञान.
    private val conjuncts = mapOf(
        "ksh" to "क्ष", "kSh" to "क्ष",
        "gyaan" to "ज्ञान", "gyaa" to "ज्ञा", "gya" to "ज्ञ",
        "jnyaan" to "ज्ञान", "jnyaa" to "ज्ञा", "jny" to "ज्ञ",
        "dnyaan" to "ज्ञान", "dnyaa" to "ज्ञा", "dny" to "ज्ञ",
        "SRI" to "श्री", "shr" to "श्र"
    )
    // Extra signs, appended as-is (nukta keeps the syllable open for a following matra).
    // '`' is a zero-width scan barrier: emits nothing, closes the syllable (kha`ike→खइके).
    private val specials = mapOf(
        "M" to "ं", // anusvara
        "H" to "ः", // visarga
        "MM" to "ँ", // chandrabindu
        "~" to "ऽ", // avagraha
        "_" to VIRAMA, // explicit halant
        "*" to "़", // nukta
        "^" to "़", // nukta alias
        "`" to "", // scan barrier
        "OM" to "ॐ" // om syllable (ITRANS: OM→ॐ, not ओं)
    )

    private val allKeys: List<String> =
        (independentVowels.keys + consonants.keys + conjuncts.keys + specials.keys)
            .sortedWith(compareByDescending<String> { it.length }.thenBy { it })

    fun transliterate(input: String): String {
        val out = StringBuilder()
        var i = 0
        var hasConsonant = false
        while (i < input.length) {
            var key = allKeys.firstOrNull { input.regionMatches(i, it, 0, it.length) }
            // `ai`+`i` is a hiatus (गई), not the diphthong (गै): prefer `a`+`ii`. Same for `au`+`u`.
            if ((key == "ai" && input.getOrNull(i + 2) == 'i')
                || (key == "au" && input.getOrNull(i + 2) == 'u')
            ) {
                key = "a"
            }
            if (key == null) {
                out.append(input[i])
                hasConsonant = false
                i++
                continue
            }

            val vowel = independentVowels[key]
            if (vowel != null) {
                if (hasConsonant) out.append(matras.getValue(key)) else out.append(vowel)
                hasConsonant = false
            } else {
                val consonant = consonants[key]
                if (consonant != null) {
                    if (hasConsonant) out.append(VIRAMA)
                    out.append(consonant)
                    hasConsonant = true
                } else {
                    val conjunct = conjuncts[key]
                    if (conjunct != null) {
                        if (hasConsonant) out.append(VIRAMA)
                        out.append(conjunct)
                        // Conjuncts ending in a vowel (ज्ञा, श्री) close the syllable.
                        hasConsonant = key != "SRI" && !key.endsWith("aa") && !key.endsWith("aan")
                    } else {
                        // Nukta combines with the previous consonant, so the syllable stays open.
                        out.append(specials.getValue(key))
                        if (key != "*" && key != "^") hasConsonant = false
                    }
                }
            }
            i += key.length
        }
        return out.toString()
    }
}