from __future__ import print_function
import httplib2
import os
import rfc3339
import time
import datetime
import time
import oauth2client
import atexit
import thread
import pytz
import tzlocal

from apiclient import discovery
from oauth2client import client
from oauth2client import tools

# Change these to dot3k if using that :)
import dothat.touch as touch
import dothat.backlight as backlight
import dothat.lcd as lcd
from dot3k.menu import Menu
from dot3k.menu import MenuOption

"""
Pimoroni DOTHat/Dot3k Google Calendar Menu Plugin

Code to fetch Calendar Events Based on 
  https://developers.google.com/google-apps/calendar/quickstart/python

Follow the instructions above to install the Google Apps libraries
and to create an API key for your copy of the module and to authorise
it to access your calendar.
  
"""

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Google Calendar API Python Quickstart'

def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    try:
        import argparse
        flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
    except ImportError:
        flags = None

    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'calendar-python-quickstart.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials



class GoogleCalendar(MenuOption):
    def __init__(self):
        """
        Initialise a few values that we use to track stuff
          d_event : displayed event in the list of results. Default to first one
          c_event : I set this to 99 so that first menu redraw processes the events
          last_update : Set to the minute within the hour that we last calculated event timers
          idletimer : use epoch seconds for this. Time of last button press.
          idletimeout : how long before the screensaver kicks in
          calendarid : ID of the calendar being used. Theoretically, you can write code to alter this
                       and change the active calendar if you want. I haven't.
          nextrefresh : datetime container for the soonest event finish

        We also define an arrow character and set it as \x01. I've noticed at least
        one case where the character has corrupted, so we'll redefine it each time we use it.
        Finally, we call UpdateCalendar to pull down some events from our calendar
        """
        self.clockanim = [[
                  0b00000,
                  0b01100,
                  0b01100,
                  0b00000,
                  0b01100,
                  0b01100,
                  0b00000,
                  0b00000
                  ],[
                  0b00000,
                  0b00000,
                  0b00000,
                  0b00000,
                  0b01100,
                  0b01100,
                  0b00000,
                  0b00000
                  ]
        ]
        self.arrow = [
                  0b00000,
                  0b00100,
                  0b00110,
                  0b11111,
                  0b11111,
                  0b00110,
                  0b00100,
                  0b00000
        ]
        self.reminders=[]
        self.localtz = tzlocal.get_localzone()
        self.nextrefresh = datetime.datetime.max
        self.nextrefresh = self.nextrefresh.replace(tzinfo=self.localtz)
        self.updating_calendar = 0
        self.d_event = 0
        self.c_event = 99
        self.screensave = 0
        self.last_update = datetime.datetime.now().minute
        self.idletimer = time.time()
        self.idletimeout = 90
        self.maxevents = 9
        # Default this to the primary (account's main) calendar
        self.calendarid = 'primary'
        # REMOVE THIS LINE BEFORE PUBLISHING!
        self.calendarid = 'd9me3pebd5rcgd8kq1l9pjlqao@group.calendar.google.com'
        # Default Backlight Colours when not doing R->G transition. Set to taste.
        self.defaultR = 0
        self.defaultG = 0
        self.defaultB = 255
        # Set the screen to the default colours above. And save those values as
        # the current colours too.
        self.SetRGB(self.defaultR, self.defaultG, self.defaultB)
        self.UpdateCalendar()
        MenuOption.__init__(self) 

    def left(self):
        """
        Increment the currently displayed event. Wrap at 8, letting us cycle through 9 events (0-8)
        Update the clock to confirm a button's been pressed
        If screensave is active, set the values to deactivate it and don't process the button
        This gives us 'tap to wake up'
        """
        if (self.screensave == 1):
            self.idletimer=time.time()
            self.screensave=2
            return True
        self.d_event=self.d_event - 1
        if (self.d_event < 0):
            self.d_event=(self.maxevents)
        return True

    def right(self):
        """
        Decrement the currently displayed event. Wrap at 0, letting us cycle through 9 events (0-8)
        Update the clock to confirm a button's been pressed.
        If screensave is active, set the values to deactivate it and don't process the button
        This gives us 'tap to wake up'
        """
        if (self.screensave == 1):
            self.idletimer=time.time()
            self.screensave=2
            return True
        self.d_event=self.d_event + 1
        if (self.d_event > self.maxevents):
          self.d_event=0
          return True

    def BgUpdateCalendar(self):
        """
        Slightly less sophisticated version of select() below. Designed to be called
        when we need to update the calendar within the main code path. I launch this 
        one in a thread, so that we don't freeze the main display codepath, although 
        I guess that if this function fails, the script will get stuck displaying 
        "Updating Calendar" anyway.
        """
        # Crude locking to ensure we don't call the gApps update code more than once
        if (self.updating_calendar == 1):
            return False
        self.updating_calendar = 1
        self.UpdateCalendar()
        time.sleep(2)
        self.updating_calendar = 0
        return False

    def select(self):
        """
        For now, make the middle button force a refresh of the calendar.
        Mostly, this should happen pretty quickly, but we add a 2 second delay
        so that the user has time to see that the calendar refresh is happening :).
        Ideally, we'd time the update and only delay further if it wasn't slow, but 
        maybe later.
        """
        if (self.updating_calendar == 1):
            return False 
        if (self.screensave == 1):
            self.idletimer=time.time()
            self.screensave=2
            return False
        self.updating_calendar = 1
        self.UpdateCalendar()
        time.sleep(2)
        self.idletimer=time.time()
        self.updating_calendar = 0
        return False

    def SetRGB(self, red, green, blue):
        """
        Helper function to set the RGB values. Save the RGB values to a state variable 
        and then call the backlight update function. This way, we know the previous backlight
        colour and when we turn the screen back on, we can set the colour as planned.
        """
        self.red = red
        self.green = green
        self.blue = blue
        backlight.rgb(self.red, self.green, self.blue)

    def UpdateCalendar(self):
        """
        Establish an API OAuth connection to google calendar and retrieve the next 10 events by
        end date/time. Clear the screen and make it show a message to say what's happenining.
        Mostly, this is taken from the google apps demo code :-)
        TODO: Handle HTTP/API errors more gracefully. For now, catch exceptions, return an
        empty list, and set a 5 minute retry interval.
        """
      
        credentials = get_credentials()
        http = credentials.authorize(httplib2.Http())
        service = discovery.build('calendar', 'v3', http=http)

        #now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        now = "2016-03-27T00:45:00Z"

        # Just in case this throws a HTTP exception or something
        try:
            eventsResult = service.events().list(
                calendarId=self.calendarid, timeMin=now, maxResults=11, singleEvents=True,
                orderBy='startTime').execute()
            self.events = eventsResult.get('items', [])
        except:
            self.events=[]

        # if you don't want to refresh immediately after an event finishes uncomment this:
        # self.nextrefresh = self.nextrefresh + datetime.timedelta(minutes=5)
        if not self.events:
            self.maxevents = 0
            self.nextrefresh = datetime.datetime.now(self.localtz) + datetime.timedelta(minutes=5)
            return

        # Let's deal with the API returning fewer results than expected
        if ((len(self.events) > 9)):
            self.maxevents = 8
        else:
            # Subtract one because the index is zero based
            self.maxevents = (len(self.events) - 1)

        # Initialise nextrefresh to the latest possible date allowed by Python.
        self.nextrefresh=datetime.datetime.max
        self.nextrefresh=self.nextrefresh.replace(tzinfo=self.localtz)

        # Calculate start / end times and store them in datetime objects in the event dictionary
        # If the event only has a date property, it's an all day event, so append T00:00:00Z to
        # make it midnight instead.
        for event in self.events:
            print (event)
            if (event['start'].get('date')):   
                event['estart_dt']=rfc3339.parse_datetime(event['start'].get('date') + "T00:00:00Z")
                event['estart_dt']=event['estart_dt'].replace(tzinfo=None)
                event['estart_dt']=self.localtz.localize(event['estart_dt'])
            else:
                event['estart_dt']=rfc3339.parse_datetime(event['start'].get('dateTime'))
            if (event['end'].get('date')):  
                event['eend_dt']=rfc3339.parse_datetime(event['end'].get('date') + "T00:00:00Z")
                event['eend_dt']=event['eend_dt'].replace(tzinfo=None)
                event['eend_dt']=self.localtz.localize(event['eend_dt'])
                event['allday_flag']=True
            else:
                event['eend_dt']=rfc3339.parse_datetime(event['end'].get('dateTime'))
                event['allday_flag']=False
            
            print (event['eend_dt'])
            print (event['estart_dt'])


            # Replace the timezones with None to make them suitable for subtracting datetime.now
            # We've ignored the timezones provided by google, so everything should be UTC based.
            # The tzinfo attached when parsed seems to be +00:00 anyway.
            # TODO: Check behaviour with events crossing DST boundaries

            print (event['eend_dt'].astimezone(self.localtz))
            print (event['estart_dt'].astimezone(self.localtz))

            # If this event finishes earlier than the current assigned date, update it
            # At the end of the loop, we'll have the closest event end date. We use this
            # to kick off a calendar refresh automatically after the event finishes.
            if(event['eend_dt'] < self.nextrefresh):
                self.nextrefresh=event['eend_dt']

            # Event.reminders.overrides is a list of dictionaries. Loop this to look for popup reminders
            # then make a list of dictionaries with start/end datetime objects. 
            # Start times are when we need to turn on the reminder lights, end times we turn off.
            if event['reminders'].get('overrides'):
                tempevent = {}
                for items in event['reminders'].get('overrides'):
                    if (items.get('method') == 'popup'):
                        tempevent['start'] = (event['estart_dt'] - 
                            datetime.timedelta(minutes=items.get('minutes')) )
                        tempevent['end'] = event['estart_dt'] 
                        self.reminders.append(tempevent)




        # Whenever we've re-read the calendar, display from the first event.
        self.d_event=0
        self.c_event=99

    def CalculateGraph(self, reminderactive):
        """ 

        Takes a single parameter that says whether a reminder is active or not.
        Based on this, return a list of 6 states that are written to the graph LEDs
        each redraw cycle.

        This way, you can cleanly do what you want with the graph either as a reminder
        alert or when idle. Sample code here cycles through the LEDs one per second whether
        the screen is on or off, and in reminder mode alternates the top 3 and the bottom 3.

        Other ideas, you could make the LEDs count the seconds in binary, or do an up/down
        sweep. Or even set it to turn them off completely when the screensaver is active.
        
        """
        graph=[0,0,0,0,0,0]
        if (reminderactive == 0):
            graph[(int(time.time() % 6))]=1
        else:
            if (int((time.time()*3) % 2)==0):
                graph=[1,1,1,0,0,0]
            else:
                graph=[0,0,0,1,1,1]
        return graph

    def redraw(self, menu):
        """
          The output to the LCD looks as follows

          |Mon 01 Jan 16:35| |Mon 01 Jan 16.35|
          |[1] Now 0d7h25m | |[1] In 04d5h25m |
          |Event descriptio| |Event descriptio|

          Line 1: constantly updating clock. Time seperator blinks between : and .
          Line 2: Event number in square brackets
                  Ongoing events show "Now", an arrow and time to end of event.
                  Upcoming events show "In", and a countdown to start of event.
          Line 3: Event description. "All Day:" is appended if it's an all day event.
                  Will scroll if the line doesn't fully fit on the screen.
        """

        # Start by seeing if we need to be in a reminder state
        reminderactive=0
        for reminder in self.reminders:
            timenow=datetime.datetime.now(self.localtz)
            if (timenow > reminder['start'] and timenow < reminder['end']):
                reminderactive=1

        # Decide what to do with the graph LEDs and set them 
        graphstates = self.CalculateGraph(reminderactive)
        for x in range(6):
          backlight.graph_set_led_state(x,graphstates[x])

        # If it's time for a refresh because an event's ended, do a background refresh
        if (datetime.datetime.now(self.localtz) > self.nextrefresh):
            thread.start_new_thread(self.BgUpdateCalendar,())
            return

        # If maxevents is zero, we have no events due to an error or an empty calendar
        if (self.maxevents == 0):
            menu.write_option(
                row=0,
                text="No events!",
                scroll=False
            )
            menu.write_option(
                row=1,
                text="Rechecking at",
                scroll=False
            )
            menu.write_option(
                row=2,
                text=str(self.nextrefresh.time().replace(microsecond=0)),
                scroll=False
            )
            return

        # If there's a calendar update happening, say so and do nothing else.
        if (self.updating_calendar == 1):
            menu.write_option(
                row=0,
                text="Please Wait",
                scroll=False
            )
            menu.write_option(
                row=1,
                text="Updating",
                scroll=False
            )
            menu.write_option(
                row=2,
                text="Calendar",
                scroll=False
            )
            return


        # Do nothing if the screen is turned off
        if (self.screensave == 1):
            return

        # If the idle timer has been reached, turn the screen off 
        if ((time.time() - self.idletimer) > self.idletimeout):
            lcd.clear()
            self.screensave = 1
            backlight.rgb(0,0,0)
            return

        # A screensave state of 2 means we need to activate the screen/
        # Restore the backlight to the last saved RGB values.
        if (self.screensave == 2):
            backlight.rgb(self.red,self.green,self.blue)

        # Either the displayed event has been changed, or the time has moved on a minute
        # In both cases, we need to recalculate the countdown strings
        if ((self.d_event != self.c_event) or (datetime.datetime.now().minute != self.last_update)):

            # Create timediff items so we can see when the start and finish are relative to now
            self.timetoevent=self.events[self.d_event]['estart_dt'] - datetime.datetime.now(self.localtz)
            self.timetoend=self.events[self.d_event]['eend_dt'] - datetime.datetime.now(self.localtz)

            print ('Handling event data:')
            print ('estart_dt',self.events[self.d_event]['estart_dt'])
            print ('eend_dt', self.events[self.d_event]['eend_dt'])
            print ('dt_now', datetime.datetime.now(self.localtz))
            print (self.timetoevent)
            print (self.timetoend)

            # Calculate days/hours/mins remaining till event start
            self.tte_days = self.timetoevent.days
            self.tte_secs = self.timetoevent.seconds
            self.tte_hours = (self.tte_secs // 3600)
            # +1 minute because we're not counting seconds
            self.tte_mins = ((self.tte_secs % 3600) // 60) + 1
            # Though this does introduce a kettle of worms that 1h60m is a possible result.
            if (self.tte_mins == 60):
                self.tte_hours = self.tte_hours + 1
                self.tte_mins = 0
  
            # Calculate days/hours/mins remaining till event finish
            self.ttee_days = self.timetoend.days
            self.ttee_secs = self.timetoend.seconds
            self.ttee_hours = (self.ttee_secs // 3600)
            print('ttee_hours', self.ttee_hours)
            # +1 minute because we're not counting seconds
            self.ttee_mins = ((self.ttee_secs % 3600) // 60) + 1
            print('ttee_mins', self.ttee_mins)
            # Though this does introduce a kettle of worms that 1h60m is a possible result.
            if (self.ttee_mins == 60):
              self.ttee_hours = self.ttee_hours + 1
              self.ttee_mins = 0
            print('after minute fudge')
            print('ttee_hours', self.ttee_hours)
            print('ttee_mins', self.ttee_mins)

            # Update state to reflect the event and the timestamp we've calculated for
            self.c_event = self.d_event
            self.last_update = datetime.datetime.now().minute
  
        # If the number of days to the event is positive, the event is upcoming.
        # Work out how long we have till the event starts.
        # If it's negative, the event has already started, so instead we work out how long till the end
        if (self.tte_days >= 0):
            # If it's over a week away, just show days remaining
            if (self.tte_days > 7):
                countdown = ("[" + str(self.d_event+1) + "] in " + str(self.tte_days) + "d" )
            else:
                countdown=("[" + str(self.d_event+1) + "] in " + str(self.tte_days) + "d" + 
                    str(self.tte_hours) + "h" + str(self.tte_mins) + "m" )
            start = self.events[self.d_event]['estart_dt'].astimezone(self.localtz).strftime("%H:%M")
        else:
            # Recreate the arrow character when we know we need to use it. Just to be safe.
            # Just show days if it's not finishing in less than a week :)
            lcd.create_char(1, self.arrow)
            if (self.ttee_days > 7):
              countdown= "["+ str(self.d_event+1) + "] Now\x01" + str(self.ttee_days) + "d" 
            else:
              countdown= ("["+ str(self.d_event+1) + "] Now\x01" + str(self.ttee_days) + "d" + 
                  str(self.ttee_hours) + "h" + str(self.ttee_mins) + "m" )
            start = ""

        # If the event is less than 300 minutes away (5 hours), vary the backlight
        # Hue values 0.0 -> 0.3 give us a decent green -> red transition.
        # Take the number of seconds left, divide by 60 to give us minutes remaining
        # then divide by 1,000 to give us 0.3 at 300 mins left ~~> 0.0 at 0 mins.
        # Use the provided hue_to_rgb() function to do the maths for us, and set the
        # backlight accordingly.
        if (self.tte_days == 0 and (float(self.tte_secs) / 60) < 300):
            rgb = backlight.hue_to_rgb(float(self.tte_secs)/60000)
            self.SetRGB(rgb[0], rgb[1], rgb[2])
        else:
            self.SetRGB(self.defaultR, self.defaultG, self.defaultB)

        # Pick out the event summary
        if (self.events[self.d_event]['allday_flag'] == True):
            summary = "All Day:" + self.events[self.d_event]['summary']
        else:
            summary = start + " " + self.events[self.d_event]['summary']

        # We don't need to bother scrolling events with short names
        if (len(summary) < 16):
            scrollsummary = False
        else:
            scrollsummary = True
        
        #  When the clock's active, we use a custom character for the colon
        #  We redefine this character every other second so the top dot is
        #  missing. Which gives us a nice 'blinking' top dot in the time :)
        animframe = (datetime.datetime.now().second % 2)
        lcd.create_char(2, self.clockanim[animframe])
        # datetime.now returns local time, so this behaves correctly
        clockstring=datetime.datetime.now(self.localtz).strftime('%a %d %b %H\x02%M')

        # Write the menu rows
        menu.write_option(
          row=0,
          text=clockstring,
          scroll=False
        )
        menu.write_option(
          row=1,
          text=countdown,
          scroll=False
        )
        menu.write_option(
          row=2,
          text=summary,
          scroll=scrollsummary
        )

def cleanup():
    """
       Function called on exit. Just clears the screen and turns all the lights off
    """
    lcd.clear()
    backlight.rgb(0,0,0)
    backlight.graph_off()

def main():
    """ 
       Set up a menu with the Calendar and go straight into it.
    """

    menu = Menu(
      structure={
          'calendar': GoogleCalendar()
      },
      lcd=lcd
    )

    # Register a function to turn the lights off on script exit.
    atexit.register(cleanup)

    # Go straight into out menu plugin, making it an app in this case
    menu.right()

    # setup default menu handlers 
    touch.bind_defaults(menu)
    while 1:
        menu.redraw()
        time.sleep(0.02)

# Go into the main function if running as a script instead of a plugin
if __name__ == '__main__':
    main()

