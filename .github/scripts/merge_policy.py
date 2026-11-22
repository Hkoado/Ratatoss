"""Accounts authorized to squash merge pull requests into main."""


def is_authorized_merger(login, owner):
    return bool(login and login.casefold() in {owner.casefold(), "nguyenhuy1804"})
