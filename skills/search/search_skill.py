"""
搜索技能

处理用户的搜索请求，搜索特定电影
"""

from typing import Dict, Any, List
import json

import structlog

from skills.base import BaseSkill

logger = structlog.get_logger()


class SearchSkill(BaseSkill):
    """
    搜索技能
    
    处理用户的搜索请求，搜索特定电影
    """
    
    name: str = "search_skill"
    description: str = "搜索特定电影"
    priority: int = 1  # 高优先级，搜索意图应该优先处理
    
    async def _execute(
        self,
        query: str,
        user_id: str = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        执行搜索
        
        Args:
            query: 搜索关键词
            user_id: 用户 ID
            top_k: 结果数量
            
        Returns:
            搜索结果
        """
        logger.info("执行搜索技能", query=query, user_id=user_id)
        
        try:
            # 从本地 JSON 文件搜索
            results = await self._search_local(query, top_k)
            
            if results:
                return {
                    "success": True,
                    "response": f"找到 {len(results)} 部与 '{query}' 相关的电影",
                    "data": {"query": query, "results": results, "count": len(results)},
                    "skill": self.name
                }
            else:
                return {
                    "success": True,
                    "response": f"未找到与 '{query}' 相关的电影",
                    "data": {"query": query, "results": [], "count": 0},
                    "skill": self.name
                }
                
        except Exception as e:
            logger.error("搜索技能执行失败", query=query, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "skill": self.name
            }
    
    async def _search_local(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """本地 JSON 文件搜索"""
        import os
        movies_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "movies_rich.json")
        
        if not os.path.exists(movies_file):
            movies_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "movies.json")
        
        if not os.path.exists(movies_file):
            return []
        
        with open(movies_file, "r", encoding="utf-8") as f:
            movies = json.load(f)
        
        query_lower = query.lower()
        matched = []
        
        for movie in movies:
            title = movie.get("title", "").lower()
            title_en = movie.get("title_en", "").lower()
            genres = movie.get("genres", "").lower() if isinstance(movie.get("genres"), str) else " ".join(movie.get("genres", [])).lower()
            
            if query_lower in title or query_lower in title_en or query_lower in genres:
                matched.append(movie)
                if len(matched) >= top_k:
                    break
        
        return matched[:top_k]
