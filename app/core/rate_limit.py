try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
except ImportError:  # pragma: no cover
    class Limiter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        def limit(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    def get_remote_address(*args, **kwargs):  # type: ignore[no-redef]
        return "local"


limiter = Limiter(key_func=get_remote_address)
