# 2 workers is enough for a low-traffic CMS site; SQLite serializes writes, so more
# processes would only add write contention.
workers = 2
# Threaded workers keep signalling the arbiter while a request runs, so a long AI
# request (the site assistant can take 2+ minutes) isn't killed mid-way, which the
# browser reports as "Failed to fetch".
worker_class = "gthread"
threads = 4
timeout = 300
