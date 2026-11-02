import asyncio
from dataclasses import FrozenInstanceError
import importlib.util
import uuid

import pytest
from controlplane_tenancy import db_session
from controlplane_tenancy.directory import UserView
from controlplane_tenancy.tenant_guc import set_current_tenant_id_guc


def test_detached_view_json_and_frozen_fields():
    user = UserView(uuid.uuid4(), uuid.uuid4(), 'user@example.com', 'User', 'View', 'unknown', True, None, None, None, {'teams':['one']})
    user.sociacl_attributes['teams'].append('two')
    assert user.sociacl_attributes == {'teams':['one']}
    with pytest.raises(FrozenInstanceError): user.first_name = 'changed'
    assert not hasattr(user, '_sa_instance_state')


@pytest.mark.parametrize('name', ['api', 'user_service', 'fastapi'])
def test_no_legacy_service_dependency(name):
    assert importlib.util.find_spec(name) is None


def test_nested_session_context_resets():
    with pytest.raises(RuntimeError): db_session.get_db_session()
    outer, inner = object(), object()
    token = db_session.set_db_session(outer)
    try:
        nested = db_session.set_db_session(inner)
        assert db_session.get_db_session() is inner
        db_session.reset_db_session(nested)
        assert db_session.get_db_session() is outer
    finally: db_session.reset_db_session(token)
    with pytest.raises(RuntimeError): db_session.get_db_session()


@pytest.mark.asyncio
@pytest.mark.parametrize('tenant', [None, uuid.UUID('11111111-1111-4111-8111-111111111111')])
async def test_guc_is_transaction_local_and_parameterized(tenant):
    calls = []
    class Session:
        async def execute(self, statement, params=None): calls.append((str(statement), params))
    await set_current_tenant_id_guc(Session(), tenant)
    sql, params = calls[0]
    assert 'true)' in sql
    assert params == (None if tenant is None else {'tid':str(tenant)})
