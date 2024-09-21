# run.py

import argparse
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from api import fetch_userIdHash, fetch_chatChannelId

class ChzzkChat:
    def __init__(self, streamer, cookies):
        self.streamer = streamer
        self.cookies = cookies
        self.update_cookies()  # Fetch initial cookies using Selenium
        self.userIdHash = fetch_userIdHash(self.cookies)
        self.chatChannelId = fetch_chatChannelId(self.streamer, self.cookies)
        self.connect()

    def update_cookies(self):
        try:
            options = webdriver.ChromeOptions()
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.get('https://chzzk.naver.com/live/34edb106b3fba99451c269a95a39c49a')

            input("로그인 후 Enter를 눌러주세요...")

            cookies = driver.get_cookies()
            nid_aut = next(cookie['value'] for cookie in cookies if cookie['name'] == 'NID_AUT')
            nid_ses = next(cookie['value'] for cookie in cookies if cookie['name'] == 'NID_SES')

            updated_cookies = {
                "NID_AUT": nid_aut,
                "NID_SES": nid_ses
            }

            with open("cookies.json", "w", encoding='utf-8') as json_file:
                json.dump(updated_cookies, json_file, indent=4, ensure_ascii=False)

            self.cookies = updated_cookies
            driver.quit()
            print("쿠키 갱신 완료!")
        except Exception as e:
            print(f"Failed to update cookies: {e}")

    def connect(self):
        self.chatChannelId = fetch_chatChannelId(self.streamer, self.cookies)
        self.accessToken, self.extraToken = fetch_accessToken(self.chatChannelId, self.cookies)

        self.sock = WebSocket()
        self.sock.connect('wss://kr-ss1.chat.naver.com/chat')
        print(f'{self.channelName} 채팅창에 연결 중 .', end="")

        default_dict = {
            "ver": "2",
            "svcid": "game",
            "cid": self.chatChannelId,
        }

        send_dict = {
            "cmd": CHZZK_CHAT_CMD['connect'],
            "tid": 1,
            "bdy": {
                "uid": self.userIdHash,
                "devType": 2001,
                "accTkn": self.accessToken,
                "auth": "SEND"
            }
        }

        self.sock.send(json.dumps(dict(send_dict, **default_dict)))
        sock_response = json.loads(self.sock.recv())
        self.sid = sock_response['bdy']['sid']
        print(f'\r{self.channelName} 채팅창에 연결 중 ..', end="")

        send_dict = {
            "cmd": CHZZK_CHAT_CMD['request_recent_chat'],
            "tid": 2,
            "sid": self.sid,
            "bdy": {
                "recentMessageCount": 50
            }
        }

        self.sock.send(json.dumps(dict(send_dict, **default_dict)))
        self.sock.recv()
        print(f'\r{self.channelName} 채팅창에 연결 중 ...')

        if self.sock.connected:
            print('연결 완료')
        else:
            raise ValueError('오류 발생')

    def run(self):
        while True:
            try:
                if self.sock.connected:
                    raw_message = self.sock.recv()
                    raw_message = json.loads(raw_message)
                    chat_cmd = raw_message['cmd']

                    if chat_cmd == CHZZK_CHAT_CMD['ping']:
                        self.sock.send(
                            json.dumps({
                                "ver": "2",
                                "cmd": CHZZK_CHAT_CMD['pong']
                            })
                        )
                        if self.chatChannelId != fetch_chatChannelId(self.streamer, self.cookies):
                            self.connect()
                        continue

                    if chat_cmd in [CHZZK_CHAT_CMD['chat'], CHZZK_CHAT_CMD['donation']]:
                        chat_type = '채팅' if chat_cmd == CHZZK_CHAT_CMD['chat'] else '후원'
                        for chat_data in raw_message['bdy']:
                            nickname = '익명의 후원자' if chat_data['uid'] == 'anonymous' else json.loads(chat_data['profile'])["nickname"]
                            message = chat_data.get('msg', '')

                            now = datetime.datetime.fromtimestamp(chat_data['msgTime'] / 1000)
                            now = datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')

                            self.logger.info(f'[{now}][{chat_type}] {nickname} : {message}')
                            self.chatbot.handle_message(nickname, message, "ko", "Chzzk")
                else:
                    print("Socket is not connected, reconnecting...")
                    self.connect()
            except WebSocketConnectionClosedException:
                print("WebSocket connection closed, reconnecting...")
                self.connect()
            except Exception as e:
                print(f"Error during run: {e}")
                pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamer_id', type=str, required=True)
    args = parser.parse_args()

    with open('cookies.json', 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    chzzkchat = ChzzkChat(args.streamer_id, cookies)
    chzzkchat.run()
