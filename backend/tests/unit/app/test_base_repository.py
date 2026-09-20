import datetime as dt

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.errors import ConflictError
from app.repositories.base import BaseRepository


class Widget(BaseModel):
    id: str = Field(alias="_id")
    name: str
    rank: int = 0
    created_at: dt.datetime | None = None

    model_config = {"populate_by_name": True}


class WidgetRepo(BaseRepository[Widget]):
    collection_name = "widgets"
    model = Widget


@pytest.fixture
async def repo(mongo_db: AsyncIOMotorDatabase) -> WidgetRepo:
    await mongo_db.widgets.create_index("name", unique=True)
    return WidgetRepo(mongo_db)


async def test_insert_get_round_trip(repo: WidgetRepo) -> None:
    created = dt.datetime.now(dt.UTC).replace(microsecond=0)
    await repo.insert(Widget(id="w1", name="a", rank=2, created_at=created))
    got = await repo.get("w1")
    assert got is not None
    assert (got.id, got.name, got.rank) == ("w1", "a", 2)
    assert got.created_at == created
    assert got.created_at.tzinfo is not None


async def test_stored_document_uses_underscore_id(
    repo: WidgetRepo, mongo_db: AsyncIOMotorDatabase
) -> None:
    await repo.insert(Widget(id="w1", name="a"))
    raw = await mongo_db.widgets.find_one({"_id": "w1"})
    assert raw is not None
    assert "id" not in raw


async def test_get_missing_returns_none(repo: WidgetRepo) -> None:
    assert await repo.get("nope") is None


async def test_find_one(repo: WidgetRepo) -> None:
    await repo.insert(Widget(id="w1", name="a"))
    assert (await repo.find_one({"name": "a"})).id == "w1"  # type: ignore[union-attr]
    assert await repo.find_one({"name": "zzz"}) is None


async def test_find_many_filter_sort_limit(repo: WidgetRepo) -> None:
    for i, name in enumerate(["c", "a", "b", "d"]):
        await repo.insert(Widget(id=f"w{i}", name=name, rank=i))
    got = await repo.find_many({"rank": {"$lt": 3}}, sort=[("name", 1)], limit=2)
    assert [w.name for w in got] == ["a", "b"]


async def test_update_one_reports_modification(repo: WidgetRepo) -> None:
    await repo.insert(Widget(id="w1", name="a"))
    assert await repo.update_one("w1", {"$set": {"rank": 9}}) is True
    assert (await repo.get("w1")).rank == 9  # type: ignore[union-attr]
    assert await repo.update_one("missing", {"$set": {"rank": 1}}) is False


async def test_delete(repo: WidgetRepo) -> None:
    await repo.insert(Widget(id="w1", name="a"))
    assert await repo.delete("w1") is True
    assert await repo.delete("w1") is False
    assert await repo.get("w1") is None


async def test_duplicate_key_raises_conflict(repo: WidgetRepo) -> None:
    await repo.insert(Widget(id="w1", name="a"))
    with pytest.raises(ConflictError) as exc:
        await repo.insert(Widget(id="w2", name="a"))
    assert exc.value.status_code == 409
    assert exc.value.code == "CONFLICT"
