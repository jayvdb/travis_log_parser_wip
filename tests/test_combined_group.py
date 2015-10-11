from __future__ import absolute_import, unicode_literals

from travis_log_parser.blocks import Block
from travis_log_parser.block_parser import CombinedGroup

import pytest


class FakeBlock(Block):

    def __init__(self, name):
        self.name = name
        self._content = name


class Test:

    def test_string(self):
        block = CombinedGroup('git', ['submodule', 'checkout'])
        assert block.suffixes == ['submodule', 'checkout']
        assert block.numerical_identifiers is False
        assert block.expected_element_count == 2

    def test_numbers(self):
        block = CombinedGroup('git', [1, 2, 3])
        assert block.suffixes == [1, 2, 3]
        assert block.numerical_identifiers == [1, 2, 3]
        assert block.expected_element_count == 3

    def test_skipped_number(self):
        block = CombinedGroup('git', [1, 3])
        assert block.suffixes == [1, 3]
        assert block.numerical_identifiers == [1, 3]
        assert block.expected_element_count == 3

    def test_old_git(self):
        block = CombinedGroup('git', [1, 3, 4, 5])
        assert block.expected_element_count == 5

        block.append(FakeBlock('git.1'))
        assert block.is_finished() is False
        block.append(FakeBlock('cd legoktm/pywikibot-core'))
        assert block.is_finished() is False
        block.append(FakeBlock('git.3'))
        assert block.is_finished() is False
        block.append(FakeBlock('timer:22b88b71'))
        assert block.is_finished() is False
        block.append(FakeBlock('git.4'))
        assert block.is_finished() is False
        block.append(FakeBlock('git.5'))
        assert block.is_finished() is True

