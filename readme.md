# Pimoroni Google Calendar Plugin

Plugin for the Pimoroni display-o-tron-3000 to display Google Calendar Events.

Features:

* Clock
* Displays the next 9 events from your calendar, including ones that have started but not finished. Use the buttons to scroll through them
* Shows time until each event
* Backlight colour changes from green to red as an event draws closer (starting at 5 hours)
* Auto screensaver with configurable timeout
* Activity ticker using the graph LEDs even if the screen is off
* Auto-reloads the calendar when an event finishes (or can manual refresh with select button)
* If an event has a 'pop up' reminder, it will flash the graph LEDs during the reminder period, though you can't 'dismiss' the reminder.
* If an event has started but not finished, it shows time remaining until the event ends

Script definitely runs as a standalone, and should work as an external module, though I've not tested that. You will need to get a Google API key for your application, and to go through the OAuth setup process at least once.

I'm pretty sure most of the bugs have been eliminated now, but I'm pretty new to python, so there might be some I've missed.


