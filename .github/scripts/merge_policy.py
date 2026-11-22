"""Account policy for approvals and squash merges into main."""


DELEGATE = "nguyenhuy1804"
COLLABORATOR_ASSOCIATIONS = {"COLLABORATOR", "MEMBER", "OWNER"}


def is_authorized_merger(login, owner):
    return bool(login and login.casefold() in {owner.casefold(), DELEGATE})


def is_eligible_reviewer(reviewer, author, owner, association):
    reviewer = reviewer.casefold()
    author = author.casefold()
    owner = owner.casefold()
    if reviewer == author:
        return False
    if reviewer == owner:
        return True
    return association in COLLABORATOR_ASSOCIATIONS and (
        author in {owner, DELEGATE} or reviewer == DELEGATE
    )
