
class ParseError(Exception):

    """Base class for log parsing errors."""

    pass


class TravisLogCorrupt(ParseError):

    pass
