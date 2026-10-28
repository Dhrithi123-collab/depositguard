import json
from fastapi.testclient import TestClient
from backend.app.main import app

def login_user(email, password):
    client = TestClient(app)
    resp = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert resp.status_code == 200
    csrf = resp.json()['csrf_token']
    client.headers.update({'X-CSRF-Token': csrf})
    return client

def main():
    client = TestClient(app)
    # admin login (system admin credentials?) assume default admin created? Not sure.
    # For simplicity, create admin user via auth endpoint? Skip.
    print('Script placeholder')

if __name__ == '__main__':
    main()
