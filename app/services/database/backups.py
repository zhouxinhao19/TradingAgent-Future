"""
Backup, import, and export routines extracted from DatabaseService.
"""
from __future__ import annotations

import json
import os
import gzip
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.core.database import get_mongo_db
from .serialization import serialize_document


async def create_backup(name: str, backup_dir: str, collections: Optional[List[str]] = None, user_id: str | None = None) -> Dict[str, Any]:
    db = get_mongo_db()

    backup_id = str(ObjectId())
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{name}_{timestamp}.json.gz"
    backup_path = os.path.join(backup_dir, backup_filename)

    if not collections:
        collections = await db.list_collection_names()

    backup_data: Dict[str, Any] = {
        "backup_id": backup_id,
        "name": name,
        "created_at": datetime.utcnow().isoformat(),
        "created_by": user_id,
        "collections": collections,
        "data": {},
    }

    for collection_name in collections:
        collection = db[collection_name]
        documents: List[dict] = []
        async for doc in collection.find():
            documents.append(serialize_document(doc))
        backup_data["data"][collection_name] = documents

    os.makedirs(backup_dir, exist_ok=True)
    with gzip.open(backup_path, "wt", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(backup_path)

    backup_meta = {
        "_id": ObjectId(backup_id),
        "name": name,
        "filename": backup_filename,
        "file_path": backup_path,
        "size": file_size,
        "collections": collections,
        "created_at": datetime.utcnow(),
        "created_by": user_id,
    }

    await db.database_backups.insert_one(backup_meta)

    return {
        "id": backup_id,
        "name": name,
        "filename": backup_filename,
        "file_path": backup_path,
        "size": file_size,
        "collections": collections,
        "created_at": backup_meta["created_at"].isoformat(),
    }


async def list_backups() -> List[Dict[str, Any]]:
    db = get_mongo_db()
    backups: List[Dict[str, Any]] = []
    async for backup in db.database_backups.find().sort("created_at", -1):
        backups.append({
            "id": str(backup["_id"]),
            "name": backup["name"],
            "filename": backup["filename"],
            "size": backup["size"],
            "collections": backup["collections"],
            "created_at": backup["created_at"].isoformat(),
            "created_by": backup.get("created_by"),
        })
    return backups


async def delete_backup(backup_id: str) -> None:
    db = get_mongo_db()
    backup = await db.database_backups.find_one({"_id": ObjectId(backup_id)})
    if not backup:
        raise Exception("备份不存在")
    if os.path.exists(backup["file_path"]):
        os.remove(backup["file_path"])
    await db.database_backups.delete_one({"_id": ObjectId(backup_id)})


async def import_data(content: bytes, collection: str, *, format: str = "json", overwrite: bool = False, filename: str | None = None) -> Dict[str, Any]:
    db = get_mongo_db()
    collection_obj = db[collection]

    if format.lower() == "json":
        data = json.loads(content.decode("utf-8"))
    else:
        raise Exception(f"不支持的格式: {format}")

    if not isinstance(data, list):
        data = [data]

    if overwrite:
        await collection_obj.delete_many({})

    for doc in data:
        if "_id" in doc and isinstance(doc["_id"], str):
            try:
                doc["_id"] = ObjectId(doc["_id"])
            except Exception:
                del doc["_id"]

    inserted_count = 0
    if data:
        res = await collection_obj.insert_many(data)
        inserted_count = len(res.inserted_ids)

    return {
        "collection": collection,
        "inserted_count": inserted_count,
        "filename": filename,
        "format": format,
        "overwrite": overwrite,
    }


async def export_data(collections: Optional[List[str]] = None, *, export_dir: str, format: str = "json") -> str:
    import pandas as pd

    db = get_mongo_db()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if not collections:
        collections = await db.list_collection_names()
        collections = [c for c in collections if not c.startswith("system.")]

    os.makedirs(export_dir, exist_ok=True)

    all_data: Dict[str, List[dict]] = {}
    for collection_name in collections:
        collection = db[collection_name]
        docs: List[dict] = []
        async for doc in collection.find():
            docs.append(serialize_document(doc))
        all_data[collection_name] = docs

    if format.lower() == "json":
        filename = f"export_{timestamp}.json"
        file_path = os.path.join(export_dir, filename)
        export_data = {
            "export_info": {
                "created_at": datetime.utcnow().isoformat(),
                "collections": collections,
                "format": format,
            },
            "data": all_data,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return file_path

    if format.lower() == "csv":
        filename = f"export_{timestamp}.csv"
        file_path = os.path.join(export_dir, filename)
        rows: List[dict] = []
        for collection_name, documents in all_data.items():
            for doc in documents:
                row = {**doc}
                row["_collection"] = collection_name
                rows.append(row)
        if rows:
            pd.DataFrame(rows).to_csv(file_path, index=False, encoding="utf-8-sig")
        else:
            pd.DataFrame().to_csv(file_path, index=False, encoding="utf-8-sig")
        return file_path

    if format.lower() in ["xlsx", "excel"]:
        filename = f"export_{timestamp}.xlsx"
        file_path = os.path.join(export_dir, filename)
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            for collection_name, documents in all_data.items():
                df = pd.DataFrame(documents) if documents else pd.DataFrame()
                sheet = collection_name[:31]
                df.to_excel(writer, sheet_name=sheet, index=False)
        return file_path

    raise Exception(f"不支持的导出格式: {format}")

