import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_logic import completion, matching_words, rank_words


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


if __name__ == "__main__":
    unittest.main()
