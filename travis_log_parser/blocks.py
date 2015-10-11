import sys

if sys.version_info[0] > 2:
    basestring = (str, )


class Block(object):

    def __init__(self, *args, **kwargs):
        if args and kwargs:
            self._content = args, kwargs
        elif args:
            if len(args) == 1:
                self._content = args[0]
            else:
                self._content = args
        elif kwargs:
            self._content = kwargs
        else:
            self._content = None

    def _get_content_repr(self):
        if isinstance(self._content, basestring) and len(self._content) > 50:
            return self._content[:50] + '...'
        elif isinstance(self._content, tuple) and len(self._content) > 50:
            return self._content[:50] + ('...', )
        elif isinstance(self._content, list) and len(self._content) > 50:
            return self._content[:50] + ['...']
        else:
            return self._content

    def __repr__(self):
        if self.name == self._content:
            return '{0}({1})'.format(self.__class__.__name__, self.name)

        content = self._get_content_repr()

        return '{0}({1}, {2})'.format(
            self.__class__.__name__, self.name, content)


class AutoNameBlock(Block):

    def __init__(self, *args, **kwargs):
        self.name = ''.join(
            '_' + c if c.isupper() else c
            for c in self.__class__.__name__).lower()
        super(AutoNameBlock, self).__init__(*args, **kwargs)

    def __repr__(self):
        content = self._get_content_repr()

        return '{0}({1})'.format(
            self.__class__.__name__, content)


class AutoNameOnlyBlock(AutoNameBlock):

    def __repr__(self):
        return '{0}()'.format(self.__class__.__name__)


class Worker(AutoNameBlock):

    def __init__(self, worker):
        self.worker = worker
        super(Worker, self).__init__(worker)

    def __str__(self):
        return self.worker


class Fold(Block):

    def __init__(self, identifier, content):
        self.name = identifier
        super(Fold, self).__init__(content)


class EmptyFold(Fold):

    def __init__(self, identifier):
        super(EmptyFold, self).__init__(identifier, content=None)


class Timer(Block):

    def __init__(self, identifier, parameters, content):
        assert ':' not in identifier
        self.name = identifier
        self.parameters = parameters
        super(Timer, self).__init__(content)

        parameters = dict(parameter.split('=')
                          for parameter in parameters.split(','))
        for key, value in parameters.items():
            setattr(self, key, int(value))


class EmptyTimer(Timer):

    def __init__(self, identifier, parameters):
        super(EmptyTimer, self).__init__(identifier, parameters, content=None)


class AnsiColour(AutoNameBlock):

    def __init__(self, text):
        self.color_string = text
        assert text[0:2] == '\x1b['
        text = text[2:]
        super(AnsiColour, self).__init__(text)


class Line(Block):

    def __init__(self, line):
        self.name = line
        super(Line, self).__init__(line)
        assert line != '\n'


class BlankLine(AutoNameOnlyBlock, Line):

    def __init__(self):
        # skip Line
        super(Line, self).__init__('\n')


class CommandLine(Line):

    def __init__(self, line):
        self.executed = line
        super(CommandLine, self).__init__(line)


class CommandCompleted(AutoNameBlock):

    def __init__(self, command, exit_code):
        self.executed = command
        self.exit_code = int(exit_code)
        super(CommandCompleted, self).__init__(command, exit_code)


class Done(AutoNameBlock):

    def __init__(self, exit_code):
        self.exit_code = int(exit_code)
        super(Done, self).__init__(exit_code)


class Activate(AutoNameBlock):

    pass
   

class EnvironmentSettings(AutoNameBlock):

    pass


class TravisYmlEnvironmentVariables(EnvironmentSettings):

    pass


class RepositoryEnvironmentVariables(EnvironmentSettings):

    pass


class PythonNoRequirements(AutoNameBlock):

    pass


class ContainerNotice(AutoNameBlock):

    pass
