import os
from app import app
import routes  # noqa: F401

if __name__ == "__main__":
    # Get port from environment for production compatibility
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') != 'production'

    app.run(host="0.0.0.0", port=port, debug=debug)
