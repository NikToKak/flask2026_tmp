import os

class Config:
    SECRET_KEY = 'secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'uploads'
    RESULT_FOLDER = 'results'
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024