"""Shared model base: Mongo `_id` is exposed as `id`; ids are UUID4 strings (03_DATA_MODEL)."""

import uuid

from pydantic import BaseModel, ConfigDict


def new_id() -> str:
    return str(uuid.uuid4())


class MongoModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
