import requests
import os


def main():
    base = os.environ.get('SGR_BASE_URL', 'http://127.0.0.1:8000')
    username = os.environ.get('SGR_TEST_USERNAME')
    password = os.environ.get('SGR_TEST_PASSWORD')
    if not username or not password:
        raise RuntimeError(
            'Define SGR_TEST_USERNAME y SGR_TEST_PASSWORD para ejecutar la prueba manual.'
        )
    session = requests.Session()

    session.get(f"{base}/accounts/login/")
    csrf_token = session.cookies.get('csrftoken')
    response = session.post(
        f"{base}/accounts/login/",
        data={
            "username": username,
            "password": password,
            "csrfmiddlewaretoken": csrf_token,
        },
        headers={"Referer": f"{base}/accounts/login/"},
        allow_redirects=False,
    )
    print("Login status:", response.status_code)
    print("Login Location:", response.headers.get('Location'))

    url = f"{base}/dashboard/admin/"
    for index in range(5):
        response = session.get(url, allow_redirects=False)
        location = response.headers.get('Location')
        print(
            f"[{index}] {url} -> status {response.status_code} "
            f"-> Location: {location}"
        )
        if response.status_code != 302:
            break
        url = location if location.startswith('http') else base + location


if __name__ == '__main__':
    main()