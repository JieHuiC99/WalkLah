import os

# Tests use a throwaway in-memory database and the demo operator key.
os.environ.setdefault("WALKLAH_DB", ":memory:")
os.environ.setdefault("WALKLAH_OPERATOR_KEY", "walklah-demo")

OPERATOR = {"X-Operator-Key": "walklah-demo"}
