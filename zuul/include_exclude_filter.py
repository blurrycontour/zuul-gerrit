import re

def compile_regex_list(regex_list):
    return [
        re.compile(regex.__str__())
        for regex in regex_list
        if regex is not None
    ]

def is_any_matched(matchers, filterable):
    return any(
        matcher.match(filterable.__str__())
        for matcher in matchers
    )
class IncludeExcludeFilter():

    def __init__(self, includes = None, excludes = None):
        self.include_matchers = compile_regex_list(includes or [])
        self.exclude_matchers = compile_regex_list(excludes or [])

    def is_included(self, filterable):
        if filterable == []:
            return True
        if self.is_excluded(filterable):
            return False
        return is_any_matched(self.include_matchers, filterable)

    def is_excluded(self, filterable):
        if not self.include_matchers:
            return True
        if self.exclude_matchers:
            return is_any_matched(self.exclude_matchers, filterable)