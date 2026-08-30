from xrpl.clients import JsonRpcClient

from app.config import get_settings


def get_xrpl_client() -> JsonRpcClient:
    """A fresh client per call - xrpl-py's JsonRpcClient is a thin,
    stateless HTTP wrapper, so there's no connection to pool or reuse."""
    return JsonRpcClient(get_settings().xrpl_json_rpc_url)
