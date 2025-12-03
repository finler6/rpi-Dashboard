import os
import re
import yt_dlp
import instaloader
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import aiohttp
import certifi
import json
import ssl
import requests
from bs4 import BeautifulSoup

class SocialMediaDownloader:
    def __init__(self, download_path: str = "downloads"):
        self.download_path = download_path
        if not os.path.exists(download_path):
            os.makedirs(download_path)
        
        self.insta = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern=None,
            max_connection_attempts=3
        )
        ig_username = os.getenv('INSTAGRAM_USERNAME')
        ig_password = os.getenv('INSTAGRAM_PASSWORD')
        if ig_username and ig_password:
            try:
                self.insta.login(ig_username, ig_password)
                print(f"Successfully authenticated to Instagram as {ig_username}")
            except Exception as e:
                print(f"Instagram authentication error: {str(e)}")
        self.ydl_opts = {
            'format': 'best[height<=720]/best',
            'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 10,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }
        }
        self.tiktok_opts = self.ydl_opts.copy()
        self.tiktok_opts.update({
            'outtmpl': os.path.join(download_path, 'tiktok_%(id)s.%(ext)s'),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Referer': 'https://www.tiktok.com/',
            }
        })

    async def download_youtube(self, url: str) -> Optional[Dict[str, Any]]:
        """Download video from YouTube"""
        try:
            print(f"Starting video download from URL: {url}")
            clean_url = url.split('&')[0]
            print(f"Cleaned URL: {clean_url}")
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                print("Extracting video information...")
                info = ydl.extract_info(clean_url, download=True)
                
                if 'entries' in info:
                    info = info['entries'][0]
                
                filename = ydl.prepare_filename(info)
                
                if not os.path.exists(filename):
                    print(f"File not found: {filename}")
                    return None
                
                result = {
                    'filename': filename,
                    'title': info.get('title', 'Unknown Title'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', None)
                }
                print(f"Download completed successfully: {result['title']}")
                return result
                
        except Exception as e:
            print(f"Error downloading from YouTube: {str(e)}")
            return None

    async def download_tiktok(self, url: str) -> Optional[Dict[str, Any]]:
        """Download video from TikTok using yt-dlp"""
        try:
            print(f"Starting TikTok video download from URL: {url}")
            if 'vt.tiktok.com' in url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, allow_redirects=True) as response:
                        url = str(response.url)
                        print(f"Got full URL: {url}")
            
            with yt_dlp.YoutubeDL(self.tiktok_opts) as ydl:
                print("Extracting video information...")
                info = ydl.extract_info(url, download=True)
                
                filename = ydl.prepare_filename(info)
                
                if not os.path.exists(filename):
                    print(f"File not found: {filename}")
                    return None
                
                result = {
                    'filename': filename,
                    'title': info.get('title', f"TikTok Video {info.get('id', 'Unknown')}"),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', None)
                }
                print(f"Download completed successfully: {result['title']}")
                return result
            
        except Exception as e:
            print(f"Error downloading from TikTok: {str(e)}")
            raise

    async def download_instagram(self, url: str) -> Optional[Dict[str, Any]]:
        """Download content from Instagram (posts, reels, stories)"""
        try:
            print(f"Starting download from Instagram: {url}")
            if '/stories/' in url:
                return await self._download_instagram_story(url)
            elif '/reel/' in url:
                return await self._download_instagram_reel(url)
            else:
                return await self._download_instagram_post(url)
        except instaloader.exceptions.InstaloaderException as e:
            error_msg = str(e)
            if "401" in error_msg:
                raise Exception("Instagram authentication required. Please log in.")
            elif "429" in error_msg:
                raise Exception("Too many requests to Instagram. Please wait a few minutes.")
            else:
                raise Exception(f"Error downloading from Instagram: {error_msg}")
        except Exception as e:
            raise Exception(f"Error downloading from Instagram: {str(e)}")

    async def _download_instagram_story(self, url: str) -> Optional[Dict[str, Any]]:
        """Download story from Instagram"""
        try:
            match = re.search(r'instagram.com/stories/([^/]+)/(\d+)', url)
            if not match:
                raise ValueError("Invalid Instagram story URL format")
            username, story_id = match.groups()
            print(f"Downloading story from user {username}, ID: {story_id}")
            story = self.insta.download_stories([username])
            
            return {
                'type': 'story',
                'username': username,
                'story_id': story_id,
                'download_path': self.download_path
            }
        except Exception as e:
            print(f"Error downloading Instagram story: {str(e)}")
            raise

    async def _download_instagram_reel(self, url: str) -> Optional[Dict[str, Any]]:
        """Download reel from Instagram"""
        try:
            match = re.search(r'instagram.com/reel/([^/]+)', url)
            if not match:
                raise ValueError("Invalid Instagram reel URL format")
            shortcode = match.group(1)
            print(f"Downloading reel with code: {shortcode}")
            post = instaloader.Post.from_shortcode(self.insta.context, shortcode)
            self.insta.download_post(post, target=self.download_path)
            
            return {
                'type': 'reel',
                'shortcode': shortcode,
                'caption': post.caption,
                'likes': post.likes,
                'download_path': self.download_path
            }
        except Exception as e:
            print(f"Error downloading Instagram reel: {str(e)}")
            raise

    async def _download_instagram_post(self, url: str) -> Optional[Dict[str, Any]]:
        """Download post from Instagram"""
        try:
            match = re.search(r'instagram.com/p/([^/]+)', url)
            if not match:
                raise ValueError("Invalid Instagram post URL format")
            shortcode = match.group(1)
            print(f"Downloading post with code: {shortcode}")
            post = instaloader.Post.from_shortcode(self.insta.context, shortcode)
            self.insta.download_post(post, target=self.download_path)
            
            return {
                'type': 'post',
                'shortcode': shortcode,
                'caption': post.caption,
                'likes': post.likes,
                'is_video': post.is_video,
                'download_path': self.download_path
            }
        except Exception as e:
            print(f"Error downloading Instagram post: {str(e)}")
            raise

    def cleanup_old_files(self, max_age_hours: int = 24):
        """Clean up old downloaded files"""
        try:
            current_time = datetime.now()
            for filename in os.listdir(self.download_path):
                file_path = os.path.join(self.download_path, filename)
                if os.path.isfile(file_path):
                    file_age = datetime.fromtimestamp(os.path.getctime(file_path))
                    age_hours = (current_time - file_age).total_seconds() / 3600
                    
                    if age_hours > max_age_hours:
                        os.remove(file_path)
                        print(f"Deleted old file: {filename}")
        except Exception as e:
            print(f"Error cleaning up old files: {str(e)}")
