"""
IMDb API 客户端

使用 IMDb 的免费 API（通过 OMDb API）搜索电影信息
"""

import os
from typing import Any, Dict, List, Optional

import aiohttp
import structlog

logger = structlog.get_logger()


class IMDbAPIClient:
    """
    IMDb API 客户端

    使用 OMDb API (http://www.omdbapi.com/) 作为 IMDb 数据源
    免费版支持每天 1000 次请求
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 IMDb API 客户端

        Args:
            api_key: OMDb API Key（可从 http://www.omdbapi.com/apikey.aspx 免费获取）
        """
        self.api_key = api_key or os.getenv("IMDB_API_KEY")
        self.base_url = "http://www.omdbapi.com/"
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """初始化 HTTP 会话"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            logger.info("IMDb API 客户端初始化完成")

    async def close(self):
        """关闭 HTTP 会话"""
        if self.session:
            await self.session.close()
            self.session = None

    async def search_by_title(
        self, title: str, year: Optional[str] = None, page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        根据标题搜索电影

        Args:
            title: 电影标题
            year: 可选的年份
            page: 页码

        Returns:
            搜索结果列表
        """
        if not self.api_key:
            logger.warning("未配置 IMDb API Key")
            return []

        params = {"apikey": self.api_key, "s": title, "type": "movie", "page": str(page)}

        if year:
            params["y"] = year

        try:
            async with self.session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("Response") == "True":
                        movies = data.get("Search", [])
                        logger.info("IMDb 搜索成功", title=title, count=len(movies))
                        return movies
                    else:
                        logger.info("IMDb 未找到结果", title=title, error=data.get("Error"))
                        return []
                else:
                    logger.error("IMDb API 请求失败", status=response.status)
                    return []
        except Exception as e:
            logger.error("IMDb 搜索异常", error=str(e))
            return []

    async def get_movie_details(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        """
        获取电影详细信息

        Args:
            imdb_id: IMDb ID（如 tt0111161）

        Returns:
            电影详细信息
        """
        if not self.api_key:
            logger.warning("未配置 IMDb API Key")
            return None

        params = {"apikey": self.api_key, "i": imdb_id, "plot": "short"}

        try:
            async with self.session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("Response") == "True":
                        logger.info("IMDb 获取详情成功", imdb_id=imdb_id, title=data.get("Title"))
                        return data
                    else:
                        logger.info("IMDb 未找到详情", imdb_id=imdb_id, error=data.get("Error"))
                        return None
                else:
                    logger.error("IMDb API 请求失败", status=response.status)
                    return None
        except Exception as e:
            logger.error("IMDb 获取详情异常", error=str(e))
            return None

    async def search_movies(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索电影（整合搜索和详情）

        Args:
            query: 搜索关键词
            top_k: 返回数量

        Returns:
            电影详细信息列表
        """
        # 先搜索标题
        search_results = await self.search_by_title(query)

        if not search_results:
            return []

        # 获取前 top_k 个结果的详细信息
        results = []
        for movie in search_results[:top_k]:
            imdb_id = movie.get("imdbID")
            if imdb_id:
                details = await self.get_movie_details(imdb_id)
                if details:
                    results.append(self._format_movie_data(details))

        return results

    def _format_movie_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化电影数据"""
        return {
            "imdb_id": data.get("imdbID", ""),
            "title": data.get("Title", ""),
            "year": data.get("Year", ""),
            "rated": data.get("Rated", ""),
            "released": data.get("Released", ""),
            "runtime": data.get("Runtime", ""),
            "genres": data.get("Genre", ""),
            "director": data.get("Director", ""),
            "writers": data.get("Writer", ""),
            "actors": data.get("Actors", ""),
            "plot": data.get("Plot", ""),
            "language": data.get("Language", ""),
            "country": data.get("Country", ""),
            "awards": data.get("Awards", ""),
            "poster": data.get("Poster", ""),
            "ratings": data.get("Ratings", []),
            "metascore": data.get("Metascore", ""),
            "imdb_rating": data.get("imdbRating", ""),
            "imdb_votes": data.get("imdbVotes", ""),
            "box_office": data.get("BoxOffice", ""),
        }


# 全局 IMDb API 客户端实例
imdb_api_client = IMDbAPIClient()
