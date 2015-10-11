"""A dict containing high-level blocks."""
from __future__ import absolute_import, unicode_literals

from collections import OrderedDict

from travis_log_parser.blocks import Block
from travis_log_parser.exceptions import ParseError


class BlockDict(OrderedDict):

    """OrderedDict of Block."""

    @staticmethod
    def _parse_name(name):
        """Return block name, and number as int or None."""
        assert name
        dotted = name.split('.')
        if len(dotted) == 1:
            return name, None

        assert len(dotted) == 2

        # try to parse the second half as a number
        # e.g. git.10
        try:
            num = int(dotted[1])
            assert num is not 0
        except ValueError:
            num = None

        if num:
            return dotted[0], num
        else:
            # e.g. git.checkout .submodule .etc
            return dotted[0], dotted[1]

    def _get_existing(self, name):
        full_name = name
        name, num = self._parse_name(full_name)
        block = super(BlockDict, self).get(name)
        if block is None:
            raise KeyError('{0} ({1}) not in {2}'.format(full_name, name, self.keys()))

        return block

    def __getitem__(self, item):
        if isinstance(item, slice):
            return super(BlockDict, self).__getitem__(item)
        elif isinstance(item, int):
            if item < 0:
                item = len(self) + item
            elif item > len(self):
                raise KeyError('{0} is greater than length of {1}'.format(i, len(self)))

            for i, value in enumerate(self.values()):
                if i == item:
                    return value
            raise KeyError('unexpected failure: {0}'.format(item))
        else:
            return self._get_existing(item)

    def get(self, name, start=False, cls=Block):
        full_name = name
        #print('get', full_name)
        name, num = self._parse_name(name)
        if name in self:
            if start:
                assert num and num > 1

            block = self[name]
            if num:
                if start:
                    if num < 2:
                        raise KeyError('{0} is never an existing item'.format(full_name))
                    if num - 1 != len(block):
                        print(block)
                        raise KeyError('{0} while len is {1}'.format(full_name, len(block)))
                # foo.<id> should only be used sequentially
                assert len(block) == num - 1

                if block.name != self.last.name:
                    raise ParseError('unexpected block {0} after {1}'.format(
                        block.name, self.last.name))
                assert block == self.last  # this is the same as above
            return block
        else:
            if num:
                assert num == 1
            new_block = cls(name)
            self[name] = new_block
            return new_block

    def append(self, block):
        group_name, group_id = self._parse_name(block.name)
        if group_name in self:
            raise ParseError('{0} already in {1}'.format(block, self))
        self[group_name] = block

    @property
    def last(self):
        """Get the last block."""
        return self[-1]

    def remove_last(self):
        """Remove the last block."""
        last = self.last
        del self[last.name]
