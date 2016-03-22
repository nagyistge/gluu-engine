'''
from .app import create_app
from crochet import setup as crochet_setup

def run_app(app, use_reloader=True):
    crochet_setup()
    app.run(
        host=app.config["HOST"],
        port=int(app.config["PORT"]),
        use_reloader=use_reloader,
    )

if __name__ == '__main__':
    app = create_app()
    run_app(app)
'''

from gluuapi.cli import runserver

if __name__ == "__main__":
    runserver()