"""An N-1 image must boot when Postgres is already at a newer owner head."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from controlplane_db import migrations
from controlplane_db.startup import main
from controlplane_tenancy import startup as tenancy_startup

pytestmark = pytest.mark.integration
CHAINS = migrations._ROOT


def _drop_head_script(root: Path, chain: str, revision: str) -> None:
    scripts = ScriptDirectory.from_config(migrations._config(root, chain))
    head = scripts.get_revision(revision)
    parent = head.down_revision
    assert parent is not None
    # A merged head has two parents. Model the prior image on its first-parent
    # branch, excluding the newly merged sibling scripts as well as the merge.
    prior = parent[0] if isinstance(parent, tuple) else parent
    keep = {r.revision for r in scripts.iterate_revisions(prior, 'base')}
    assert prior in keep and revision not in keep
    removed = []
    for script in scripts.walk_revisions():
        if script.revision not in keep:
            Path(script.path).unlink()
            removed.append(script.revision)
    assert revision in removed


def test_startup_boots_when_database_is_ahead_of_the_image(migration_database, tmp_path, monkeypatch, caplog):
    url = migration_database()
    migrations.upgrade(url)
    before = migrations.current_heads(url)
    root = tmp_path / 'chains'
    shutil.copytree(CHAINS, root)
    _drop_head_script(root, 'hypermesh', before['hypermesh'])
    image_head = ScriptDirectory.from_config(migrations._config(root, 'hypermesh')).get_current_head()
    assert image_head != before['hypermesh']

    monkeypatch.setattr(migrations, '_ROOT', root)
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setenv('CONTROLPLANE_MIGRATION_MODE', 'owners')
    # Legacy Alembic fileConfig disables loggers that already exist. Re-enable
    # this one so the warning is visible when those tests ran first.
    startup_log = logging.getLogger('controlplane_db.startup')
    startup_log.disabled = False
    startup_log.propagate = True
    with caplog.at_level(logging.WARNING, logger='controlplane_db.startup'):
        assert main() == 0
        assert tenancy_startup.main() == 0

    assert migrations.current_heads(url) == before
    warnings = [record.getMessage() for record in caplog.records if record.name == 'controlplane_db.startup']
    expected = (
        'skipping hypermesh upgrade: database revision '
        f'{before["hypermesh"]} is not in this image (image head {image_head})'
    )
    assert warnings == [expected, expected]
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            assert inspect(connection).has_table('hypermesh_protection_approvals')
    finally:
        engine.dispose()
