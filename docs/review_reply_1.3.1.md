Thanks for the review. Version 1.3.1 addresses both points:

**Auto Frame (`_auto_frame_tick`)**: removed completely, including the option, the timer and the code
behind it. You're right that framing should be the animator's decision.

**"sync tools" and timers**: removed. All tools are now registered once in `register()` and unregistered in
`unregister()`; nothing is registered or unregistered later. The per-tool on/off preferences only change
what `poll()` returns (panels hide, operators and shortcuts do nothing) and what the draw callbacks draw.

The add-on now registers no `bpy.app.timers` at all:

- the deferred loading of ghosts saved in a .blend now happens on first use instead of from a timer,
- the "What's New" popup timer is gone (it's a note in the sidebar panel now),
- there is no update check of any kind in the submitted build (no updater module, no network permission).

The only remaining timer-like object is a `window_manager.event_timer_add` owned by the Simplify modal
operator. It exists only while that operator is analysing a large selection and is removed when it finishes or
is cancelled.
