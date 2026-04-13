from flask import Flask
from .views import main
from flask_login import LoginManager
from .auth import User

def create_app():
    app = Flask(__name__)
    app.secret_key = 'supersecretkey'
    app.register_blueprint(main)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "main.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User()

    return app