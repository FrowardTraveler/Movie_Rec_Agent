"""查看 RAG 数据库内容统计"""
import json
from pathlib import Path

# 读取数据
data_file = Path(__file__).parent.parent / "data" / "movies_rich.json"
with open(data_file, 'r', encoding='utf-8') as f:
    movies = json.load(f)

print("=" * 60)
print("RAG 数据库内容统计")
print("=" * 60)
print(f"电影总数: {len(movies)}")

# 年份分布
years = []
for m in movies:
    y = m.get('year', 0)
    if isinstance(y, str) and y != '未知':
        try:
            y = int(y)
        except:
            y = 0
    elif not isinstance(y, (int, float)):
        y = 0
    if y > 0:
        years.append(y)
print(f"\n年份范围: {min(years)} - {max(years)}")

# 评分统计
ratings = [m.get('rating', 0) for m in movies if m.get('rating', 0) > 0]
print(f"有评分的电影: {len(ratings)} ({len(ratings)/len(movies)*100:.1f}%)")
if ratings:
    print(f"平均评分: {sum(ratings)/len(ratings):.2f}")
    print(f"最高评分: {max(ratings)}")
    print(f"最低评分: {min(ratings)}")

# 海报统计
posters = [m for m in movies if m.get('poster')]
print(f"\n有海报的电影: {len(posters)} ({len(posters)/len(movies)*100:.1f}%)")

# 类型统计
all_genres = {}
for m in movies:
    genres = m.get('genres', '').split(',')
    for g in genres:
        g = g.strip()
        if g and g != '未知':
            all_genres[g] = all_genres.get(g, 0) + 1

print(f"\n电影类型分布:")
for genre, count in sorted(all_genres.items(), key=lambda x: x[1], reverse=True):
    print(f"  {genre}: {count} 部")

# IMDb ID 统计
imdb_ids = [m for m in movies if m.get('imdb_id')]
print(f"\n有 IMDb ID 的电影: {len(imdb_ids)} ({len(imdb_ids)/len(movies)*100:.1f}%)")

# 描述统计
overviews = [m for m in movies if m.get('overview')]
print(f"有描述的电影: {len(overviews)} ({len(overviews)/len(movies)*100:.1f}%)")

# 数据来源
sources = {}
for m in movies:
    source = m.get('source', 'unknown')
    sources[source] = sources.get(source, 0) + 1
print(f"\n数据来源:")
for source, count in sources.items():
    print(f"  {source}: {count} 部")

print("\n" + "=" * 60)
print("示例电影（前 5 部）:")
print("=" * 60)
for m in movies[:5]:
    print(f"\nID: {m['id']}")
    print(f"标题: {m['title']}")
    print(f"年份: {m.get('year', '未知')}")
    print(f"类型: {m.get('genres', '未知')}")
    print(f"评分: {m.get('rating', '未知')}")
    print(f"描述: {m.get('overview', '无')[:80]}...")

print("\n" + "=" * 60)
print("数据结构字段:")
print("=" * 60)
if movies:
    print(f"所有字段: {list(movies[0].keys())}")
