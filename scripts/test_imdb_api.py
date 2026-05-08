"""
测试 IMDb API 搜索功能
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

# 加载 .env 文件
env_path = Path(project_root) / ".env"
load_dotenv(dotenv_path=env_path)

import os

from services.imdb_api import imdb_api_client


async def test_imdb_search():
    """测试 IMDb 搜索"""
    print("=" * 60)
    print("IMDb API 搜索功能测试")
    print("=" * 60)

    # 检查环境变量
    api_key = os.getenv("IMDB_API_KEY")
    print(f"\n环境变量 IMDB_API_KEY: {api_key}")

    # 初始化
    await imdb_api_client.initialize()

    if not imdb_api_client.api_key:
        print("\n[错误] 未配置 IMDb API Key")
        print("请从 http://www.omdbapi.com/apikey.aspx 免费获取 API Key")
        print("并添加到 .env 文件: IMDB_API_KEY=your_key_here")
        return

    print(f"\nIMDb API Key 已配置: {imdb_api_client.api_key[:5]}...{imdb_api_client.api_key[-3:]}")

    # 测试搜索
    test_queries = ["Inception", "The Matrix", "Interstellar"]

    for query in test_queries:
        print(f"\n{'=' * 60}")
        print(f"搜索: {query}")
        print(f"{'=' * 60}")

        results = await imdb_api_client.search_movies(query, top_k=3)

        if results:
            print(f"找到 {len(results)} 部结果:\n")
            for i, movie in enumerate(results, 1):
                print(f"{i}. {movie['title']} ({movie['year']})")
                if movie.get("genres"):
                    print(f"   类型: {movie['genres']}")
                if movie.get("director"):
                    print(f"   导演: {movie['director']}")
                if movie.get("imdb_rating"):
                    print(
                        f"   IMDb 评分: {movie['imdb_rating']}/10 ({movie.get('imdb_votes', '0')} 票)"
                    )
                if movie.get("plot"):
                    plot_preview = (
                        movie["plot"][:100] + "..." if len(movie["plot"]) > 100 else movie["plot"]
                    )
                    print(f"   简介: {plot_preview}")
                print()
        else:
            print("未找到结果")

    await imdb_api_client.close()


if __name__ == "__main__":
    asyncio.run(test_imdb_search())
