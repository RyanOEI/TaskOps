import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:5000')
    host = '127.0.0.1'
    port = 5000
    if ':' in bind:
        parts = bind.split(':', 1)
        host = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            port = 5000
    else:
        host = bind

    app.run(host=host, port=port, debug=True)

