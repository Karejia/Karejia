# 強制 aiohttp 使用 IPv4
import aiohttp
import socket

class IPv4OnlyConnector(aiohttp.TCPConnector):
    async def _resolve_host(self, host, port, traces=None):
        # 只返回 IPv4 地址
        hosts = await super()._resolve_host(host, port, traces)
        return [h for h in hosts if h['family'] == socket.AF_INET]

# 使用方式：
# connector = IPv4OnlyConnector()
# session = aiohttp.ClientSession(connector=connector)
