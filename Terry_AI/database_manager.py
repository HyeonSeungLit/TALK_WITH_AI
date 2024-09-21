import json
import os

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            self.init_database()

    def init_database(self):
        with open(self.db_path, 'w') as db_file:
            json.dump({}, db_file)

    def load_data(self):
        with open(self.db_path, 'r') as db_file:
            return json.load(db_file)

    def save_data(self, data):
        with open(self.db_path, 'w') as db_file:
            json.dump(data, db_file, indent=4)

    def get_user_data(self, user_id):
        data = self.load_data()
        return data.get(user_id, {})

    def save_user_data(self, user_id, user_data):
        data = self.load_data()
        data[user_id] = user_data
        self.save_data(data)
