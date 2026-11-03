"""Simple smoke tests for the Smart Task Manager backend.
Run this after starting the backend at http://127.0.0.1:8000
"""
import sys
import requests

BASE = "http://127.0.0.1:8000"

def check(path, method='get', data=None):
    url = BASE + path
    try:
        if method == 'get':
            r = requests.get(url, timeout=5)
        else:
            r = requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"ERROR: request failed {url}: {e}")
        return False
    ok = r.status_code == 200
    print(f"{r.status_code} {url} -> {ok}")
    if not ok:
        print(r.text)
    return ok

def main():
    tests = [
        ('/', 'get', None),
        ('/tasks', 'get', None),
        ('/notifications', 'get', None),
        ('/devices', 'post', {'device_token': 'smoke-token', 'platform': 'android'}),
        ('/energy-log/today', 'get', None),
    ]

    all_ok = True
    for path, method, data in tests:
        ok = check(path, method, data)
        all_ok = all_ok and ok

    # simple parse-task test (send as query param because backend expects `text` query)
    import urllib.parse
    sample_text = 'เตรียมรายงานส่งวันศุกร์หน้าตอนเย็น'
    ok = check('/parse-task?text=' + urllib.parse.quote(sample_text), 'post', None)
    all_ok = all_ok and ok

    if not all_ok:
        print('One or more smoke tests failed')
        sys.exit(2)
    print('All smoke tests passed')

if __name__ == '__main__':
    main()
