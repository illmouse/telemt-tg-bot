import os
import requests


class TelemtAPI:
    def __init__(self):
        self.base_url = os.environ["TELEMT_URL"].rstrip("/")
        auth = os.environ.get("TELEMT_AUTH", "")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if auth:
            self.session.headers["Authorization"] = auth

    def _request(self, method, path, **kwargs):
        resp = self.session.request(method, f"{self.base_url}{path}", **kwargs)
        if not resp.ok:
            try:
                body = resp.json()
                err = body.get("error", {})
                msg = f"{resp.status_code} {err.get('code', '')} — {err.get('message', resp.text)}"
            except Exception:
                msg = f"{resp.status_code} — {resp.text}"
            raise RuntimeError(msg)
        return resp.json()["data"]

    def get_users(self) -> list[dict]:
        return self._request("GET", "/v1/users")

    def get_user(self, username: str) -> dict:
        return self._request("GET", f"/v1/users/{username}")

    def create_user(self, username: str) -> dict:
        """Returns CreateUserResponse: {user: UserInfo, secret: str}"""
        return self._request("POST", "/v1/users", json={"username": username, "max_unique_ips": 1})

    def delete_user(self, username: str) -> str:
        return self._request("DELETE", f"/v1/users/{username}")
