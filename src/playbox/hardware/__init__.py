"""Hardware interfaces (RFID reader, GPIO buttons).

Everything in this package degrades gracefully when the underlying libraries or
devices are unavailable (e.g. on a dev PC): services log a warning and become
no-ops rather than crashing the application.
"""
