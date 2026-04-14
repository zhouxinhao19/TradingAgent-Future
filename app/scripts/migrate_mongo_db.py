import argparse
import os
from typing import Iterable, List, Optional, Set

from pymongo import MongoClient

from app.core.config import settings


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _get_collection_names(db) -> List[str]:
    return sorted(db.list_collection_names())


def _iter_collections(
    db,
    include: Optional[Set[str]],
    exclude: Set[str],
) -> List[str]:
    names = _get_collection_names(db)
    if include:
        names = [n for n in names if n in include]
    if exclude:
        names = [n for n in names if n not in exclude]
    return names


def _copy_collection(
    source_db,
    target_db,
    name: str,
    drop_target: bool,
    dry_run: bool,
    batch_size: int,
) -> dict:
    src = source_db[name]
    tgt = target_db[name]

    src_count = src.estimated_document_count()
    tgt_count_before = tgt.estimated_document_count() if name in target_db.list_collection_names() else 0

    if dry_run:
        return {
            "collection": name,
            "source_count": src_count,
            "target_count_before": tgt_count_before,
            "target_count_after": tgt_count_before,
            "dropped": False,
            "upserted": 0,
        }

    dropped = False
    if drop_target and name in target_db.list_collection_names():
        tgt.drop()
        dropped = True

    upserted = 0
    cursor = src.find({}, no_cursor_timeout=True).batch_size(batch_size)
    try:
        ops = []
        for doc in cursor:
            doc_id = doc.get("_id")
            if doc_id is None:
                continue
            ops.append(({"_id": doc_id}, doc))
            if len(ops) >= batch_size:
                for filt, repl in ops:
                    tgt.replace_one(filt, repl, upsert=True)
                upserted += len(ops)
                ops = []
        if ops:
            for filt, repl in ops:
                tgt.replace_one(filt, repl, upsert=True)
            upserted += len(ops)
    finally:
        cursor.close()

    tgt_count_after = tgt.estimated_document_count()
    return {
        "collection": name,
        "source_count": src_count,
        "target_count_before": tgt_count_before,
        "target_count_after": tgt_count_after,
        "dropped": dropped,
        "upserted": upserted,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="migrate_mongo_db")
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI") or settings.MONGO_URI)
    parser.add_argument("--source-db", default=os.getenv("MONGO_SOURCE_DB") or "tradingagents")
    parser.add_argument("--target-db", default=os.getenv("MONGO_TARGET_DB") or settings.MONGO_DB)
    parser.add_argument("--include", default="", help="Comma-separated collection names to include")
    parser.add_argument("--exclude", default="", help="Comma-separated collection names to exclude")
    parser.add_argument("--drop-target", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(list(argv) if argv is not None else None)

    include = set(_split_csv(args.include)) or None
    exclude = set(_split_csv(args.exclude))

    client = MongoClient(args.mongo_uri)
    try:
        source_db = client[args.source_db]
        target_db = client[args.target_db]

        collections = _iter_collections(source_db, include, exclude)
        results = []
        for name in collections:
            results.append(
                _copy_collection(
                    source_db=source_db,
                    target_db=target_db,
                    name=name,
                    drop_target=args.drop_target,
                    dry_run=args.dry_run,
                    batch_size=args.batch_size,
                )
            )

        total = {
            "source_db": args.source_db,
            "target_db": args.target_db,
            "collections": results,
        }
        print(total)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
