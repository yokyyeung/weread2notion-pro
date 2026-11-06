"""Minimal client for Tencent's documented WeRead Agent API (skill 1.0.5)."""

import os
import time

import requests


GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.0.5"


class GatewayError(RuntimeError):
    pass


class GatewayClient:
    def __init__(self):
        key = os.getenv("WEREAD_API_KEY", "").strip()
        if not key:
            raise GatewayError("请在 GitHub Secrets 配置 WEREAD_API_KEY。")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {key}"})

    def request(self, api_name, **parameters):
        payload = {**parameters, "api_name": api_name, "skill_version": SKILL_VERSION}
        for attempt in range(3):
            try:
                response = self.session.post(GATEWAY_URL, json=payload, timeout=30)
            except requests.RequestException:
                if attempt == 2:
                    raise GatewayError(f"微信读书网络请求失败：{api_name}") from None
                time.sleep(5)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    time.sleep(5)
                    continue
            if not response.ok:
                raise GatewayError(f"微信读书请求失败：{api_name}，HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError:
                raise GatewayError(f"微信读书返回了无效 JSON：{api_name}") from None
            if not isinstance(data, dict):
                raise GatewayError(f"微信读书返回结构异常：{api_name}")
            if data.get("upgrade_info"):
                raise GatewayError("微信读书要求升级 skill；请核查官方版本后更新 SKILL_VERSION。")
            code = data.get("errcode", data.get("errCode", 0))
            if code:
                safe_code = code if isinstance(code, int) else "invalid"
                raise GatewayError(f"微信读书请求失败：{api_name}，错误码 {safe_code}")
            return data
