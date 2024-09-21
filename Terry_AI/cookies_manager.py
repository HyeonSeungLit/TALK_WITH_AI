# cookies_manager.py

import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

class CookiesManager:
    def __init__(self):
        self.cookies_file = "cookies.json"
        self.url = 'https://chzzk.naver.com/live/34edb106b3fba99451c269a95a39c49a'
        self.update_interval = 600  # 10분마다 갱신

    def update_cookies(self):
        try:
            options = webdriver.ChromeOptions()
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.get(self.url)
            input("로그인 후 Enter를 눌러주세요...")

            while True:
                cookies = driver.get_cookies()
                nid_aut = next(cookie['value'] for cookie in cookies if cookie['name'] == 'NID_AUT')
                nid_ses = next(cookie['value'] for cookie in cookies if cookie['name'] == 'NID_SES')

                updated_cookies = {
                    "NID_AUT": nid_aut,
                    "NID_SES": nid_ses
                }

                with open(self.cookies_file, "w", encoding='utf-8') as json_file:
                    json.dump(updated_cookies, json_file, indent=4, ensure_ascii=False)

                print("쿠키 갱신 완료!")
                time.sleep(self.update_interval)

        except Exception as e:
            print(f"Failed to update cookies: {e}")

if __name__ == "__main__":
    manager = CookiesManager()
    manager.update_cookies()
