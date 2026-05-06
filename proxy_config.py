# CryptoAI 代理配置說明
# ========================

"""
如果你的 WSL 無法直接連接 Binance API，需要配置代理服務器。

## 步驟 1：確認代理服務器

常見的代理服務器地址格式：
- HTTP 代理：http://127.0.0.1:7890
- SOCKS5 代理：socks5://127.0.0.1:1080
- 遠程代理：http://username:password@proxy-server.com:8080

如果你沒有代理服務器，可以：
1. 使用 Clash、V2Ray 等軟件的局域網模式
2. 購買代理服務（如：青龍、芝麻代理等）
3. 使用免費代理（不穩定，不推薦）

## 步驟 2：配置代理

在 config.yaml 中添加：

```yaml
sentiment:
  enabled: true
  proxy_url: "http://127.0.0.1:7890"  # 替換成你的代理地址
```

或者在 main.py 中初始化時傳入：

```python
from services.sentiment_client import SentimentAnalyzer

analyzer = SentimentAnalyzer(proxy_url="http://127.0.0.1:7890")
```

## 步驟 3：測試代理

運行以下命令測試代理是否可用：

```bash
curl -x http://127.0.0.1:7890 https://fapi.binance.com/fapi/v1/ping
```

如果返回 JSON 數據，表示代理可用。

## 常見代理端口

| 軟件 | 默認端口 | 代理類型 |
|------|---------|---------|
| Clash | 7890 | HTTP |
| V2Ray | 1080 | SOCKS5 |
| Shadowsocks | 1080 | SOCKS5 |
| 青龍面板 | 5701 | HTTP |

## 注意事項

1. 代理地址格式必須正確，包含協議前綴（http:// 或 socks5://）
2. 如果代理需要認證，格式：http://username:password@proxy:port
3. WSL 和 Windows 的代理是共享的，確保 Windows 下的代理已啟用
"""

# 測試代理連接的 Python 腳本
if __name__ == "__main__":
    import asyncio
    from binance.async_client import AsyncClient
    
    async def test_proxy(proxy_url):
        print(f"測試代理：{proxy_url}")
        try:
            client = await AsyncClient.create(https_proxy=proxy_url)
            # 測試連接
            ping = await client.ping()
            print(f"✅ 代理可用！響應：{ping}")
            await client.close_connection()
            return True
        except Exception as e:
            print(f"❌ 代理不可用：{e}")
            return False
    
    # 替換成你的代理地址
    PROXY_URL = "http://127.0.0.1:7890"
    asyncio.run(test_proxy(PROXY_URL))
