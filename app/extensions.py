from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Create unbound extension instances to use with the application factory.
db = SQLAlchemy()
migrate = Migrate()
