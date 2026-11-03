"""Staff roles and what each may do. Everyone sees every client, deal and activity; roles decide who changes what."""
ROLES = ("super_admin", "account_manager", "support", "finance")
ROLE_NAMES = {"super_admin": "Super admin", "account_manager": "Account manager", "support": "Support", "finance": "Finance"}

PERMS = {
    "accounts.edit": ("super_admin", "account_manager"),            # add and change clients
    "deals.edit": ("super_admin", "account_manager"),               # the pipeline
    "contacts.edit": ("super_admin", "account_manager", "support"),
    "activities.edit": ROLES,                                       # everyone logs calls, notes and tasks
    "records.delete": ("super_admin",),                             # deleting a client or a deal
    "staff.manage": ("super_admin",),
    "audit.view": ("super_admin", "finance"),
}


def can(role: str | None, perm: str) -> bool:
    return bool(role) and role in PERMS[perm]


def perms_of(role: str) -> list[str]:
    return [p for p in PERMS if can(role, p)]
