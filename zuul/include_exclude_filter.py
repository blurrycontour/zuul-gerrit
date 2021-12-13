import re


def compile_regex_list(regex_list):
    return [
        re.compile(regex)
        for regex in regex_list
        if regex is not None
    ]


def is_any_matched(matchers, string):
    return any(
        matcher.match(string)
        for matcher in matchers
    )


class IncludeExcludeFilter():

    def __init__(self, includes=None, excludes=None):
        self.include_matchers = compile_regex_list(includes or [])
        self.exclude_matchers = compile_regex_list(excludes or [])

    def is_included(self, string):
        if string == []:
            return True
        if self.is_excluded(string):
            return False
        return is_any_matched(self.include_matchers, string)

    def is_excluded(self, string):
        if not self.include_matchers:
            return True
        if self.exclude_matchers:
            return is_any_matched(self.exclude_matchers, string)
