"""Parse log file into blocks."""
from __future__ import absolute_import, unicode_literals

from collections import Counter

from pydsl.file.parsley import load_parsley_grammar_file
from pydsl.translator import translator_factory

from travis_log_parser.blockdict import BlockDict
from travis_log_parser.blocks import *

_repository = {
    'Worker': Worker,
    'EmptyFold': EmptyFold,
    'Fold': Fold,
    'EmptyTimer': EmptyTimer,
    'Timer': Timer,
    'AnsiColour': AnsiColour,
    'Line': Line,
    'BlankLine': BlankLine,
    'CommandLine': CommandLine,
    'CommandCompleted': CommandCompleted,
    'Done': Done,
    'TravisYmlEnvironmentVariables': TravisYmlEnvironmentVariables,
    'RepositoryEnvironmentVariables': RepositoryEnvironmentVariables,
    'PythonNoRequirements': PythonNoRequirements,
    'ContainerNotice': ContainerNotice,
}

_parsley_grammar = None


def _get_parsley_grammar():
    global _parsley_grammar
    if not _parsley_grammar:
        _parsley_grammar = load_parsley_grammar_file(
            'travis_log_parser/blocks.parsley', repository=_repository)
    return _parsley_grammar


class CombinedGroup(Block):

    def __init__(self, name, suffixes):
        self.name = name
        self.suffixes = suffixes
        super(CombinedGroup, self).__init__()
        self._content = []

        self.numerical_identifiers = list(
            identifier for identifier in suffixes
            if isinstance(identifier, int)) or False
        if self.numerical_identifiers:
            assert len(self.numerical_identifiers) == len(suffixes)

        self._is_finished = False

    @property
    def expected_element_count(self):
        if self.numerical_identifiers:
            return max(self.numerical_identifiers)
        else:
            return len(self.suffixes)

    def is_finished(self):
        #print('isfinished', len(self.elements), self.expected_element_count)
        return self._is_finished

    def append(self, item):
        assert not self.is_finished()
        assert isinstance(item, Block)
        if not isinstance(item, Fold):
            print('inserting unusual element into combined at {0}:{1}: {2}'.format(self.name, len(self._content), item))
        self._content.append(item)
        if self.numerical_identifiers is False:
            # TODO: check each expected item has been added
            self._is_finished = len(self._content) == self.expected_element_count
        else:
            try:
                (group_name, suffix) = BlockDict._parse_name(item.name)
                if isinstance(suffix, int):
                    if suffix == max(self.numerical_identifiers):
                        self._is_finished = True
            except:
                pass

    def __repr__(self):
        return '<{0}: {1}>'.format(self.name, self._content)


class ScriptBlock(Block):

    def __init__(self):
        self.name = 'script'
        self._content = []

    def append(self, item):
        self._content.append(item)


class BlockParser(object):

    _parsley_grammar = None

    def __init__(self):
        """
        Constructor.

        Loads the grammar.
        """
        self._parsley_grammar = _get_parsley_grammar()
        self._solver = translator_factory(self._parsley_grammar)

    def _parse(self, s):
        """Return raw parse tree for s."""
        return self._solver(s)

    def _regroup(self, tree):
        """Regroup tree into a dictionary of well defined blocks."""
        blocks = BlockDict()
        parsed_block_names = list(
            blocks._parse_name(block.name) for block in tree
            if not isinstance(block, str))

        print('parsed_block_names', parsed_block_names)

        group_names = Counter(
            group_name for group_name, suffix in parsed_block_names)
        print('group names', group_names)
        repeated_names = [name for name, cnt in group_names.most_common() if cnt > 1]
        print('repeats', repeated_names)
        suffixes = {}
        for group_name in repeated_names:
            suffixes[group_name] = [
                suffix for identifier, suffix in parsed_block_names
                if identifier == group_name]
        print('suffixes', suffixes)

        for item in tree:
            if isinstance(item, AnsiColour):
                continue
            elif not isinstance(item, Block):
                assert isinstance(item, str)
                print('string found: {0}'.format(item))
                continue

            full_name = item.name
            group_name, suffix = blocks._parse_name(full_name)
            print('found {0} . {1}'.format(group_name, suffix))

            if blocks and isinstance(blocks.last, CombinedGroup):
                last_block = blocks.last
                print('finished?', last_block.is_finished())
                if not last_block.is_finished():
                    last_block.append(item)
                    continue

            if group_name in repeated_names:
                if group_name not in blocks:
                    block = CombinedGroup(group_name, suffixes[group_name])
                    blocks.append(block)
                else:
                    block = blocks[group_name]

                print('add {0} to {1}'.format(full_name, group_name))
                block.append(item)
            else:
                print('adding block {0}'.format(full_name))
                blocks.append(item)

        # Find 'script'
        if 'script' not in blocks and '_done' in blocks:
            script_block = ScriptBlock()

            if 'install' in blocks:
                start_after_name = 'install'

            end_before_name = '_done'

            found = False

            for index, item_name in enumerate(blocks.keys()):
                if item_name == start_after_name:
                    found = True
                elif item_name == end_before_name:
                    break
                elif found is True:
                    script_block.append(blocks[item_name])
                    del blocks[item_name]

            blocks.append(script_block)
            blocks.move_to_end(end_before_name)

        # Wrap activation
        for index, (name, block) in enumerate(blocks.items()):
            if name == 'script':
                break

            if isinstance(block, Timer):
                activate_block = Activate()
                if block._content and isinstance(block._content[0], CommandLine):
                    executed = block._content[0].executed
                    if re.match('source.*\/activate', executed):
                        activate_block._contents = block
                        blocks[index] = activate_block
                        break

        return blocks

    def split(self, s):
        """Return s split into blocks."""
        return self._regroup(self._parse(s))
