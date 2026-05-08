r"""
从 movielens_data 导入电影数据到 Agent RAG 知识库

数据源: d:\Code\Movie_Rec_Agent\data\movielens_data
目标: d:\Code\movie-rec-agent\data\movies.json (RAG 知识库)
"""

import json
import pickle
from pathlib import Path

import pandas as pd

# 数据源路径
DATA_DIR = Path(r"d:\Code\Movie_Rec_Agent\data\movielens_data")

# 目标路径
AGENT_DATA_DIR = Path(r"d:\Code\movie-rec-agent\data")
OUTPUT_FILE = AGENT_DATA_DIR / "movies_rich.json"

# 海报路径
IMAGE_DIR = Path(r"d:\Code\Movie_Rec_Agent\data\movielens_data\image")


def load_pickle(file_path: str) -> pd.DataFrame:
    """加载 pickle 文件"""
    print(f"加载 {file_path}...")
    try:
        with open(file_path, "rb") as f:
            df = pickle.load(f)
        print(f"  成功加载 {len(df)} 条记录")
        return df
    except Exception as e:
        print(f"  加载失败: {e}")
        return None


def load_metadata(file_path: str) -> dict:
    """加载元数据字典"""
    print(f"加载元数据 {file_path}...")
    try:
        with open(file_path, "rb") as f:
            metadata = pickle.load(f)
        for key, df in metadata.items():
            print(f"  - {key}: {len(df)} 条记录")
        return metadata
    except Exception as e:
        print(f"  加载失败: {e}")
        return {}


def parse_genres(genres_str) -> str:
    """解析类型字符串"""
    if pd.isna(genres_str):
        return "未知"
    if isinstance(genres_str, str):
        # MovieLens 格式: Action|Comedy|Drama
        genres = [g.strip() for g in genres_str.split("|") if g.strip()]
        return ",".join(genres) if genres else "未知"
    if isinstance(genres_str, list):
        return ",".join([str(g) for g in genres_str if str(g).strip()])
    return "未知"


def translate_genres(genres_en: str) -> str:
    """翻译英文类型为中文"""
    genre_map = {
        "Action": "动作",
        "Adventure": "冒险",
        "Animation": "动画",
        "Children": "儿童",
        "Children's": "儿童",
        "Comedy": "喜剧",
        "Crime": "犯罪",
        "Documentary": "纪录片",
        "Drama": "剧情",
        "Fantasy": "奇幻",
        "Film-Noir": "黑色电影",
        "Horror": "恐怖",
        "IMAX": "IMAX",
        "Musical": "音乐",
        "Mystery": "悬疑",
        "Romance": "爱情",
        "Sci-Fi": "科幻",
        "Thriller": "惊悚",
        "War": "战争",
        "Western": "西部",
        "未知": "未知",
    }

    parts = genres_en.split(",")
    translated = []
    for p in parts:
        p_stripped = p.strip()
        # 先查完整匹配，再查部分匹配
        if p_stripped in genre_map:
            translated.append(genre_map[p_stripped])
        else:
            # 尝试模糊匹配
            found = False
            for key, val in genre_map.items():
                if key.lower() in p_stripped.lower():
                    translated.append(val)
                    found = True
                    break
            if not found:
                translated.append(p_stripped)

    return ",".join(translated)


def get_image_path(movie_id: int) -> str:
    """获取海报路径"""
    img_file = IMAGE_DIR / f"{movie_id}.png"
    if img_file.exists():
        return f"/images/{movie_id}.png"
    return ""


def create_movie_record(
    movie_id: int,
    title: str,
    year: int,
    genres_en: str,
    description: str = "",
    imdb_id: str = None,
    imdb_rating: float = None,
    imdb_votes: int = None,
    avg_rating: float = None,
    rating_count: int = 0,
) -> dict:
    """创建电影记录"""
    genres_en_clean = parse_genres(genres_en)
    genres_cn = translate_genres(genres_en_clean)

    # 清理标题中的年份
    import re

    title_clean = re.sub(r"\(\d{4}\)\s*$", "", title).strip()

    # 提取导演信息（如果有imdb_id）
    director = "未知"
    actors = []

    # 构建简介
    if not description:
        description = f"《{title_clean}》是一部{genres_cn}类型的电影。"

    return {
        "id": movie_id,
        "imdb_id": imdb_id if imdb_id else "",
        "title": title_clean,
        "year": year if year else "未知",
        "genres_en": genres_en_clean,
        "genres": genres_cn,
        "director": director,
        "actors": actors,
        "overview": description,
        "rating": imdb_rating if imdb_rating else (avg_rating if avg_rating else 0),
        "rating_count": rating_count,
        "imdb_votes": imdb_votes if imdb_votes else 0,
        "poster": get_image_path(movie_id),
        "source": "movielens",
    }


def main():
    """主函数"""
    print("=" * 60)
    print("从 movielens_data 导入电影数据到 Agent RAG 知识库")
    print("=" * 60)

    # 检查数据目录
    if not DATA_DIR.exists():
        print(f"错误: 数据目录不存在: {DATA_DIR}")
        return

    # 加载基础电影数据
    movies_pkl = DATA_DIR / "movies.pkl"
    df_movies = load_pickle(str(movies_pkl))

    if df_movies is None or len(df_movies) == 0:
        print("错误: 无法加载电影数据")
        return

    print(f"\n电影数据列: {list(df_movies.columns)}")
    print("前5条记录:")
    print(df_movies.head())

    # 加载元数据（包含IMDb评分、人物信息等）
    metadata_pkl = DATA_DIR / "movie_metadata.pkl"
    metadata = load_metadata(str(metadata_pkl))

    # 提取各元数据表
    df_title_ratings = metadata.get("title_ratings", None)
    df_name_basics = metadata.get("name_basics", None)
    df_title_crew = metadata.get("title_crew", None)
    df_title_principals = metadata.get("title_principals", None)

    # 构建IMDb评分字典 (imdb_id -> rating/votes)
    imdb_ratings_dict = {}
    if df_title_ratings is not None:
        for _, row in df_title_ratings.iterrows():
            tconst = row.get("tconst", "")
            if pd.notna(tconst):
                imdb_ratings_dict[str(tconst)] = {
                    "rating": float(row.get("averageRating", 0)),
                    "votes": int(row.get("numVotes", 0)),
                }
        print(f"\nIMDb评分数据: {len(imdb_ratings_dict)} 条")

    # 构建导演字典 (imdb_id -> directors)
    directors_dict = {}
    if df_title_crew is not None:
        for _, row in df_title_crew.iterrows():
            tconst = row.get("tconst", "")
            if pd.notna(tconst):
                directors = row.get("directors", [])
                if pd.notna(directors):
                    directors_dict[str(tconst)] = (
                        directors if isinstance(directors, list) else [directors]
                    )
        print(f"导演数据: {len(directors_dict)} 条")

    # 构建人物名称字典 (nconst -> name)
    names_dict = {}
    if df_name_basics is not None:
        for _, row in df_name_basics.iterrows():
            nconst = row.get("nconst", "")
            if pd.notna(nconst):
                names_dict[str(nconst)] = str(row.get("primaryName", ""))
        print(f"人物数据: {len(names_dict)} 条")

    # 构建主要演员字典 (imdb_id -> actors)
    actors_dict = {}
    if df_title_principals is not None:
        for _, row in df_title_principals.iterrows():
            tconst = row.get("tconst", "")
            if pd.notna(tconst):
                nconst = row.get("nconst", "")
                category = row.get("category", "")
                if pd.notna(tconst) and pd.notna(nconst) and "actor" in str(category).lower():
                    if tconst not in actors_dict:
                        actors_dict[tconst] = []
                    actor_name = names_dict.get(nconst, nconst)
                    if actor_name:
                        actors_dict[tconst].append(actor_name)
        print(f"演员数据: {len(actors_dict)} 条")

    # 转换为Agent RAG格式
    print("\n" + "=" * 60)
    print("转换电影数据...")
    print("=" * 60)

    movies_list = []

    for idx, row in df_movies.iterrows():
        movie_id = int(row.get("movie_id", 0))
        title = str(row.get("title", "未知"))

        # 处理年份
        year = row.get("startYear", None)
        if pd.notna(year) and str(year) != "\\N":
            try:
                year = int(year)
            except:
                year = "未知"
        else:
            year = "未知"

        # 处理类型
        genres = row.get("genres", "")

        # 处理描述
        description = str(row.get("description", "")) if pd.notna(row.get("description")) else ""

        # 处理IMDb ID
        imdb_id = row.get("imdb_id", None)
        if pd.isna(imdb_id) or str(imdb_id) == "\\N":
            imdb_id = None

        # 获取IMDb评分
        imdb_rating = None
        imdb_votes = 0
        if imdb_id and imdb_id in imdb_ratings_dict:
            imdb_rating = imdb_ratings_dict[imdb_id]["rating"]
            imdb_votes = imdb_ratings_dict[imdb_id]["votes"]

        # 获取导演
        director = "未知"
        if imdb_id and imdb_id in directors_dict:
            director_nconsts = directors_dict[imdb_id]
            director_names = [names_dict.get(n, n) for n in director_nconsts if n in names_dict]
            if director_names:
                director = ",".join(director_names)

        # 获取演员
        actors = []
        if imdb_id and imdb_id in actors_dict:
            actors = actors_dict[imdb_id][:5]  # 最多5个演员

        # 获取MovieLens评分（直接从movies.pkl）
        avg_rating = row.get("averageRating", None)
        rating_count = row.get("numVotes", 0)
        if pd.isna(avg_rating):
            avg_rating = None
        if pd.isna(rating_count):
            rating_count = 0

        # 使用movies.pkl中的评分
        if avg_rating and avg_rating > 0:
            imdb_rating = float(avg_rating)
            imdb_votes = int(rating_count) if rating_count else 0

        # 创建记录
        movie = create_movie_record(
            movie_id=movie_id,
            title=title,
            year=year,
            genres_en=genres,
            description=description,
            imdb_id=imdb_id,
            imdb_rating=imdb_rating,
            imdb_votes=imdb_votes,
            avg_rating=avg_rating,
            rating_count=rating_count,
        )
        movie["director"] = director
        movie["actors"] = actors

        movies_list.append(movie)

        if (idx + 1) % 500 == 0:
            print(f"  已处理 {idx + 1}/{len(df_movies)} 部电影")

    print(f"\n总共转换 {len(movies_list)} 部电影")

    # 统计数据
    with_ratings = sum(1 for m in movies_list if m["rating"] and m["rating"] > 0)
    with_posters = sum(1 for m in movies_list if m["poster"])
    with_directors = sum(1 for m in movies_list if m["director"] and m["director"] != "未知")
    with_actors = sum(1 for m in movies_list if m["actors"])

    print("\n数据统计:")
    print(f"  有评分: {with_ratings} 部 ({with_ratings / len(movies_list) * 100:.1f}%)")
    print(f"  有海报: {with_posters} 部 ({with_posters / len(movies_list) * 100:.1f}%)")
    print(f"  有导演: {with_directors} 部 ({with_directors / len(movies_list) * 100:.1f}%)")
    print(f"  有演员: {with_actors} 部 ({with_actors / len(movies_list) * 100:.1f}%)")

    # 保存
    AGENT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n保存到: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(movies_list, f, ensure_ascii=False, indent=2)

    print(f"文件大小: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB")
    print("\n导入完成!")

    # 显示示例
    print("\n示例电影:")
    for movie in movies_list[:3]:
        print(
            f"  - {movie['title']} ({movie['year']}) - {movie['genres']} - 评分: {movie['rating']}"
        )


if __name__ == "__main__":
    main()
