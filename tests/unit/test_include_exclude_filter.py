import unittest
from unittest.mock import Mock

from zuul.include_exclude_filter import IncludeExcludeFilter


def filterable_mock(string="something"):
    return Mock(__str__=Mock(side_effect=lambda: string))


class IncludeExcludeFilterTest(unittest.TestCase):

    def test_givenNothing_includesNothing(self):
        include_exclude_filter = IncludeExcludeFilter()
        self.assertFalse(include_exclude_filter.is_included(filterable_mock()))

    def test_givenEmptyIncludes_includesNothing(self):
        include_exclude_filter = IncludeExcludeFilter(includes=[])
        self.assertFalse(include_exclude_filter.is_included(filterable_mock()))

    def test_givenNoneIncludes_includesNothing(self):
        include_exclude_filter = IncludeExcludeFilter(includes=None)
        self.assertFalse(include_exclude_filter.is_included(filterable_mock()))

    def test_noneIsNeverIncluded(self):
        include_exclude_filter = IncludeExcludeFilter()
        self.assertFalse(include_exclude_filter.is_included(None))

    def test_emptyListIsAlwaysIncluded(self):
        include_exclude_filter = IncludeExcludeFilter()
        self.assertTrue(include_exclude_filter.is_included([]))

    def test_givenSomething_includesIdenticalThing(self):
        filterable = filterable_mock()
        include_exclude_filter = IncludeExcludeFilter(includes=[filterable])
        self.assertTrue(include_exclude_filter.is_included(filterable))

    def test_givenSomething_includesEqualThing(self):
        something = filterable_mock("something")
        equalThing = filterable_mock("something")
        include_exclude_filter = IncludeExcludeFilter(includes=[something])
        self.assertTrue(include_exclude_filter.is_included(equalThing))

    def test_givenSomething_excludesSomethingDifferent(self):
        something = filterable_mock("something")
        somethingElse = filterable_mock("some other thing")
        include_exclude_filter = IncludeExcludeFilter(includes=[something])
        self.assertFalse(include_exclude_filter.is_included(somethingElse))

    def test_givenSomethingAndOther_includesSameThing(self):
        secondThing = filterable_mock("secondThing")
        givenThings = [filterable_mock(), filterable_mock("secondThing")]
        include_exclude_filter = IncludeExcludeFilter(includes=givenThings)
        self.assertTrue(include_exclude_filter.is_included(secondThing))

    def assertIncluded(self, something, including, excluding=None):
        include_exclude_filter = IncludeExcludeFilter(
            includes=including,
            excludes=excluding
        )
        self.assertTrue(include_exclude_filter.is_included(something))

    def assertExcluded(self, something, including, excluding=None):
        include_exclude_filter = IncludeExcludeFilter(
            includes=including,
            excludes=excluding
        )
        self.assertFalse(include_exclude_filter.is_included(something))

    def test_givenNoneListEntries_ignoresAllNoneEntries(self):
        something = filterable_mock()
        self.assertExcluded(something, including=[None])
        self.assertExcluded(something, including=[None, None])
        self.assertIncluded(something, including=[None, something, None])
        comparesToNone = filterable_mock("None")
        self.assertIncluded(comparesToNone, including=[None, comparesToNone])
        self.assertIncluded(comparesToNone, including=[None, comparesToNone,
                                                       None])
        self.assertExcluded(comparesToNone, including=[None])

    def test_givenNoneExcludes_includesAllIncludes(self):
        something = filterable_mock()
        include_exclude_filter = IncludeExcludeFilter(
            includes=[something],
            excludes=None
        )
        self.assertTrue(include_exclude_filter.is_included(something))

    def test_givenEmptyExcludes_includesAllIncludes(self):
        something = filterable_mock()
        include_exclude_filter = IncludeExcludeFilter(
            includes=[something],
            excludes=[]
        )
        self.assertTrue(include_exclude_filter.is_included(something))

    def test_givenSomeIncludeRegex_matchingThingsAreIncluded(self):
        something = filterable_mock("/path1/")
        include_exclude_filter = IncludeExcludeFilter(
            includes=["/path1.*"],
            excludes=[]
        )
        self.assertTrue(include_exclude_filter.is_included(something))

    def test_givenSomeExclude_excludesThatExclude(self):
        exclude = "something excluded"
        somethingExcluded = filterable_mock(exclude)
        something = filterable_mock("something included")
        self.assertExcluded(somethingExcluded,
                            including=[somethingExcluded],
                            excluding=[exclude])
        self.assertExcluded(somethingExcluded,
                            including=[something, somethingExcluded],
                            excluding=[exclude])
        self.assertIncluded(something,
                            including=[something, somethingExcluded],
                            excluding=[exclude])

    def test_givenSomeExcludes_excludesThoseExcludes(self):
        exclude1 = "something excluded"
        exclude2 = "something more excluded"
        somethingExcluded = filterable_mock(exclude1)
        somethingMoreExcluded = filterable_mock(exclude2)
        something = filterable_mock("something included")
        self.assertExcluded(somethingExcluded,
                            including=[something, somethingExcluded,
                                       somethingMoreExcluded],
                            excluding=[exclude1, exclude2])
        self.assertExcluded(somethingMoreExcluded,
                            including=[something, somethingExcluded,
                                       somethingMoreExcluded],
                            excluding=[exclude1, exclude2])
        self.assertIncluded(something,
                            including=[something, somethingExcluded,
                                       somethingMoreExcluded],
                            excluding=[exclude1, exclude2])

    def test_givenSomeExcludeRegex_excludesTheCorrectThings(self):
        excludeRegex = ".*something.*"
        excludeRegex2 = ".*(ex|in).*cluded.*"
        something = filterable_mock("something")
        somethingElse = filterable_mock("somethingElse")
        andSomethingDifferent = filterable_mock("and something different")
        somethingIncluded = filterable_mock("someth. included")
        self.assertExcluded(something,
                            including=[something, somethingElse,
                                       andSomethingDifferent],
                            excluding=[excludeRegex])
        self.assertExcluded(somethingElse,
                            including=[something, somethingElse,
                                       andSomethingDifferent],
                            excluding=[excludeRegex])
        self.assertExcluded(andSomethingDifferent,
                            including=[something, somethingElse,
                                       andSomethingDifferent],
                            excluding=[excludeRegex])
        self.assertIncluded(somethingIncluded,
                            including=[something, somethingIncluded,
                                       somethingElse],
                            excluding=[excludeRegex])
        self.assertExcluded(somethingIncluded,
                            including=[something, somethingIncluded,
                                       somethingElse],
                            excluding=[excludeRegex, excludeRegex2])
        self.assertExcluded(filterable_mock("/path1/tests/path3"),
                            including=["/path1.*"],
                            excluding=[".*/tests/.*"])
        self.assertIncluded(filterable_mock("/path1/src/path3"),
                            including=["/path1.*"],
                            excluding=[".*/tests/.*"])
