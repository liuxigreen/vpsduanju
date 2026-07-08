# -*- coding: utf-8 -*-
"""YouTube API 客户端模块

统一封装 YouTube API 调用，包括：
- Key 轮换
- 错误处理
- 配额管理
"""
import json
import time
import urllib.request
from typing import Optional

from .config import get_competitor_api_keys, get_own_channel_api_key


class YouTubeAPIClient:
    """YouTube API 客户端
    
    支持 key 轮换和错误处理。
    """
    
    def __init__(self, api_keys: list = None, key_type: str = "competitor"):
        """初始化客户端
        
        Args:
            api_keys: API key 列表，如果为 None 则自动获取
            key_type: "competitor" 或 "own"
        """
        if api_keys is None:
            if key_type == "competitor":
                self.api_keys = get_competitor_api_keys()
            else:
                self.api_keys = [get_own_channel_api_key()]
        else:
            self.api_keys = api_keys
        
        self.current_key_index = 0
        self.base_url = "https://www.googleapis.com/youtube/v3"
    
    @property
    def current_key(self) -> str:
        """获取当前使用的 key"""
        if self.current_key_index < len(self.api_keys):
            return self.api_keys[self.current_key_index]
        return ""
    
    def _rotate_key(self):
        """轮换到下一个 key"""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
    
    def _make_request(self, endpoint: str, params: dict) -> dict:
        """发送 API 请求
        
        Args:
            endpoint: API 端点（如 "videos", "channels", "search"）
            params: 请求参数
            
        Returns:
            API 响应的 JSON 数据
            
        Raises:
            Exception: 请求失败时抛出异常
        """
        params["key"] = self.current_key
        url = f"{self.base_url}/{endpoint}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        
        for attempt in range(len(self.api_keys)):
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 403:  # 配额超限
                    self._rotate_key()
                    params["key"] = self.current_key
                    url = f"{self.base_url}/{endpoint}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
                    continue
                raise
            except Exception as e:
                if attempt < len(self.api_keys) - 1:
                    self._rotate_key()
                    params["key"] = self.current_key
                    url = f"{self.base_url}/{endpoint}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
                    continue
                raise
        
        raise Exception("所有 API key 都失败了")
    
    def get_video_details(self, video_ids: list) -> list:
        """获取视频详情
        
        Args:
            video_ids: 视频 ID 列表（最多 50 个）
            
        Returns:
            视频详情列表
        """
        if not video_ids:
            return []
        
        # YouTube API 限制每次最多 50 个
        all_items = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            params = {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
            }
            result = self._make_request("videos", params)
            all_items.extend(result.get("items", []))
            time.sleep(0.1)  # 避免请求过快
        
        return all_items
    
    def get_channel_details(self, channel_ids: list) -> list:
        """获取频道详情
        
        Args:
            channel_ids: 频道 ID 列表（最多 50 个）
            
        Returns:
            频道详情列表
        """
        if not channel_ids:
            return []
        
        all_items = []
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i:i+50]
            params = {
                "part": "snippet,statistics",
                "id": ",".join(batch),
            }
            result = self._make_request("channels", params)
            all_items.extend(result.get("items", []))
            time.sleep(0.1)
        
        return all_items
    
    def search_videos(self, query: str, max_results: int = 50, 
                      order: str = "viewCount", published_after: str = None) -> list:
        """搜索视频
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            order: 排序方式（date, rating, relevance, title, viewCount）
            published_after: 发布时间限制（ISO 8601 格式）
            
        Returns:
            视频列表
        """
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": order,
        }
        if published_after:
            params["publishedAfter"] = published_after
        
        result = self._make_request("search", params)
        return result.get("items", [])


def create_competitor_client() -> YouTubeAPIClient:
    """创建竞品采集专用的客户端"""
    return YouTubeAPIClient(key_type="competitor")


def create_own_channel_client() -> YouTubeAPIClient:
    """创建自有频道专用的客户端"""
    return YouTubeAPIClient(key_type="own")
