from __future__ import absolute_import, unicode_literals

from travis_log_parser.block_parser import BlockParser
from travis_log_parser.blocks import (
    TravisYmlEnvironmentVariables,
    CommandLine,
)

import pytest


class Test:

    def test_envvars(self):
        text = (
            '\x1b[33;1mSetting environment variables from .travis.yml[0m\n'
            '$ export LANGUAGE=en\n'
            '$ export FAMILY=wikipedia\n'
            '\n'
        )

        parser = BlockParser()
        tree = parser._parse(text)
        assert isinstance(tree[0], TravisYmlEnvironmentVariables)
        assert isinstance(tree[1], str)
        assert len(tree) == 2

        envvars = tree[0]
        assert len(envvars._content) == 2
        assert isinstance(envvars._content[0], CommandLine)
        assert envvars._content[0].executed == 'export LANGUAGE=en'
        assert isinstance(envvars._content[1], CommandLine)
        assert envvars._content[1].executed == 'export FAMILY=wikipedia'

