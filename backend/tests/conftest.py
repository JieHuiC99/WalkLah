import os
import tempfile

# Tests use a throwaway in-memory database and an operator key (Insights is open when none is set).
os.environ.setdefault("WALKLAH_DB", ":memory:")
os.environ.setdefault("WALKLAH_OPERATOR_KEY", "walklah-test-key")
# Unit tests run on the committed UM graph; the Malaysia database is tested with a synthetic file.
os.environ.setdefault("WALKLAH_MY_DATA", os.path.join(os.path.dirname(__file__), "_no_malaysia_db"))
os.environ.setdefault("WALKLAH_RATE_LIMITS", "off")
os.environ.setdefault("WALKLAH_PHOTOS", os.path.join(tempfile.mkdtemp(prefix="walklah-photos-")))

OPERATOR = {"X-Operator-Key": "walklah-test-key"}
