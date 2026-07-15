"""验证 Phase 3a 路由挂载(不启 FastAPI server / MongoDB)"""
from app.routers.commodity import quotes_router, extended_router, news_router

total = len(quotes_router.routes) + len(extended_router.routes) + len(news_router.routes)
print(f"\n[Phase 3a] commodity router 端点数: {total}")
print(f"  quotes(Phase 1):    {len(quotes_router.routes)}")
print(f"  extended(Phase 3a): {len(extended_router.routes)}")
print(f"  news(Phase 3a):     {len(news_router.routes)}")

print(f"\n--- extended.py 端点清单 ---")
for r in extended_router.routes:
    m = ",".join(sorted(r.methods - {"HEAD", "OPTIONS"}))
    print(f"  {m:8s} {r.path}")

print(f"\n--- news.py 端点清单 ---")
for r in news_router.routes:
    m = ",".join(sorted(r.methods - {"HEAD", "OPTIONS"}))
    print(f"  {m:8s} {r.path}")
