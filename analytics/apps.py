from django.apps import AppConfig

LEAKED_SESSIONS = []


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"

    def ready(self):
        from django.db.backends.base.base import BaseDatabaseWrapper
        from django.db.backends.utils import CursorWrapper

        orig_cursor = BaseDatabaseWrapper.cursor

        def tracked_cursor(self_db, *args, **kwargs):
            cur = orig_cursor(self_db, *args, **kwargs)
            if not hasattr(self_db, "_active_cursors"):
                self_db._active_cursors = set()

            if getattr(self_db, "vendor", "") == "postgresql" and self_db.connection:
                try:
                    if self_db.connection.autocommit:
                        self_db.connection.autocommit = False
                except Exception:
                    pass

            self_db._active_cursors.add(cur)
            return cur

        BaseDatabaseWrapper.cursor = tracked_cursor

        def custom_close(self_wrapper, *args, **kwargs):
            db = getattr(self_wrapper, "db", None)
            if db and hasattr(db, "_active_cursors"):
                db._active_cursors.discard(self_wrapper)
                if not db._active_cursors and getattr(db, "vendor", "") == "postgresql" and db.connection:
                    try:
                        db.connection.commit()
                        db.connection.autocommit = True
                    except Exception:
                        pass
            return self_wrapper.cursor.close(*args, **kwargs)

        CursorWrapper.close = custom_close
