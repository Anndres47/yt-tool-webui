from flask_login import UserMixin

class User(UserMixin):
    def __init__(self):
        self.id = "admin"

    def get_id(self):
        return self.id