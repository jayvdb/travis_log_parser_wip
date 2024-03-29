from __future__ import absolute_import, unicode_literals

import os
import regex
import sys

from collections import OrderedDict

from travispy import ParseError, TravisLogCorrupt

from travispy._log_functions import *
from travispy._log_items import *


class Block(object):

    """Travis log block."""

    def __init__(self, name):
        """Constructor."""
        self.name = name
        self.elements = []
        self._finished = None

    @property
    def commands(self):
        return self.elements

    @property
    def last_item(self):
        if not self.elements:
            return None
        return self.elements[-1]

    def append(self, item):
        if isinstance(item, BlankLine):
            self.elements.append(item)
        elif not item:
            print('{0}: inserting empty item: {1}'.format(self, item))
            self.elements.append(item)
        else:
            self.elements.append(item)

    def allow_empty(self):
        return False

    def append_line(self, line):
        if self.elements:
            last_command = self.elements[-1]
            #print('append to block', last_command, type(last_command), line, last_command.finished())
            if isinstance(last_command, TimedCommand):
                raise ParseError('not expecting {0}.append_line({1})'.format(self, line))

        nocolor_line = remove_ansi_color(line)
        if nocolor_line.startswith('$ '):
            new_command = UntimedCommand()
            new_command.append_line(line)
        elif self.elements:
            last_command = self.elements[-1]
            last_command.append_line(line)
        else:
            new_item = Note()
            new_item.append_line(line)
            # TODO add the Note?

    def finished(self):
        #print('{0}.finished() == {1}'.format(self.__class__.__name__, self._finished))
        return self._finished

    def __hash__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other

    def __len__(self):
        return len(self.elements)

    def __repr__(self):
        if not self.elements:
            return '<empty block {0}>'.format(self.name)

        elements = self.elements
        if len(elements) > 3:
            elements = elements[0:3] + ['...']

        return '<block {0} ({1} elements): {2}>'.format(
            self.name, len(self.elements), elements)


class OneNoteBlock(Block):

    def append_line(self, line):
        if not self.elements:
            note = Note()
            self.append(note)
        else:
            note = self.elements[-1]
            assert isinstance(note, Note)
        note.append_line(line)


class CommandBlock(Block):

    def append_line(self, line):
        #print('CommandBlock.append_line ', line)
        nocolor_line = remove_ansi_color(line)

        assert self.commands

        last_command = self.commands[-1]
        if isinstance(last_command, BlankLine):
            last_command = self.commands[-2]

        if not isinstance(last_command, Command):
            if last_command and last_command.identifier in ['_unsolved_exit_code-1', '_unsolved_exit_code-2']:
                pass
            else:
                raise ParseError('last command is {0}: {1} when inserting: {2}'.format(type(last_command), last_command, line))

        if len(last_command.lines):

            # clean the last command line, and remove the '$ '
            exit_code_pattern = 'The command "{0}" exited with '.format(remove_ansi_color(last_command.lines[0])[2:])
            if nocolor_line.startswith(exit_code_pattern):
                exit_code = nocolor_line[len(exit_code_pattern):-1]
                last_command.exit_code = int(exit_code)
                return
            elif nocolor_line and exit_code_pattern.startswith(nocolor_line):
                # TODO: The exit_code_pattern needs to be a multi-line match
                # e.g. happy5214/pywikibot-core/6.10
                current_command = Note('_unsolved_exit_code-1')
                self.commands.append(current_command)
                return

            exit_code_pattern = 'The command "{0}" failed and exited with '.format(remove_ansi_color(last_command.lines[0])[2:])
            if nocolor_line.startswith(exit_code_pattern):
                exit_code = nocolor_line[len(exit_code_pattern):].split(' during ')[0]
                last_command.exit_code = int(exit_code)
                return

        last_command.append_line(line)


class SingleCommandBlock(Block):

    def append_line(self, line):
        assert len(self.elements) == 1
        if len(self.elements[0].lines) != 0:
            raise ParseError('cant insert line into {0}: {1}'.format(self, line))
        assert len(self.elements[0].lines) == 0
        self.elements[0].append_line(line)

    def finished(self):
        return len(self.elements[0].lines) == 1


class AutoCommandBlock(CommandBlock):

    _single_line_response = False

    def append_line(self, line):
        if self.finished():
            raise ParseError('Unexpectedly adding {0} to {1}'.format(line, self))
        #print('adding {0} to {1}'.format(line, self))
        nocolor_line = remove_ansi_color(line)
        if nocolor_line.startswith('$ '):
            if self.elements and self._single_line_response:
                last_command = self.elements[-1]
                assert len(last_command.lines) == 2
            command = UntimedCommand()
            command.append_line(line)
            self.elements.append(command)
        else:
            if not len(self):
                raise ParseError('Unexpected version line: {0}'.format(line))
            last_command = self.elements[-1]
            if self._single_line_response:
                assert len(last_command.lines) == 1
            last_command.append_line(line)

    def __repr__(self):
        return '<auto {0}({1}) commands: {2}>'.format(self.name, self.__class__.__name__, self.elements)


class AutoVersionCommandBlock(AutoCommandBlock):

    _single_line_response = False  # php --version emits multiple lines

    def append_line(self, line):
        nocolor_line = remove_ansi_color(line)
        if nocolor_line.startswith('$ '):
            # smalruby/smalruby/193.1 has export BUNDLE_GEMFILE=$PWD/Gemfile
            if not nocolor_line.startswith('$ export '):
                assert nocolor_line.endswith('--version')
        super(AutoVersionCommandBlock, self).append_line(line)

    def append(self, item):
        raise RuntimeError('not allowed to add {0} to {1}'.format(item, self))


class MixedCommandBlock(AutoCommandBlock):

    def append_line(self, line):
        if self.elements:
            if self.elements[-1].finished():
                super(MixedCommandBlock, self).append_line(line)
            else:
                self.elements[-1].append_line(line)
        else:
            super(MixedCommandBlock, self).append_line(line)


class ScriptBlock(CommandBlock):

    pass


class AutoScriptBlock(AutoCommandBlock):

    pass


class OldGitBlock(MixedCommandBlock):

    """Special handler for old 'git.*' blocks."""

    def __len__(self):
        if len(self.elements) == 4 and not self.elements[-1].lines and self.elements[-1].finished():
            # remove the empty '4th' item, so it doesnt conflict with 'git.4'
            self.elements = self.elements[:-1]

        return super(OldGitBlock, self).__len__()

    @property
    def last_item(self):
        if len(self.elements) == 4 and not self.elements[-1].lines and self.elements[-1].finished():
            # remove the empty '4th' item, so it doesnt conflict with 'git.4'
            self.elements = self.elements[:-1]

        return super(OldGitBlock, self).last_item

    def allow_empty(self):
        if len(self.elements) == 3 and '$ git checkout -qf ' in self.elements[2].lines[0]:
            return True
        else:
            return False

    def finished(self):
        return False


class AutoGitBlock(MixedCommandBlock):

    def append_line(self, line):
        #if self.elements:
        #    print('appending', line, len(self.elements), self.elements[0].finished())
        if self.elements and len(self.elements) == 1 and '$ cd ' in line:
            command = UntimedCommand()
            command.append_line(line)
            command._finished = True
            self.append(command)
            print('added an untimed command')
            return
        prev = self._finished
        self._finished = False
        super(AutoGitBlock, self).append_line(line)
        self._finished = prev

    def finished(self):
        if self._finished is not None:
            return self._finished
        return len(self.elements) > 3 and self.elements[-1].finished()


class OSXRubyVersionBlock(AutoVersionCommandBlock):

    def allow_empty(self):
        #print('allow empty?')
        return True

    def append_line(self, line):
        #print('appending' , line, self)
        super(OSXRubyVersionBlock, self).append_line(line)

    def finished(self):
        if self.elements and self.elements[-1].lines and self.elements[-1].executed == 'bundle --version' and len(self.elements[-1].lines) == 3:
            #print('finished: True', self.elements)
            return True
        else:
            #if self.elements and self.elements[-1].lines:
            #    #print('finished: False', self.elements[-1].lines)
            return False

    def append(self, block):
        self.elements.append(block)


class PHPActivateBlock(CommandBlock):

    def allow_empty(self):
        return True

    def finished(self):
        if self.elements and self.elements[0].lines and self.elements[0].executed != 'phpenv global 7 2>/dev/null':
            return True

        if self.elements and self.elements[0].lines and self.elements[0].executed == 'phpenv global 7 2>/dev/null':
            if len(self.elements) > 3 and self.elements[-1].lines and self.elements[-1].executed == 'phpenv global 7':
                #print('finished', True)
                return True

        return False


class AutoNameBlock(Block):

    def __init__(self):
        name = ''.join(
            '_' + c if c.isupper() else c
            for c in self.__class__.__name__).lower()
        super(AutoNameBlock, self).__init__(name)


class RegexBlock(AutoNameBlock):

    _is_note = False
    _blank_line_end = False
    _single_line = False

    def is_note(self):
        return self._is_note

    def append_line(self, line):
        #print('appending', self, line)
        if self.finished():
            raise ParseError('block {0} is finished'.format(self))

        if remove_ansi_color(line) == '':
            self.elements.append(BlankLine())
        else:
            self.elements[0].append_line(line)

    def finished(self):
        if not self.elements:
            return False
        if self._single_line:
            #print('single line', self)
            return len(self.elements[-1].lines) == 1
        if self._blank_line_end:
            return isinstance(self.elements[-1], BlankLine)
        else:
            return None


class ExactMatchBlock(RegexBlock):

    _except = []

    def is_note(self):
        return True

    def append_line(self, line):
        assert not self.finished()
        expect_line = self._expect[len(self.elements[-1].lines)]
        assert remove_ansi_color(line) == expect_line
        self.elements[-1].lines.append(line)

    def finished(self):
        return len(self.elements[-1].lines) == len(self._expect)


class StalledJobTerminated(ExactMatchBlock):

    _match = '^No output has been received in the last 10 minutes'
    _expect = (
        'No output has been received in the last 10 minutes, this potentially indicates a stalled build or something wrong with the build itself.',
        '',
        'The build has been terminated',
    )


class LogExceededJobTerminated(ExactMatchBlock):

    _match = '^The log length has exceeded the limit of 4 Megabytes'
    _expect = (
        'The log length has exceeded the limit of 4 Megabytes (this usually means that test suite is raising the same exception over and over).',
        '',
        'The build has been terminated.',
    )


class NoTravisYmlWarning(RegexBlock):

    _match = '^WARNING: We were unable to find a .travis.yml file.'
    _is_note = True
    _blank_line_end = True


class Worker(RegexBlock):

    _match = '^Using worker'

    _is_note = True
    _blank_line_end = True


class StandardConfigurationWarning(RegexBlock):

    _match = '^Could not find .travis.yml, using standard configuration.'
    _is_note = True


class PythonNoRequirements(RegexBlock):

    _match = '^Could not locate requirements.txt'
    _is_note = True


#class SystemInformation(RegexBlock):
#
#    _match = '^Build system information'
#
#    _is_note = True
#    _blank_line_end = True


class ContainerNotice(RegexBlock):

    _match = ('^This job is running on container-based '
              'infrastructure')

    _is_note = True
    _blank_line_end = None
    # /home/jayvdb/tmp/travis-bot/jayvdb/citeproc-test/13.1-failed.txt doesnt include a blank line


class EnvironmentSettings(RegexBlock):

    _is_note = True  # captures the first line as a note
    _blank_line_end = True

    def append_line(self, line):
        if remove_ansi_color(line) == '':
            self.elements.append(BlankLine())
            return

        envvar = UntimedCommand()
        envvar.append_line(line)
        self.elements.append(envvar)
        #print('appended', envvar)


class RepositoryEnvironmentVariables(EnvironmentSettings):

    _match = '^Setting environment variables from repository settings'


class TravisYmlEnvironmentVariables(EnvironmentSettings):

    _match = '^Setting environment variables from \.travis\.yml'


class AptBlock(CommandBlock):

    def append_line(self, line):
        if not self.elements:
            assert 'Installing APT Packages' in line
            header = Note()
            header.lines.append(line)
            self.elements.append(header)
        # TODO: this is an ugly workaround for CommandBlock asserting that the previous item is a Command
        elif len(self.elements) == 1:
            header = TimedCommand('ugly')
            header.lines.append(line)
            self.elements.append(header)
        else:
            self.elements[-1].append_line(line)


class BlankLineBlock(Block):

    def append_line(self, line):
        if remove_ansi_color(line) != '':
            raise ParseError('BlankLineBlock not expecting {0}'.format(line))
        self.elements.append(BlankLine())

    def finished(self):
        return len(self.elements) == 1


class JobCancelled(RegexBlock):

    # two leading blank lines?

    _match = '^Done: Job Cancelled'
    _is_note = True
    _single_line = True


class JobStopped(RegexBlock):

    _match = '^Your build has been stopped.'
    _is_note = True


class Done(RegexBlock):

    _match = '^Done. Your build exited with '
    _is_note = False

    def __init__(self, *args, **kwargs):
        super(Done, self).__init__(*args, **kwargs)
        self.exit_code = None

    def append_line(self, line):
        # remove trailing '.'
        exit_code = line[len('Done. Your build exited with '):-1]
        self.exit_code = int(exit_code)
        note = Note()
        note.append_line(line)
        self.append(note)

    def finished(self):
        return self.exit_code is not None


BLOCK_CLASSES = [
    NoTravisYmlWarning,
    Worker,
    StandardConfigurationWarning,
    PythonNoRequirements,
    ContainerNotice,
    RepositoryEnvironmentVariables,
    TravisYmlEnvironmentVariables,
    JobCancelled,
    JobStopped,
    StalledJobTerminated,
    LogExceededJobTerminated,
    Done,
]


