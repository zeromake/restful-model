import pytest
import asyncio
import copy

from datetime import datetime

from .model import User
from restful_model.view import BaseView
from restful_model.context import Context
from restful_model.database import DataBase
from restful_model.utils import return_true
from urllib.parse import quote_plus as urlquote


class ApiView(BaseView):
    __model__ = User


async def build_db():
    db_name = urlquote(":memory:")
    db = DataBase("sqlite:///%s" % db_name, asyncio.get_event_loop())
    db.engine = await db.create_engine(echo=True)
    return db


async def insert_user(api: "ApiView"):
    user1 = {
        "account": "test1",
        "email": "test1@test.com",
        "role_name": "昵称1",
        "password": "123456",
        "create_time": int(datetime.now().timestamp()),
    }
    create_context = Context("post", "", {}, form_data=user1)
    assert {
        "status": 201,
        "message": "Insert ok!",
        "meta": {"count": 1, "rowid": 1}
    } == await api.post(create_context, return_true)
    # context = Context("get", "/user", {})
    user1["id"] = 1
    query_context = Context("get", "/user", {})
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": [user1]
    } == await api.get(query_context, return_true)
    del user1["id"]
    return user1


@pytest.mark.asyncio
async def test_view_query():
    """
    测试view的查询
    """
    db = await build_db()
    api = ApiView(db)
    await db.create_table(User)
    query_context = Context("get", "/user", {})
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": []
    } == await api.get(query_context, return_true)
    user1 = {
        "account": "test1",
        "email": "test1@test.com",
        "role_name": "昵称1",
        "password": "123456",
        "create_time": int(datetime.now().timestamp()),
    }
    create_context = Context("post", "", {}, form_data=user1)
    assert {
        "status": 201,
        "message": "Insert ok!",
        "meta": {"count": 1, "rowid": 1}
    } == await api.post(create_context, return_true)
    # context = Context("get", "/user", {})
    user1["id"] = 1
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": [user1]
    } == await api.get(query_context, return_true)


@pytest.mark.asyncio
async def test_view_create():
    db = await build_db()
    await db.create_table(User)
    api = ApiView(db)
    user1 =  await insert_user(api)
    user2 = copy.copy(user1)
    user3 = copy.copy(user1)
    user2["account"] = "test2"
    user3["account"] = "test3"
    create_context2 = Context("post", "", {}, form_data=[user2, user3])
    assert {
        "status": 201,
        "message": "Insert ok!",
        "meta": {"count": 3}
    } == await api.post(create_context2, return_true)
    user1["id"] = 1
    user2["id"] = 2
    user3["id"] = 3
    query_context = Context("get", "/user", {})
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": [user1, user2, user3]
    } == await api.get(query_context, return_true)


@pytest.mark.asyncio
async def test_view_delete():
    db = await build_db()
    await db.create_table(User)
    api = ApiView(db)
    await insert_user(api)
    query_context = Context("get", "/user", {})
    delete_context = Context("delete", "", {}, form_data={"id": 1})
    assert {
        "status": 200,
        "message": "Delete ok!",
        "meta": {"count": 1}
    } == await api.delete(delete_context, return_true)
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": []
    } == await api.get(query_context, return_true)


@pytest.mark.asyncio
async def test_view_update():
    db = await build_db()
    await db.create_table(User)
    api = ApiView(db)
    user1 = await insert_user(api)
    user2 = copy.copy(user1)
    user2["account"] = "test2"
    put_context = Context(
        "put",
        "",
        {},
        form_data={
            "where": {"id": 1},
            "values": {"account": "test2"},
        },
    )
    assert {
        "status": 201,
        "message": "Update ok!",
        "meta": {"count": 1}
    } == await api.put(put_context, return_true)
    user2["id"] = 1
    query_context = Context("get", "/user", {})
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": [user2]
    } == await api.get(query_context, return_true)

    assert {
        "status": 201,
        "message": "Update ok!",
        "meta": {"count": 1}
    } == await api.patch(put_context, return_true)


@pytest.mark.asyncio
async def test_view_query2():
    db = await build_db()
    await db.create_table(User)
    api = ApiView(db)
    user1 = await insert_user(api)
    query_context1 = Context("get", "/user", {}, url_param={"id": 1})
    user1["id"] = 1
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": user1
    } == await api.dispatch_request(query_context1, return_true)
    query_context2 = Context("get", "/user", {}, form_data={"limit": [0, 10]})
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": [user1],
        "meta": {
            "pagination": {
                "total": 1,
                "count": 1,
                'skip': 0,
                'limit': 10
            }
        }
    } == await api.dispatch_request(query_context2, return_true)
    query_context3 = Context("get", "/user", {}, args={"limit": ["[0, 10]"], "order": ["00000"]})
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": [user1],
        "meta": {
            "pagination": {
                "total": 1,
                "count": 1,
                'skip': 0,
                'limit': 10
            }
        }
    } == await api.dispatch_request(query_context3, return_true)

    query_context3 = Context("post", "/user", {}, args={"method": ["get"]})
    assert {
        "status": 200,
        "message": "Query ok!",
        "data": [user1],
    } == await api.dispatch_request(query_context3, return_true)
