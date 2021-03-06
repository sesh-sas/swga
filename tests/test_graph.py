import pytest
import swga.graph
from swga.database import Primer

class TestGraph:

    @pytest.fixture(scope="function")
    def primers(self, initdb):
        primers = [
            # reference primer
            Primer.create(_id=0, seq="ATGCTC"),
            # rev. complement has 4 bases overlapping
            Primer.create(_id=1, seq="CAGCAT"),
            # rev. complement has 3 bases overlapping
            Primer.create(_id=2, seq="GAGGTA"),
            Primer.create(_id=3, seq="ATCGAG"),
            # rev. complement has one base overlapping
            Primer.create(_id=4, seq="TTCCAC"),
            # substring of reference primer
            Primer.create(_id=5, seq="ATGC")
        ]
        return primers

    def test_heterodimer_check(self, primers):
        '''An edge must not exist between heterodimers.'''
        ref_primer = primers[0]
        heterodimers = primers[1:4]
        for heterodimer in heterodimers:
            edges = swga.graph.test_pairs([ref_primer, heterodimer], 2)
            assert edges == []

    def test_valid_primer_pair(self, primers):
        '''An edge should exist between valid primer pairs.'''
        ref_primer = primers[0]
        valid_primer = primers[4]
        edges = swga.graph.test_pairs([ref_primer, valid_primer], 2)
        assert edges == [[0, 4]]

    def test_subsequence_check(self, primers):
        '''
        An edge should not exist between a primer whose sequence is a
        subsequence of the other primer.
        '''
        ref_primer = primers[0]
        subseq_primer = primers[5]
        edges = swga.graph.test_pairs([ref_primer, subseq_primer], 2)
        assert edges == []

        
