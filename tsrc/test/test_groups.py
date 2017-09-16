import tsrc.groups

import pytest


def test_happy_grouping():
    group_list = tsrc.groups.GroupList(elements={"a", "b", "c"})
    group_list.add("default", {"a", "b"})
    group_list.add("other", {"c"}, includes={"default"})
    actual = group_list.get_elements(groups={"other"})
    assert actual == {"a", "b", "c"}


def test_default_is_all():
    group_list = tsrc.groups.GroupList(elements={"a", "b", "c"})
    assert group_list.get_elements() == {"a", "b", "c"}


def test_unknown_element():
    group_list = tsrc.groups.GroupList(elements={"a", "b", "c"})
    with pytest.raises(tsrc.groups.UnknownElement) as e:
        group_list.add("invalid-group", {"no-such-element"})
    assert e.value.group_name == "invalid-group"
    assert e.value.element == "no-such-element"


def test_unknown_include():
    group_list = tsrc.groups.GroupList(elements={"a", "b", "c"})
    group_list.add("default", {"a", "b"})
    group_list.add("invalid-group", {"c"}, includes={"no-such-group"})
    with pytest.raises(tsrc.groups.GroupNotFound) as e:
        group_list.get_elements(groups={"invalid-group"})
    assert e.value.parent_group.name == "invalid-group"
    assert e.value.group_name == "no-such-group"


def test_unknown_group():
    group_list = tsrc.groups.GroupList(elements={"a", "b", "c"})
    group_list.add("default", {"a", "b"})
    with pytest.raises(tsrc.groups.GroupNotFound) as e:
        group_list.get_elements(groups={"no-such-group"})
    assert e.value.parent_group is None
    assert e.value.group_name == "no-such-group"
