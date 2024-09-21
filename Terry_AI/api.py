# api.py

import requests
import json

# 쿠키 파일을 읽어오는 함수
def load_cookies():
    with open('cookies.json', 'r', encoding='utf-8') as f:
        cookies = json.load(f)
    return cookies

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def fetch_chatChannelId(streamer: str, cookies: dict) -> str:
    url = f'https://api.chzzk.naver.com/polling/v2/channels/{streamer}/live-status'
    try:
        response = requests.get(url, cookies=cookies, headers=HEADERS)
        response.raise_for_status()
        response = response.json()
        chatChannelId = response['content']['chatChannelId']
        assert chatChannelId is not None
        return chatChannelId
    except Exception as e:
        print(f"Error fetching chatChannelId: {e}")
        raise e

def fetch_channelName(streamer: str) -> str:
    url = f'https://api.chzzk.naver.com/service/v1/channels/{streamer}'
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        response = response.json()
        return response['content']['channelName']
    except Exception as e:
        print(f"Error fetching channelName: {e}")
        raise e

def fetch_accessToken(chatChannelId, cookies: dict) -> str:
    url = f'https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chatChannelId}&chatType=STREAMING'
    try:
        response = requests.get(url, cookies=cookies, headers=HEADERS)
        response.raise_for_status()
        response = response.json()
        return response['content']['accessToken'], response['content']['extraToken']
    except Exception as e:
        print(f"Error fetching accessToken: {e}")
        raise e

def fetch_userIdHash(cookies: dict) -> str:
    url = 'https://comm-api.game.naver.com/nng_main/v1/user/getUserStatus'
    try:
        response = requests.get(url, cookies=cookies, headers=HEADERS)
        response.raise_for_status()
        response = response.json()
        return response['content']['userIdHash']
    except Exception as e:
        print(f"Error fetching userIdHash: {e}")
        raise e
