"""No models — auth/roles/permissions here are Django's own User/Group/
Permission (see accounts/apps.py, accounts/migrations/0001).

This file exists anyway, empty, because Django's ``emit_post_migrate_signal``
skips any app whose ``AppConfig.models_module`` is ``None`` — which is what
happens when an app has no ``models.py`` at all. Without this file, the
``post_migrate`` receiver in ``accounts/apps.py`` would never fire, silently
defeating the whole point of it (confirmed empirically: a
``transaction=True`` test's ``flush`` teardown wiped the "Staff" group and
nothing restored it, because the signal was never being sent for this app
in the first place).
"""

from __future__ import annotations
