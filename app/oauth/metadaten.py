"""Die beiden Discovery-Dokumente, gebaut aus BASE_URL.

An dieser Stelle wird bewusst KEIN Request angefasst. Der Container startet
uvicorn mit --forwarded-allow-ips='*' (siehe docker/app-start.sh), weil
hinter Coolify ein Reverse Proxy sitzt; X-Forwarded-Host und
X-Forwarded-Proto sind damit von aussen setzbar. Wuerde "resource" aus einem
Header entstehen, koennte jeder Aufrufer bestimmen, welche Adresse Claude
fuer die geschuetzte Resource haelt. Die Spec verlangt in Abschnitt 5, dass
"resource" exakt der URL entspricht, die die Lehrerin eingetragen hat - und
das ist BASE_URL.
"""

SCOPE = "lernseiten"
MCP_PFAD = "/mcp"


def resource_url(basis_url: str) -> str:
    """Die Adresse, die die Lehrerin in Cowork eintraegt."""
    return f"{basis_url}{MCP_PFAD}"


def geschuetzte_resource(basis_url: str) -> dict:
    """Das Dokument nach RFC 9728."""
    return {
        "resource": resource_url(basis_url),
        "authorization_servers": [basis_url],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
    }


def autorisierungsserver(basis_url: str) -> dict:
    """Das Dokument nach RFC 8414.

    token_endpoint_auth_methods_supported ist "none": Claude registriert sich
    als oeffentlicher Client und weist sich ueber PKCE aus, nicht ueber ein
    Client-Geheimnis. Ein Geheimnis, das in einer Cloud-Anwendung liegt, waere
    ohnehin keines.
    """
    return {
        "issuer": basis_url,
        "authorization_endpoint": f"{basis_url}/oauth/authorize",
        "token_endpoint": f"{basis_url}/oauth/token",
        "registration_endpoint": f"{basis_url}/oauth/register",
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }
