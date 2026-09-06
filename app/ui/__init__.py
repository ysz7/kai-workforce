"""The local interface: `kai serve`.

One page on loopback, served from the same process that runs the tasks it shows.
See `app/ui/server.py` for why that is one decision rather than an accident, and
docs/adr/0006 for what follows from it.
"""
