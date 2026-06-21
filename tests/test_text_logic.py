import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_logic import completion, looks_like_word, matching_words, rank_words


WORDS = ["og", "jeg", "det", "deg", "du", "er", "skrive"]


class MatchingWordsTests(unittest.TestCase):
    def test_no_partial_returns_first_words(self):
        self.assertEqual(matching_words(WORDS, "", limit=3), ["og", "jeg", "det"])

    def test_prefix_filters_matches(self):
        self.assertEqual(matching_words(WORDS, "de"), ["det", "deg"])

    def test_no_match_returns_empty(self):
        self.assertEqual(matching_words(WORDS, "xyz"), [])

    def test_case_insensitive(self):
        self.assertEqual(matching_words(WORDS, "DE"), ["det", "deg"])

    def test_respects_limit(self):
        self.assertEqual(len(matching_words(WORDS, "", limit=2)), 2)


class RankWordsTests(unittest.TestCase):
    def test_no_frequencies_keeps_base_order(self):
        self.assertEqual(rank_words(WORDS, {}, "", limit=3), ["og", "jeg", "det"])

    def test_frequency_boosts_word_to_front(self):
        self.assertEqual(rank_words(WORDS, {"du": 5}, "")[0], "du")

    def test_prefix_filter_with_ranking(self):
        result = rank_words(WORDS, {"deg": 9}, "de")
        self.assertEqual(result, ["deg", "det"])

    def test_learned_word_not_in_base_appears(self):
        result = rank_words(WORDS, {"hei": 3}, "he")
        self.assertIn("hei", result)

    def test_no_match_returns_empty(self):
        self.assertEqual(rank_words(WORDS, {}, "zzz"), [])


class CompletionTests(unittest.TestCase):
    def test_returns_suffix_for_prefix_match(self):
        self.assertEqual(completion("skrive", "skr"), "ive")

    def test_returns_whole_word_when_not_prefix(self):
        self.assertEqual(completion("hello", "xyz"), "hello")

    def test_empty_current_returns_whole_word(self):
        self.assertEqual(completion("hello", ""), "hello")

    def test_case_insensitive_suffix(self):
        self.assertEqual(completion("Hello", "he"), "llo")


class LooksLikeWordTests(unittest.TestCase):
    def test_real_words_pass(self):
        for w in ["this", "hello", "yes", "skrive", "what", "was", "but"]:
            self.assertTrue(looks_like_word(w), f"{w!r} should pass")

    def test_keyboard_mash_rejected(self):
        for w in ["tttyyyi", "bbnnmmmuyutt", "vvgggfffddd", "ddrftigggggg",
                  "uyfhfeeerrrrrrrrry", "aaaaah", "bbbbby"]:
            self.assertFalse(looks_like_word(w), f"{w!r} should be rejected")

    def test_short_words_rejected(self):
        self.assertFalse(looks_like_word("a"))
        self.assertFalse(looks_like_word(""))

    def test_non_alpha_rejected(self):
        self.assertFalse(looks_like_word("hello123"))
        self.assertFalse(looks_like_word("hi!"))

    def test_consonant_only_rejected(self):
        # "hgg", "bbnn" have no vowels -> mash
        self.assertFalse(looks_like_word("hgg"))
        self.assertFalse(looks_like_word("bbnn"))

    def test_long_run_rejected(self):
        # 4+ identical letters in a row
        self.assertFalse(looks_like_word("sooooool"))
        self.assertFalse(looks_like_word("wheeeeee"))

    def test_three_repeat_ok(self):
        # 3 in a row is allowed (e.g. "booook" is odd but not clearly mash)
        self.assertTrue(looks_like_word("book"))
        self.assertTrue(looks_like_word("bee"))


class RankWordsGibberishTests(unittest.TestCase):
    def test_gibberish_learned_words_excluded(self):
        # "tttyyyi" is in frequencies but should NOT appear in suggestions
        result = rank_words(WORDS, {"tttyyyi": 10, "du": 5}, "")
        self.assertNotIn("tttyyyi", result)
        self.assertIn("du", result)

    def test_real_learned_words_included(self):
        result = rank_words(WORDS, {"hei": 3}, "he")
        self.assertIn("hei", result)


if __name__ == "__main__":
    unittest.main()
