"""
测试向量检索不同阈值的效果
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# 初始化
client = QdrantClient(
    url='http://180.184.30.94:6333',
    api_key=os.getenv('QDRANT_API_KEY', 'Xc13129092470'),
    timeout=10
)

model = SentenceTransformer('BAAI/bge-m3')

query = '近岸海域环境监测技术规范'
query_vector = model.encode(query, normalize_embeddings=True).tolist()

collection = 'kb_b81336cf_e9ae_42e6_9314_8728d0a3e1ac'

print('=== Testing different score thresholds ===')
print(f'Query: {query}')
print(f'Collection: {collection}')
print()

for threshold in [0.1, 0.2, 0.3, 0.4, 0.5]:
    results = client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=5,
        score_threshold=threshold
    )
    print(f'Threshold {threshold}: {len(results)} results')
    if results:
        print(f'  Top score: {results[0].score:.3f}')
        content = results[0].payload.get("content", "")
        print(f'  Content preview: {content[:80]}...')
    print()
