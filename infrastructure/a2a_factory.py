import httpx
from a2a.client.client import ClientConfig as A2AClientConfig
from a2a.client.client_factory import ClientFactory as A2AClientFactory
from a2a.types import TransportProtocol as A2ATransport

httpx_client= httpx.AsyncClient(timeout=httpx.Timeout(600.0))

a2a_client_factory=A2AClientFactory(
    config=A2AClientConfig(
        httpx_client=httpx_client,
        streaming=True,
        polling=False,
        supported_transports=[A2ATransport.jsonrpc],
    )
)