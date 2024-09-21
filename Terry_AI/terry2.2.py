import argparse
import datetime
import json
import logging
import os
import random
import threading
import time
import io
from collections import deque, defaultdict

import requests
from pydub import AudioSegment
from pydub.playback import play
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from deep_translator import GoogleTranslator
import pytchat
from websocket import WebSocket, WebSocketConnectionClosedException

import ollama
from cmd_type import CHZZK_CHAT_CMD
from api import fetch_userIdHash, fetch_chatChannelId, fetch_channelName, fetch_accessToken

def get_logger():
    formatter = logging.Formatter('%(message)s')
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler('chat.log', mode="w")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger

class ChzzkChat:
    def __init__(self, streamer, cookies, logger, chatbot):
        self.streamer = streamer.rstrip('\\')
        self.cookies = cookies
        self.logger = logger
        self.chatbot = chatbot
        self.sid = None
        self.update_cookies()
        self.userIdHash = fetch_userIdHash(self.cookies)
        self.chatChannelId = fetch_chatChannelId(self.streamer, self.cookies)
        self.channelName = fetch_channelName(self.streamer)
        self.accessToken, self.extraToken = fetch_accessToken(self.chatChannelId, self.cookies)
        self.sock = None
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
        last_chat_time = time.time()
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

                            if message.startswith("!노래"):
                                self.chatbot.sing_song()

                            now = datetime.datetime.fromtimestamp(chat_data['msgTime'] / 1000)
                            now = datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')

                            self.logger.info(f'[{now}][{chat_type}] {nickname} : {message}')
                            self.chatbot.handle_message(nickname, message, "ko", "Chzzk")
                            last_chat_time = time.time()
                else:
                    print("Socket is not connected, reconnecting...")
                    self.connect()

                # 혼잣말 트리거
                if time.time() - last_chat_time > 60:  # 60초 동안 채팅이 없을 때
                    self.chatbot.mutter_to_self()
                    last_chat_time = time.time()

            except WebSocketConnectionClosedException:
                print("WebSocket connection closed, reconnecting...")
                self.connect()
            except Exception as e:
                print(f"Error during run: {e}")
                pass

class ChatBot:
    def __init__(self):
        with open("config.json", "r") as json_file:
            self.config = json.load(json_file)

        self.llama_model = self.config["llama3"]["model"]
        self.system_message = self.config["llama3"]["system_message"]
        self.eleven_labs_config = self.config["eleven_labs"]

        self.conversation_history = deque(maxlen=20)
        self.memory = defaultdict(list)
        self.log_file = open("chat_log.txt", "a", encoding="utf-8")
        self.translator = GoogleTranslator(source='auto', target='ko')
        self.voice_lock = threading.Lock()
        self.music_lock = threading.Lock()
        self.is_playing_music = False
        self.ignore_chat = False
        self.current_emotion = None
        self.last_greeting_time = 0  # 마지막 인사 시간
        self.greeting_done = False  # 인사를 한 번 했는지 여부를 저장
        self.recent_responses = deque(maxlen=5)
        self.last_processed_message = None
        self.greeting_cooldown = 600  # 10분 동안 인사말 무시

    def handle_message(self, author, message, language, platform):
        if self.is_playing_music:
            return

        if self.ignore_chat:
            return

        if message == self.last_processed_message:
            print(f"반복된 메시지: {message}, 무시됨.")
            return

        self.last_processed_message = message
        self.conversation_history.append({"role": "user", "content": f"{author}: {message}"})
        self.save_user_history(author, message)
        user_data = self.load_user_data(author)

        # 인사말인지 여부를 체크하고, 인사말이 중복되는지 판단
        if self.is_greeting(message):
            if self.greeting_done and (time.time() - self.last_greeting_time < self.greeting_cooldown):
                print(f"인사말 중복 감지: {message}, 무시됨.")
                return
            else:
                self.greeting_done = True
                self.last_greeting_time = time.time()
        else:
            # 인사말이 아니므로 질문에 우선 응답
            response = self.generate_response(author, message, platform, language, user_data)
            if response in self.recent_responses:
                print(f"중복된 응답 발견: {response}")
                return
            self.recent_responses.append(response)

            if self.should_continue_speaking(response):
                continuation = self.generate_continuation()
                response += " " + continuation

            print(f"Terry: {response}")
            self.log_chat(f"Terry: {response}")
            self.play_response(response, language)

    def is_greeting(self, message):
        """메시지가 인사말인지 판단하는 함수."""
        greetings = ["안녕하세요", "환영합니다", "사랑스러운 시청자"]
        return any(greeting in message for greeting in greetings)

    def generate_response(self, author, message, platform, language, user_data):
        # 대화 생성 로직
        messages = [{"role": "system", "content": self.system_message}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": f"User data: {user_data}"})

        response_variants = [
            {"role": "user", "content": f"{author}: {message}"},
            {"role": "user", "content": f"{author} asked about: {message}"},
            {"role": "user", "content": f"{message} - asked by {author}"}
        ]

        messages.extend(response_variants)

        response = ollama.chat(model=self.llama_model, messages=messages)
        response_text = response['message']['content']

        response_text = self.ensure_complete_response(response_text)
        response_text = self.recall_memory(message, response_text)
        if language == 'ko':
            response_text = self.translator.translate(response_text)

        return response_text

    def ensure_complete_response(self, response_text):
        """
        응답이 중간에 멈추지 않고 자연스럽게 이어질 수 있도록 보장하는 함수.
        """
        incomplete_indicators = ["...", "그런데", "그리고", "그래서", "아마도", "어쩌면"]  # 문장이 중단될 가능성이 있는 패턴들
        if response_text.strip().endswith(tuple(incomplete_indicators)) or len(response_text.split()) < 5:
            response_text += " 제가 더 이야기할게 있어요. 어떤 이야기를 계속 할까요?"
        return response_text

    def should_continue_speaking(self, response):
        # 응답이 충분히 길지 않거나, 맥락상 더 말할 여지가 있을 경우 True 반환
        if len(response.split()) < 10 or response.endswith(("그런데", "그리고", "그래서")):
            return True
        return False

    def generate_continuation(self):
        # 추가적인 대화를 생성
        continuations = [
            "그럼 다음에 대해 더 이야기해볼까요?",
            "이 주제에 대해 더 알고 싶으신가요?",
            "그럼, 계속해서 이야기해볼게요.",
            "이 부분이 흥미롭네요, 좀 더 이야기해보죠."
        ]
        return random.choice(continuations)

    def recall_memory(self, message, response_text):
        """기억을 더 효과적으로 사용하여 반복되지 않도록 함."""
        if any(topic in message for topic in self.memory):
            for topic, messages in self.memory.items():
                if topic in message:
                    if len(messages) > 0:
                        response_text += f" 예전에 {topic}에 대해 이런 대화를 했었죠: {random.choice(messages)}"
                    break
        return response_text

    def fetch_youtube_chat(self, video_id):
        try:
            print(f"Fetching YouTube chat for video ID: {video_id}")
            chat = pytchat.create(video_id=video_id)
            while chat.is_alive():
                for c in chat.get().sync_items():
                    print(f"{c.datetime} [{c.author.name}]: {c.message}")
                    self.log_chat(f"{c.datetime} [{c.author.name}]: {c.message}")
                    message_language = self.detect_language(c.message)
                    self.handle_message(c.author.name, c.message, message_language, "YouTube")
        except pytchat.exceptions.InvalidVideoIdException as e:
            print(f"Invalid video id: {video_id}")
        except Exception as e:
            print(f"Error fetching YouTube chat: {e}")

    def detect_language(self, text):
        try:
            return detect(text)
        except:
            return 'unknown'

    def filter_response(self, response):
        response = response.replace("여보", "").replace("고백", "").strip()
        return response

    def shorten_response(self, response):
        max_length = 150  # 최대 응답 길이
        if (len(response)) > max_length:
            response = response[:max_length] + "..."
        return response

    def play_response(self, message, language):
        with self.voice_lock:
            url = f'https://api.elevenlabs.io/v1/text-to-speech/{self.eleven_labs_config["voice_id"]}'
            headers = {
                'accept': 'audio/mpeg',
                'xi-api-key': self.eleven_labs_config["api_key"],
                'Content-Type': 'application/json'
            }
            data = {
                'text': message,
                'model_id': self.eleven_labs_config["model_id"],
                'voice_settings': self.eleven_labs_config["voice_settings"]
            }
            response = requests.post(url, headers=headers, json=data, stream=True)
            audio_content = AudioSegment.from_file(io.BytesIO(response.content), format="mp3")
            play(audio_content)

    def mutter_to_self(self):
        self_thoughts = [
            "아무도 말을 안 걸어주네... 그냥 혼잣말이나 해야겠다.",
            "지금 무슨 생각을 하고 있었더라... 아, 맞아!",
            "이 게임은 언제 해도 정말 재밌어.",
            "음, 뭐 재미있는 일이 없을까?",
            "테리야, 넌 정말 대단해! (혼잣말)"
        ]
        random_thought = random.choice(self_thoughts)
        print(f"Terry 혼잣말: {random_thought}")
        self.log_chat(f"Terry 혼잣말: {random_thought}")
        self.play_response(random_thought, "ko")

    def save_user_history(self, author, message):
        filename = f"user_data/{author}_history.txt"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "a", encoding="utf-8") as file:
            file.write(f"{datetime.datetime.now()}: {message}\n")

    def load_user_data(self, author):
        filename = f"user_data/{author}_history.txt"
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                return file.read()
        return ""

    def log_chat(self, message):
        self.log_file.write(message + "\n")
        self.log_file.flush()

def fetch_youtube_chat_main_thread(video_id, chatbot):
    chatbot.fetch_youtube_chat(video_id)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamer_id', type=str, required=True)
    parser.add_argument('--video_id', type=str, required=True)
    args = parser.parse_args()

    with open('cookies.json', 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    logger = get_logger()
    chatbot = ChatBot()
    chzzkchat = ChzzkChat(args.streamer_id, cookies, logger, chatbot)
    threading.Thread(target=chzzkchat.run).start()
    fetch_youtube_chat_main_thread(args.video_id, chatbot)

    # 프로그램이 종료되지 않도록 유지하는 루프
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("프로그램이 종료되었습니다.")
