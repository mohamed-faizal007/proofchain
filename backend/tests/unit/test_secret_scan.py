"""P10-01: scripts/secret_scan.py catches this project's real secret shapes.

Planted secrets are assembled at runtime so this file itself never contains a literal that
the scanner (run over the whole repo in CI) would flag.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "secret_scan.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("secret_scan", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["secret_scan"] = mod
    spec.loader.exec_module(mod)
    return mod


scan = _load()

# realistic, non-placeholder values (built from parts)
PRIVATE_KEY = "0x" + "4c0883a69102937d6231471b5dbb6204fe512961708279f2" + "3a1b9c2d5e7f8091"
ALCHEMY_KEY = "vJ3k9" + "XzQ2mL7pR4tY8wB1nC6dF0gH5sAe"
INFURA_ID = "9aa3d95b3bc440fa" + "88ea12eaa4456161"
ETHERSCAN_KEY = "QX7M2" + "PD9KJ4HFV8RT3WZ6NC1BYA5SGLE4U"
AWS_KEY_ID = "AKIA" + "Z3MZ7XQ4WJ5R2TLP"
GENERIC_VALUE = "k8Jd93LmQp" + "27XvTz51RbNw04YhCaUe6S"


def findings(text: str, name: str = "src/config.py") -> list[str]:
    return [f.rule for f in scan.scan_text(name, text)]


def test_private_key_assigned_with_0x_prefix() -> None:
    assert findings(f"ANCHOR_PRIVATE_KEY={PRIVATE_KEY}\n") == ["eth-private-key"]


def test_private_key_assigned_without_prefix_and_in_quotes() -> None:
    assert "eth-private-key" in findings(f'DEPLOYER_PRIVATE_KEY = "{PRIVATE_KEY[2:]}"')


def test_private_key_bare_on_a_line_that_says_it_is_a_private_key() -> None:
    assert "eth-private-key" in findings(f"// wallet private key: {PRIVATE_KEY}")


def test_transaction_hash_is_not_a_private_key() -> None:
    assert findings(f"anchored in tx {PRIVATE_KEY} at block 42") == []
    assert findings(f'"txHash": "{PRIVATE_KEY}"') == []


def test_hardhat_well_known_dev_key_is_allowed() -> None:
    dev = "0x" + "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    assert findings(f"ANCHOR_PRIVATE_KEY={dev}") == []


def test_obvious_placeholder_key_is_allowed() -> None:
    assert findings("anchor_private_key='0x' + '1' * 64") == []
    assert findings("ANCHOR_PRIVATE_KEY=0x" + "1" * 64) == []


def test_alchemy_key_in_rpc_url() -> None:
    url = f"https://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_KEY}"
    assert findings(f"SEPOLIA_RPC_URL={url}") == ["rpc-provider-key"]


def test_infura_project_id_in_rpc_url() -> None:
    url = f"https://sepolia.infura.io/v3/{INFURA_ID}"
    assert "rpc-provider-key" in findings(f"const rpc = '{url}'")


def test_etherscan_key_assigned() -> None:
    assert "etherscan-key" in findings(f"ETHERSCAN_API_KEY={ETHERSCAN_KEY}")


def test_etherscan_key_in_query_string() -> None:
    url = f"https://api.etherscan.io/api?module=account&apikey={ETHERSCAN_KEY}"
    # one finding per value: the query-string rule and the etherscan rule both match it
    assert set(findings(url)) & {"etherscan-key", "url-api-key"}


def test_aws_access_key_id() -> None:
    assert findings(f"aws_access_key_id = {AWS_KEY_ID}") == ["aws-access-key-id"]


def test_aws_documentation_example_key_is_allowed() -> None:
    assert findings("AKIAIOSFODNN7EXAMPLE") == []


@pytest.mark.parametrize("name", ["API_KEY", "JWT_SECRET", "SLACK_TOKEN", "db_password"])
def test_generic_long_value_on_key_secret_token_variable(name: str) -> None:
    # one finding per value; API_KEY is claimed by the more specific etherscan rule
    assert findings(f"{name}={GENERIC_VALUE}")
    assert findings(f'{name}: "{GENERIC_VALUE}"')
    if name != "API_KEY":
        assert findings(f"{name}={GENERIC_VALUE}") == ["generic-secret"]


def test_generic_rule_ignores_short_values_and_unrelated_names() -> None:
    assert findings("JWT_SECRET=short") == []
    assert findings(f"FILE_NAME={GENERIC_VALUE}") == []
    assert findings("AWS_SECRET_ACCESS_KEY=minioadmin") == []


def test_generic_rule_ignores_code_that_names_a_secret_without_a_value() -> None:
    assert findings("jwt_secret: str = DEFAULT_JWT_SECRET") == []
    assert findings("const token = localStorage.getItem('proofchain.token_value_key')") == []


def test_findings_never_contain_the_secret_itself() -> None:
    (f,) = scan.scan_text("a.env", f"ANCHOR_PRIVATE_KEY={PRIVATE_KEY}")
    assert PRIVATE_KEY not in f.preview and PRIVATE_KEY[2:] not in f.preview
    assert f.line == 1 and f.path == "a.env"


def test_inline_allow_marker_suppresses_a_finding() -> None:
    assert findings(f"API_KEY={GENERIC_VALUE}  # secret-scan: allow") == []


def test_tracked_dotenv_file_is_itself_a_finding() -> None:
    assert [f.rule for f in scan.scan_paths_by_name([".env", "backend/.env.local"])] == [
        "dotenv-file-tracked",
        "dotenv-file-tracked",
    ]
    assert scan.scan_paths_by_name([".env.example", "infra/.env.example"]) == []


# --- the project's own files ----------------------------------------------------------------


def test_env_example_placeholders_do_not_false_positive() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert scan.scan_text(".env.example", text) == []


def test_cli_exits_nonzero_on_a_planted_secret_and_zero_on_clean_input(tmp_path: Path) -> None:
    (tmp_path / "ok.txt").write_text("nothing to see\n")
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--no-git"],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    (tmp_path / "leak.env.txt").write_text(f"ETHERSCAN_API_KEY={ETHERSCAN_KEY}\n")
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--no-git"],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1
    assert "etherscan-key" in bad.stdout and ETHERSCAN_KEY not in bad.stdout


# --- review follow-ups: shapes the first version missed -------------------------------------

HEX64 = "4c0883a69102937d6231471b5dbb6204fe512961708279f2" + "3a1b9c2d5e7f8091"


@pytest.mark.parametrize("name", ["DEPLOYER_PK", "pk", "SIGNER_KEY_HEX", "WALLET_KEY", "DEPLOYER"])
def test_private_key_under_other_common_variable_names(name: str) -> None:
    assert "eth-private-key" in findings(f"{name}=0x{HEX64}")


def test_pem_private_key_header() -> None:
    for kind in ("RSA ", "EC ", "OPENSSH ", ""):
        assert findings("-----BEGIN " + kind + "PRIVATE KEY-----") == ["pem-private-key"]
    assert findings("-----BEGIN PUBLIC KEY-----") == []


def test_mnemonic_seed_phrase() -> None:
    words = "legal winner thank year wave sausage worth useful legal winner thank yellow"
    assert findings(f'MNEMONIC="{words}"') == ["seed-phrase"]
    assert findings("MNEMONIC=") == []
    assert findings("mnemonic: the hardhat default test junk phrase") == []


def test_websocket_rpc_url_and_query_string_key() -> None:
    assert "rpc-provider-key" in findings(f"wss://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_KEY}")
    assert "url-api-key" in findings(f"https://node.provider.net/rpc?apikey={ALCHEMY_KEY}")


def test_etherscan_key_without_digits_is_still_flagged() -> None:
    assert "etherscan-key" in findings("ETHERSCAN_API_KEY=" + "QXMPDKJHFVRTWZNCBYASGLEUQXMPDKJHFV")


def test_shorter_value_on_secret_or_password_name() -> None:
    assert "generic-secret" in findings("S3_SECRET_KEY=" + "Xk29sLq8" + "1mZpQw73")
    assert findings("SECRET_PHRASE_LABEL=abc") == []


def test_vendor_token_prefixes() -> None:
    assert "vendor-token" in findings("x = " + "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8")
    assert "vendor-token" in findings("sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc")
    assert "vendor-token" in findings("xoxb-" + "123456789012-abcdefghijklmnop")
    assert "vendor-token" in findings("sk-ant-api03-" + "Zk29sLq81mZpQw73Zk29sLq81mZpQw73")
