"""Check report boundaries and exact password comparison."""

import unittest

from spm.domain.credentials import Entry
from spm.domain.review import VaultReview, review_credentials


class VaultReviewTests(unittest.TestCase):
    def test_length_counts_characters_and_reuse_is_exact(self):
        entries = (
            Entry("Primera", "abcdefghijklmnñ"),
            Entry("Segunda", "abcdefghijklmnñ"),
            Entry("Mayúscula", "Abcdefghijklmnñ"),
            Entry("Espacio", "abcdefghijklmnñ "),
            Entry("Breve", "áéíóúüñÁÉÍÓÚÜÑ"),
            Entry("También breve", "áéíóúüñÁÉÍÓÚÜÑ"),
        )
        expected = VaultReview(
            total=6,
            short=("Breve", "También breve"),
            reused=(("Primera", "Segunda"), ("Breve", "También breve")),
        )
        self.assertEqual(review_credentials(iter(entries)), expected)
