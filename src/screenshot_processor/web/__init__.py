# Web module - imports should be done directly from submodules
# to avoid circular import issues:
#   from screenshot_processor.web.api.main import app
#   from screenshot_processor.web.database import init_db, drop_db
