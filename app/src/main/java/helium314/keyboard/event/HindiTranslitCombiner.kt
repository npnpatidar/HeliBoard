// SPDX-License-Identifier: GPL-3.0-only

package helium314.keyboard.event

import helium314.keyboard.keyboard.internal.keyboard_parser.floris.KeyCode
import helium314.keyboard.latin.common.Constants
import helium314.keyboard.latin.settings.Settings
import helium314.keyboard.latin.utils.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.ArrayList

/**
 * Hindi Transliteration combiner — converts Latin phonetically typed text to Devanagari script
 * using a phonetic mapping similar to Gboard's Hindi transliteration.
 *
 * Uses the same generic engine as Avro Phonetic, with a Hindi-specific JSON spec.
 */
class HindiTranslitCombiner(
    private val engine: HindiTranslitEngine = Companion.engine
) : Combiner {

    private val composingText = StringBuilder()
    /** Per-character shift tracking — '1' for shifted, '0' for unshifted. */
    private val shiftFlags = StringBuilder()

    override fun processEvent(previousEvents: ArrayList<Event>?, event: Event): Event {
        val codePoint = event.codePoint

        if (event.keyCode == KeyCode.SHIFT) {
            // Pass through; the shift state is read from each letter's own
            // case below, so the keyboard's auto-unshift after a letter can
            // never desync us (an internal auto-unshift produces no event).
            return event
        }

        if (event.keyCode == KeyCode.DELETE) {
            if (composingText.isNotEmpty()) {
                val cp = composingText.codePointBefore(composingText.length)
                composingText.delete(composingText.length - Character.charCount(cp), composingText.length)
                shiftFlags.deleteCharAt(shiftFlags.length - 1)
                if (composingText.isEmpty()) {
                    reset()
                    return Event.createHardwareKeypressEvent(0x20, Constants.CODE_SPACE, 0, event, event.isKeyRepeat)
                }
                return Event.createConsumedEvent(event)
            }
            return event
        }

        val isValidCodePoint = codePoint != Integer.MAX_VALUE && Character.isValidCodePoint(codePoint)
        val isWhitespace = isValidCodePoint && Character.isWhitespace(codePoint)

        if (event.isFunctionalKeyEvent || isWhitespace) {
            return commitAndReset(event)
        }

        if (!isValidCodePoint) return Event.createConsumedEvent(event)

        // Always store lowercase; the letter event's own case carries the
        // shift info (soft keyboard delivers 'M' when shifted), and
        // per-character flags rebuild case in buildFixedString
        val shifted = Character.isUpperCase(codePoint)
        composingText.append(Character.toChars(Character.toLowerCase(codePoint)))
        shiftFlags.append(if (shifted) '1' else '0')
        return Event.createConsumedEvent(event)
    }

    override val combiningStateFeedback: CharSequence
        get() {
            val fixed = buildFixedString()
            return engine.convert(fixed)
        }

    override fun reset() {
        composingText.setLength(0)
        shiftFlags.setLength(0)
    }

    private fun commitAndReset(event: Event): Event {
        val converted = combiningStateFeedback
        reset()
        return Event.createSoftwareTextEvent(converted, KeyCode.MULTIPLE_CODE_POINTS, event)
    }

    /** Rebuild the fixed string with per-character shift info.
     *  Only case-sensitive characters are uppercased when shifted. */
    private fun buildFixedString(): String {
        val sb = StringBuilder()
        for (i in composingText.indices) {
            val c = composingText[i]
            val shifted = i < shiftFlags.length && shiftFlags[i] == '1'
            sb.append(if (shifted && c in engine.caseSensitiveChars) c.uppercaseChar() else c)
        }
        return sb.toString()
    }

    companion object {
        private const val SPEC_ASSET = "hi_translit.json"

        val engine: HindiTranslitEngine by lazy {
            val ctx = Settings.getCurrentContext()
            val specText = try {
                ctx.assets.open(SPEC_ASSET).use { input ->
                    BufferedReader(InputStreamReader(input)).readText()
                }
            } catch (e: Exception) {
                Log.w("HindiTranslitCombiner", "Could not load spec from assets", e)
                try {
                    HindiTranslitCombiner::class.java.classLoader
                        ?.getResourceAsStream(SPEC_ASSET)
                        ?.bufferedReader()?.readText()
                } catch (_: Exception) {
                    null
                }
            }
            if (specText.isNullOrBlank()) {
                Log.e("HindiTranslitCombiner", "hi_translit.json could not be loaded; Hindi transliteration combiner disabled")
                HindiTranslitEngine("{}")
            } else {
                HindiTranslitEngine(specText)
            }
        }
    }
}

/**
 * Hindi Transliteration conversion engine.
 *
 * Generic longest-pattern-match engine with context-sensitive rules.
 * Reuses the same algorithm as AvroPhoneticEngine.
 */
class HindiTranslitEngine(specJson: String) {
    private data class PatternMatch(
        val find: String,
        val replace: String,
        val rules: List<Rule>
    )
    private data class Rule(
        val replace: String,
        val matches: List<MatchCondition>
    )
    private data class MatchCondition(
        val type: String,
        val scope: String,
        val negative: Boolean,
        val value: String
    )

    private val patterns: List<PatternMatch> = parsePatterns(specJson)
    private val vowelChars: Set<Char>
    private val consonantChars: Set<Char>
    val caseSensitiveChars: Set<Char>

    init {
        val root = try { JSONObject(specJson) } catch (_: Exception) { JSONObject() }
        vowelChars = root.optString("vowel", "aeiou").toSet()
        consonantChars = root.optString("consonant", "bcdfghjklmnpqrstvwxyz").toSet()
        caseSensitiveChars = root.optString("casesensitive", "").toSet()
    }

    fun convert(input: String): String {
        if (input.isEmpty()) return ""
        val output = StringBuilder()
        var cur = 0
        while (cur < input.length) {
            val start = cur
            var matched = false

            for (pattern in patterns) {
                val end = cur + pattern.find.length
                if (end > input.length) continue
                if (!input.regionMatches(start, pattern.find, 0, pattern.find.length)) continue

                if (pattern.rules.isNotEmpty()) {
                    for (rule in pattern.rules) {
                        if (evaluateRule(rule, input, start, end)) {
                            output.append(rule.replace)
                            cur = end - 1
                            matched = true
                            break
                        }
                    }
                    if (matched) break
                }

                output.append(pattern.replace)
                cur = end - 1
                matched = true
                break
            }

            if (!matched) {
                output.append(input[cur])
            }
            cur++
        }
        return output.toString()
    }

    private fun evaluateRule(rule: Rule, fixed: String, start: Int, end: Int): Boolean {
        for (match in rule.matches) {
            val chk = if (match.type == "suffix") end else start - 1
            val result = when (match.scope) {
                "punctuation" -> {
                    val isPunct = (chk < 0) || (chk >= fixed.length) || !isVowelOrConsonant(fixed[chk])
                    isPunct xor match.negative
                }
                "vowel" -> {
                    val isVow = chk >= 0 && chk < fixed.length && fixed[chk].lowercaseChar() in vowelChars
                    isVow xor match.negative
                }
                "consonant" -> {
                    val isCons = chk >= 0 && chk < fixed.length && fixed[chk].lowercaseChar() in consonantChars
                    isCons xor match.negative
                }
                "exact" -> {
                    val s: Int
                    val e: Int
                    if (match.type == "suffix") {
                        s = end
                        e = end + match.value.length
                    } else {
                        s = start - match.value.length
                        e = start
                    }
                    val isExact = s >= 0 && e <= fixed.length && fixed.substring(s, e) == match.value
                    isExact xor match.negative
                }
                else -> false
            }
            if (!result) return false
        }
        return true
    }

    private fun isVowelOrConsonant(c: Char): Boolean {
        val lo = c.lowercaseChar()
        return lo in vowelChars || lo in consonantChars
    }

    companion object {
        private fun parsePatterns(json: String): List<PatternMatch> {
            val result = mutableListOf<PatternMatch>()
            try {
                val root = JSONObject(json)
                val arr = root.optJSONArray("patterns") ?: return result
                for (i in 0 until arr.length()) {
                    val obj = arr.getJSONObject(i)
                    val find = obj.getString("find")
                    val replace = obj.optString("replace", "")
                    val rulesArr = obj.optJSONArray("rules")
                    val rules = if (rulesArr != null) {
                        (0 until rulesArr.length()).map { ri ->
                            val rObj = rulesArr.getJSONObject(ri)
                            val rReplace = rObj.getString("replace")
                            val matchesArr = rObj.getJSONArray("matches")
                            val matches = (0 until matchesArr.length()).map { mi ->
                                val mObj = matchesArr.getJSONObject(mi)
                                val type = mObj.getString("type")
                                var scope = mObj.getString("scope")
                                val negative = scope.startsWith("!")
                                MatchCondition(
                                    type = type,
                                    scope = if (negative) scope.substring(1) else scope,
                                    negative = negative,
                                    value = mObj.optString("value", "")
                                )
                            }
                            Rule(replace = rReplace, matches = matches)
                        }
                    } else {
                        emptyList()
                    }
                    result.add(PatternMatch(find, replace, rules))
                }
            } catch (e: Exception) {
                Log.e("HindiTranslitEngine", "Failed to parse patterns", e)
            }
            return result
        }
    }
}