#!/usr/bin/python

# The Laser Nanny project is hosted here:
# https://github.com/Workshop88/laser_nanny/blob/master/ws88_laser_nanny.py
#
# It is a Python program running on a Raspberry Pi 3 which monitors the laser 
# cutter temperatures, opens laser cutter exaust blast gate and tracks laser 
# cutter usage.
#
# This Python programs uses CharLCD to control Laser Nanny's 160 character 
# LCD.  CharLCD is hosted here & can be downloaded here:
# https://pypi.python.org/pypi/CharLCD
#
# It also uses GPIO for the Raspberry Pi and w1thermsensor.
# w1thermsensor is hosted here:
# https://github.com/timofurrer/w1thermsensor
# ...and can be installed using this command:
# pip install w1thermsensor
# gpio is hosted here:
# https://pypi.python.org/pypi/RPi.GPIO
# ...and can be installed using this command:
# sudo pip install RPi.GPIO


import os
import errno
import socket
import select
import sys
import RPi.GPIO as GPIO #pylint: disable=I0011,F0401
import datetime
import time

import urllib
import urllib2

from time import sleep
from charlcd.drivers.gpio import Gpio
from charlcd import lcd_buffered as lcd
from charlcd.drivers.i2c import I2C #pylint: disable=I0011,F0401
from socket import error as socket_error
from enum import Enum
from datetime import datetime as dt

from slacker import Slacker
try: execfile("do_not_scc_this_file.py")
except IOError: print("Missing do_not_scc_this_file.py.\n")

screen_lcd = Enum('screen_lcd', 'info menu status settings about')

# Setup for BCM pin numbering.
GPIO.setmode(GPIO.BCM)

# Setup for LaserCutter On/Off input.
GPIO.setup(17, GPIO.IN)

# Setup GPIO port for servo control.
GPIO.setup(18, GPIO.OUT)

from pad4pi import rpi_gpio

KEYPAD = [
        [1,2,3],
        [4,5,6],
        [7,8,9],
#        ["*",0,"#"]
# rbf  For now we don't want to handle "*" & "#".
        [0,0,0]
]

ROW_PINS = [23,24,25,27] # BCM numbering
COL_PINS = [9,10,22] # BCM numbering

factory = rpi_gpio.KeypadFactory()

keypad = factory.create_keypad(keypad=KEYPAD, row_pins=ROW_PINS, col_pins=COL_PINS)

url = os.environ["URL_SERVER"]

# Need to set an initial value of no key press.
key_press = False

def printKey(key):
    global key_value
    global key_press
    key_value = key
    key_press = True

# printKey will be called each time a keypad button is pressed
keypad.registerKeyPressHandler(printKey)

#
# Child program routine.
#
def child():
##    print("Starting child: ", os.getpid())

    from w1thermsensor import W1ThermSensor
    sensor = W1ThermSensor()

    # Identify sensors and remember their purposes.
    sensor_list = W1ThermSensor.get_available_sensors();
    sensor01_id = sensor_list[0].id;
    sensor02_id = sensor_list[1].id;

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Looping until we get connected.
    socket_keep_trying = True
    while socket_keep_trying:
        try:
            server_socket.connect(('', 6000))
            # If we are here the socket connect worked and we did not throw an exception.
            # This is what we want so exit the while loop.
            socket_keep_trying = False
        except socket_error as serr:
            # Check for connection refused (111)
            if serr.errno != errno.ECONNREFUSED:
                # There are not the errors (111) we are looking for.
                # So raise the error again.
                raise serr
            # Else this must be the error we are looking for.
            # So stay in loop until it goes away.

### debug print ###    print "Sending on port 6000"

    while True:
        temperature_in_fahrenheit = sensor_list[0].get_temperature(W1ThermSensor.DEGREES_F)
        string_temp = "1, " + str(temperature_in_fahrenheit)
        try:
            server_socket.send(string_temp)
        except socket_error as serr:
            # Check for broken pipe (32).
            if serr.errno == errno.EPIPE:
                # Exit the child as the parent likely had terminated.
                os._exit(0)
### debug print ###        print(temperature_in_fahrenheit)

        temperature_in_fahrenheit = sensor_list[1].get_temperature(W1ThermSensor.DEGREES_F)
        string_temp = "2, " + str(temperature_in_fahrenheit)
        try:
            server_socket.send(string_temp)
        except socket_error as serr:
            # Check for broken pipe (32).
            if serr.errno == errno.EPIPE:
                # Exit the child as the parent likely has terminated.
                os._exit(0)
### debug print ###        print(temperature_in_fahrenheit)

#
# Parent program routine.
#
def parent():
    global key_value
    global key_press
    global blast_gate_state_open
    global history_time
    global temper_probe_1_active
    global temper_probe_1_switch_average
    global temper_probe_2_switch_average
    global temper_probe_1_switch_events
    global temper_probe_2_switch_events

    drv = Gpio()
    drv.pins = {
        'RS': 26,
        'E': 19,
        'E2': 7,
        'DB4': 12,
        'DB5': 16,
        'DB6': 20,
        'DB7': 21
    }

    # Define history as lists.
    history_time=[]
    history_temperature=[]

    # Initialize LCD menus
    menus = { # key=menu_number+item_number, menu_text, menu_next, function
        # First menu is always a splash / information only screen.  
        'Menu001Type':'Info',
        'Menu001Item001':("WorkShop88 LaserCutter Monitor V1.0", 2, null_function),
        'Menu001Item002':("Duct Temperature:", 2, null_function),
        'Menu001Item003':("Cutter Temperature:", 2, null_function),
        'Menu001Item004':("Blastgate:", 2, null_function),

        # All other menus are numerated lists of selectable items.
        # Top menu.
        'Menu002Type':'Menu',
        'Menu002Item001':("Manual Control", 3, null_function),
        'Menu002Item002':("Status", 4, null_function),
        'Menu002Item003':("Settings", 7, null_function),
        'Menu002Item004':("Back", 1, null_function),
        'Menu002Item005':("About", 8, null_function),

        # Manual control.
        'Menu003Type':'Menu',
        'Menu003Item001':("Open Blast Gate", 3, blast_gate_open),
        'Menu003Item002':("Close Blast Gate", 3, blast_gate_close),
        'Menu003Item003':("Push report to web", 3, push_report_to_web),
        'Menu003Item004':("Back", 2, null_function),

        # Status menu.
        'Menu004Type':'Menu',
        'Menu004Item001':("Time Status", 5, null_function),
        'Menu004Item002':("Temperature Status", 6, null_function),
        'Menu004Item003':("Back", 2, null_function),

        # Status time.
        'Menu005Type':'Menu',
        'Menu005Item001':("Time On:", 5, time_on_report_function),
        'Menu005Item002':("Next Time Stamp:", 5, next_time_report_function),
        'Menu005Item003':("Last Time Stamp:", 5, last_time_report_function),
        'Menu005Item004':("Back", 4, null_function),

        # Status temperature.
        'Menu006Type':'Menu',
        'Menu006Item001':("Temperature:", 6, temper_probe_switch),
        'Menu006Item002':("Average:", 6, temper_probe_switch_average),
        'Menu006Item003':("Events:", 6, temper_probe_switch_events),
        'Menu006Item004':("Back", 4, null_function),

        # Settings.
        'Menu007Type':'Menu',
        'Menu007Item001':("Publish on temp change. n/a", 7, null_function),
        'Menu007Item002':("Publish on time change. n/a", 7, null_function),
        'Menu007Item003':("Publish on temp or time change. n/a", 7, null_function),
        'Menu007Item004':("Back", 2, null_function),

        # About.
        'Menu008Type':'Info',
        'Menu008Item001':("The LaserCutter laser nanny project is ", 2, null_function),
        'Menu008Item002':("hosted at: https://github.com/Workshop88", 2, null_function),
        'Menu008Item003':("/laser_nanny", 2, null_function),
        'Menu008Item004':("", 2, null_function),
    }
    menu_current = 1

    # Initialize first run flags before reading in files as
    # history may change these flag's states.
    # Setup for analyzing the 1st sample correctly.
    temperature_sensor_1_first_run = True
    temperature_sensor_2_first_run = True

    #
    # Open time stamp file and read any history.
    #
    # Because we read from these files to build the current history, these
    # files must be populated.  If they are missing we need to create
    # them for the code to succeed.
    if os.path.exists('/home/pi/git/laser_nanny/laser_nanny.log') == False:
        # Create file and populate with dummy entries.
        file = open('/home/pi/git/laser_nanny/laser_nanny.log','w')
        file.write('off, 2019-01-01 00:00:00\n')
        file.close()
    if os.path.exists('/home/pi/git/laser_nanny/laser_nanny_temperature.log') == False:
        # Create file and populate with dummy entries.
        file = open('/home/pi/git/laser_nanny/laser_nanny_temperature.log','w')
        file.write('1,  60.000,2019-01-01 00:00:00\n')
        file.write('2,  60.000,2019-01-01 00:00:00\n')
        file.close()
    #
    # Initialize elapsed time to zero
    datetime_elasped_total = dt.strptime('00:00:00', '%H:%M:%S')
    datetime_last_start = dt.strptime('00:00:00', '%H:%M:%S')
    file = open('/home/pi/git/laser_nanny/laser_nanny.log','r')
    # Go to end of file.
    file.seek(0,2)
    line_last = file.readline()
##    print("line_last:",line_last)
    # Go to beginning of file.
    file.seek(0)
    line = file.readline()
##    print("line:", line)
    while (line != line_last):
##        print("line:", line)
        # Sort on and off events and accumulate total on time.
        field_file = line.strip().split(",")
##        print("field_file:", field_file[0], field_file[1])
        if field_file[0] == "on":
            datetime_last_start = dt.strptime(field_file[1].strip(), '%Y-%m-%d %H:%M:%S')
        elif field_file[0] == "off":
            datetime_last_end = dt.strptime(field_file[1].strip(),'%Y-%m-%d %H:%M:%S')
            datetime_elasped_time = datetime_last_end - datetime_last_start
##            print("datetime_elasped_time:", datetime_elasped_time)
            datetime_elasped_total = datetime_elasped_total + datetime_elasped_time
            # Grab the last 10 elasped times.
            history_time.insert(0, datetime_elasped_time)
            # rbf Limit size of history to 10 here.
        line = file.readline()
    file.close()
    # Ignore any on event with missing off events by setting off event to on event datetime.
    datetime_last_end = datetime_last_start
    # Arrange history sequence.
##    print("length of time history: ", len(history_time))
                        
    #
    # Open temperature stamp file and read any history.
    #
    file = open('/home/pi/git/laser_nanny/laser_nanny_temperature.log','r')
    # Go to end of file.
    file.seek(0,2)
    line_last = file.readline()
##    print("line_last:",line_last)
    # Go to beginning of file.
    file.seek(0)
    line = file.readline()
##    print("line:", line)
    while (line != line_last):
##        print("line:", line)
        # Sort probe 1 and 2 readings and find max & min and calcualte averages
        field_file = line.strip().split(",")
##        print("field_file:", field_file[0], field_file[1])
        if field_file[0] == "1":
            # Looking for max & min.
            # Initialize max and min if this is the initial pass.
            if temperature_sensor_1_first_run == True:
                temperature_sensor_1_max_all_time = float(field_file[1])
                temperature_sensor_1_min_all_time = float(field_file[1])
            else:
                if temperature_sensor_1_max_all_time < float(field_file[1]):
                    temperature_sensor_1_max_all_time = float(field_file[1])
                if temperature_sensor_1_min_all_time > float(field_file[1]):
                    temperature_sensor_1_min_all_time = float(field_file[1])
            # Calculating long and short term average.
            # Initialize long term average if this is the initial pass.
            if temperature_sensor_1_first_run == True:
                temperature_sensor_1_long_term_average = float(field_file[1]) * 1024
            else:
                temperature_sensor_1_long_term_average = temperature_sensor_1_long_term_average - (temperature_sensor_1_long_term_average / 1024)
                temperature_sensor_1_long_term_average = temperature_sensor_1_long_term_average + float(field_file[1])
            # Calculate short term moving average.
            # Initialize short term average if this is the initial pass.
            if temperature_sensor_1_first_run == True:
                temperature_sensor_1_short_term_average = float(field_file[1]) * 32
            else:
                temperature_sensor_1_short_term_average = temperature_sensor_1_short_term_average - (temperature_sensor_1_short_term_average / 32)
                temperature_sensor_1_short_term_average = temperature_sensor_1_short_term_average + float(field_file[1])
            temperature_sensor_1_first_run = False
        elif field_file[0] == "2":
            # Looking for max & min.
            # Initialize max and min if this is the initial pass.
            if temperature_sensor_2_first_run == True:
                temperature_sensor_2_max_all_time = float(field_file[1])
                temperature_sensor_2_min_all_time = float(field_file[1])
            else:
                if temperature_sensor_2_max_all_time < float(field_file[1]):
                    temperature_sensor_2_max_all_time = float(field_file[1])
                if temperature_sensor_2_min_all_time > float(field_file[1]):
                    temperature_sensor_2_min_all_time = float(field_file[1])
            # Calculating long and short term average.
            # Initialize long term average if this is the initial pass.
            if temperature_sensor_2_first_run == True:
                temperature_sensor_2_long_term_average = float(field_file[1]) * 1024
            else:
                temperature_sensor_2_long_term_average = temperature_sensor_2_long_term_average - (temperature_sensor_2_long_term_average / 1024)
                temperature_sensor_2_long_term_average = temperature_sensor_2_long_term_average + float(field_file[1])
            # Calculate short term moving average.
            # Initialize short term average if this is the initial pass.
            if temperature_sensor_2_first_run == True:
                temperature_sensor_2_short_term_average = float(field_file[1]) * 32
            else:
                temperature_sensor_2_short_term_average = temperature_sensor_2_short_term_average - (temperature_sensor_2_short_term_average / 32)
                temperature_sensor_2_short_term_average = temperature_sensor_2_short_term_average + float(field_file[1])
            temperature_sensor_2_first_run = False
        line = file.readline()
    file.close()
##    print("length of temperature history: ", len(history_temperature))


##    print("flag 1:", temperature_sensor_1_first_run, "max 1:",temperature_sensor_1_max_all_time,"min 1:",temperature_sensor_1_min_all_time,"long:", temperature_sensor_1_long_term_average,"short:",temperature_sensor_1_short_term_average)
##    print("flag 2:", temperature_sensor_2_first_run, "max 2:",temperature_sensor_2_max_all_time,"min 2:",temperature_sensor_2_min_all_time,"long:", temperature_sensor_2_long_term_average,"short:",temperature_sensor_2_short_term_average) 

                        
    # Initialize LCD.
    lcd_1 = lcd.CharLCD(40, 4, drv, 0, 0)
    lcd_1.init()

    # Render menus.
    for item in menus:
        if item.startswith("Menu"+"{:03n}".format(menu_current)+"Item"):
##            print(menus.get(item)[0])
            lcd_1.set_xy(0,((int(item[11:14])) - 1))
            lcd_1.stream(menus.get(item)[0])
    lcd_1.flush()

    # Setup to listen for child process temperature readings.
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', 6000))
    server_socket.listen(5)
##    print ("Listening on port 6000")

    read_list = [server_socket]
    log_update_1 = False
    log_update_2 = False
    lcd_update = False
    web_update = False
    log_update_1 = False
    log_update_2 = False
    lasercutter_state = False
    blast_gate_state_open = False
    log_update_slack = False

    global time_on_report_function_flag
    time_on_report_function_flag = True

    global next_time_report_index
    next_time_report_index = 0

    seconds = dt.now()
    seconds_interval_web = seconds + datetime.timedelta(seconds = 10)
    seconds_interval_log = seconds + datetime.timedelta(seconds = 10)
    seconds_interval_slack = seconds + datetime.timedelta(seconds = 10)

    seconds_interval_lcd_menu_timeout = seconds + datetime.timedelta(seconds = 60)

##    print (seconds)
##    print (seconds_interval_web)

    screen_lcd_current = screen_lcd.info

    temperature_sensor_1_change = False
    temperature_sensor_2_change = False
    temperature_sensor_1_new = False
    temperature_sensor_2_new = False
    temper_probe_1_active = True
    temper_probe_1_switch_average = 0
    temper_probe_2_switch_average = 0
    temper_probe_1_switch_events = 0
    temper_probe_2_switch_events = 0
    temperature_sensor_1_old = 0
    temperature_sensor_2_old = 0

    temperature_sensor_1 = ""
    temperature_sensor_2 = ""

    first_run_after_bootup = True

    try:
        while True:
            #
            # Manage time related events.
            #
            # Grab the current time and date in string form.
            time_string = dt.now().time().strftime('%H:%M:%S')
            date_string = dt.now().date().strftime('%Y-%m-%d')
            # Grab the current date/time.
            seconds = dt.now()
            # Manage the time interval between web updates.
            if seconds > seconds_interval_web:
                seconds_interval_web = seconds + datetime.timedelta(seconds = 300)
                web_update = True
            # Manage the time interval between log updates.
            if seconds > seconds_interval_log:
                seconds_interval_log = seconds + datetime.timedelta(seconds = 300)
                log_update_1 = True
                log_update_2 = True
            # Manage the time interval between slack updates.
            if seconds > seconds_interval_slack:
                seconds_interval_slack = seconds + datetime.timedelta(seconds = 3600)
                log_update_slack = True

            #
            # Process LaserCutter power On/Off here.
            #
            if GPIO.input(17) == True:
                if lasercutter_state == False:
                    lasercutter_state = True
                    blast_gate_open()
                    datetime_last_start = dt.now()
                    # Write on time stamp to file.
                    file = open('/home/pi/git/laser_nanny/laser_nanny.log','a')
                    file.write('on, '+str(datetime_last_start.strftime('%Y-%m-%d %H:%M:%S'))+'\n')
                    file.close()
##                    print("LaserCutter is On.")
            else:
                if lasercutter_state == True:
                    lasercutter_state = False
                    blast_gate_close()
                    datetime_last_end = dt.now()
                    # Write off time stap to file.
                    file = open('/home/pi/git/laser_nanny/laser_nanny.log','a')
                    file.write('off, '+str(datetime_last_end.strftime('%Y-%m-%d %H:%M:%S'))+'\n')
                    file.close()
                    # Add this interval to total and history.
                    datetime_elasped_time = datetime_last_end - datetime_last_start
                    datetime_elasped_total = datetime_elasped_total + datetime_elasped_time
                    history_time.insert(0, datetime_elasped_time)
##                    print("LaserCutter is Off.")
            if first_run_after_bootup:
                if GPIO.input(17) == True:
                    lasercutter_state = True
                    blast_gate_open()
                    datetime_last_start = dt.now()
                    # Write on time stamp to file.
                    file = open('/home/pi/git/laser_nanny/laser_nanny.log','a')
                    file.write('on, '+str(datetime_last_start.strftime('%Y-%m-%d %H:%M:%S'))+'\n')
                    file.close()
                else:
                    lasercutter_state = False
                    blast_gate_close()
                    datetime_last_end = dt.now()
                    # Write off time stamp to file.
                    file = open('/home/pi/git/laser_nanny/laser_nanny.log','a')
                    file.write('off, '+str(datetime_last_end.strftime('%Y-%m-%d %H:%M:%S'))+'\n')
                    file.close()
                    # Add this interval to total and history.
                    datetime_elasped_time = datetime_last_end - datetime_last_start
                    datetime_elasped_total = datetime_elasped_total + datetime_elasped_time
                    history_time.insert(0, datetime_elasped_time)

            #
            # Process key time out return to top menu here.
            #
            if(seconds_interval_lcd_menu_timeout < seconds):
                # Reset the lcd menu timeout back off timer.
                seconds_interval_lcd_menu_timeout = seconds + datetime.timedelta(seconds = 60)
                # Set up to fake button press and switch / display top menu.
                key_press = True
                # Note, the following depends on menu 2 option 4 always going back to 
                # the top menu w/o calling any routines (i.e. the "back" button).  If
                # this changes then we need to change the following 2 lines.
                menu_current = 2
                key_value = 4

            #
            # Process key presses & menu changes here.
            #
            if key_press == True:
                # Clear out the keypress flag.
                key_press = False
                # Reset the lcd menu timeout back off timer.
                seconds_interval_lcd_menu_timeout = seconds + datetime.timedelta(seconds = 60)
                # Find the menu we will display next.
##                print("Before:",menu_current)
                item =  "Menu"+"{:03n}".format(menu_current)+"Item"+"{:03n}".format(key_value)
                item_save_for_later = item
                if item in menus:
                    menu_current = menus.get(item)[1]
##                else:
##                    print("key not found in dictionary")
##                print("After:",menu_current)
                # Render menu.
                lcd_1.buffer_clear()
                for item in menus:
                    if item.startswith("Menu"+"{:03n}".format(menu_current)+"Item"):
##                        print(menus.get(item)[0])
                        item_number = int(item[11:14])
                        # Set LCD position of item's text.
                        lcd_1.set_xy((20 * int(item_number / 5)),(item_number - 1) % 4)
                        # Only enumerate menus.
                        if menus.get(item[0:7]+"Type") == 'Menu':
                            lcd_1.stream("{:1n}".format(item_number)+")"+menus.get(item)[0])
                        else:
                            lcd_1.stream(menus.get(item)[0])
                lcd_update = True
                # Call function if there is one.
                if item_save_for_later in menus:
                    if menus.get(item_save_for_later)[2] != null_function:
##                        print("===>", item_save_for_later)
##                        print("===>", menus.get(item_save_for_later)[2])
                        menus.get(item_save_for_later)[2]()
                

            #
            # Check for new temperature data.  This only blocks for 1/10 of a second.
            # The "0.1" is the 100ms timeout.  We only wait 1/10 of a second then
            # proceed to other things.
            #
            readable, writable, errored = select.select(read_list, [], [], 0.1)
            for s in readable:
            ### rbf   Don't think this is necesssary ###            s.setblocking(0)
                if s is server_socket:
                    client_socket, address = server_socket.accept()
                    read_list.append(client_socket)
##                    print ("Connection from", address)
                else:
                    data = s.recv(1024)
                    if data:
                        # Temperature process is sending data: "<probe_number>, <temperature>"
                        data_list = data.split(",")
                        if data_list[0] == "1":
                            # This is temperature sensor 1.
                            temperature_sensor_1 = data_list[1]
                            temp_temperature_sensor = float(temperature_sensor_1)
                            temperature_sensor_1_new = True
                            if (temperature_sensor_1_old > (temp_temperature_sensor + 0.5)) or (temperature_sensor_1_old < (temp_temperature_sensor - 0.5)):
                                # Update old temperature
                                temperature_sensor_1_old = float(temperature_sensor_1)
                                temperature_sensor_1_change = True
                        else:
                            # This is temperature sensor 2.
                            temperature_sensor_2 = data_list[1]
                            temp_temperature_sensor = float(temperature_sensor_2)
                            temperature_sensor_2_new = True
                            if (temperature_sensor_2_old > (temp_temperature_sensor + 0.5)) or (temperature_sensor_2_old < (temp_temperature_sensor - 0.5)):
                                # Update old temperature
                                temperature_sensor_2_old = float(temperature_sensor_2)
                                temperature_sensor_2_change = True
                    else:
                        s.close()
                        read_list.remove(s)

            #
            # Analyz temperature date.
            # 
            # Calculate long term moving average.
            if temperature_sensor_1_new == True:
                # Initialize long term average if this is the initial pass.
                if temperature_sensor_1_first_run == True:
                    temperature_sensor_1_long_term_average = float(temperature_sensor_1) * 1024
                    temperature_sensor_1_max_all_time = float(temperature_sensor_1)
                    temperature_sensor_1_min_all_time = float(temperature_sensor_1)
                else:
                    temperature_sensor_1_long_term_average = temperature_sensor_1_long_term_average - (temperature_sensor_1_long_term_average / 1024)
                    temperature_sensor_1_long_term_average = temperature_sensor_1_long_term_average + float(temperature_sensor_1)
            if temperature_sensor_2_new == True:
                # Initialize long term average if this is the initial pass.
                if temperature_sensor_2_first_run == True:
                    temperature_sensor_2_long_term_average = float(temperature_sensor_2) * 1024
                    temperature_sensor_2_max_all_time = float(temperature_sensor_1)
                    temperature_sensor_2_min_all_time = float(temperature_sensor_1)
                else:
                    temperature_sensor_2_long_term_average = temperature_sensor_2_long_term_average - (temperature_sensor_2_long_term_average / 1024)
                    temperature_sensor_2_long_term_average = temperature_sensor_2_long_term_average + float(temperature_sensor_2)
            # Calculate short term moving average.
            if temperature_sensor_1_new == True:
                # Initialize short term average if this is the initial pass.
                if temperature_sensor_1_first_run == True:
                    temperature_sensor_1_short_term_average = float(temperature_sensor_1) * 32
                else:
                    temperature_sensor_1_short_term_average = temperature_sensor_1_short_term_average - (temperature_sensor_1_short_term_average / 32)
                    temperature_sensor_1_short_term_average = temperature_sensor_1_short_term_average + float(temperature_sensor_1)
            if temperature_sensor_2_new == True:
                # Initialize short term average if this is the initial pass.
                if temperature_sensor_2_first_run == True:
                    temperature_sensor_2_short_term_average = float(temperature_sensor_2) * 32
                else:
                    temperature_sensor_2_short_term_average = temperature_sensor_2_short_term_average - (temperature_sensor_2_short_term_average / 32)
                    temperature_sensor_2_short_term_average = temperature_sensor_2_short_term_average + float(temperature_sensor_2)
            # Calculate min and max temperatures.
            if temperature_sensor_1_new == True:
                # Initialize max and min if this is the initial pass.
                if temperature_sensor_1_first_run == True:
                    temperature_sensor_1_max_all_time = float(temperature_sensor_1)
                    temperature_sensor_1_min_all_time = float(temperature_sensor_1)
                else:
                    if temperature_sensor_1_max_all_time < float(temperature_sensor_1):
                        temperature_sensor_1_max_all_time = float(temperature_sensor_1)
                    if temperature_sensor_1_min_all_time > float(temperature_sensor_1):
                        temperature_sensor_1_min_all_time = float(temperature_sensor_1)
            if temperature_sensor_2_new == True:
                # Initialize max and min if this is the initial pass.
                if temperature_sensor_2_first_run == True:
                    temperature_sensor_2_max_all_time = float(temperature_sensor_2)
                    temperature_sensor_2_min_all_time = float(temperature_sensor_2)
                else:
                    if temperature_sensor_2_max_all_time < float(temperature_sensor_2):
                        temperature_sensor_2_max_all_time = float(temperature_sensor_2)
                    if temperature_sensor_2_min_all_time > float(temperature_sensor_2):
                        temperature_sensor_2_min_all_time = float(temperature_sensor_2)

            #
            # Manage writing temperature data to log file.
            #
            if (log_update_1) or (log_update_2) or (temperature_sensor_1_change == True) or (temperature_sensor_2_change == True):
                # We are updating the log information so reset the back off timer.
                seconds_interval_log = seconds + datetime.timedelta(seconds = 300)
                # Open file if either temperature sensor has changed.
                file = open('/home/pi/git/laser_nanny/laser_nanny_temperature.log','a')
                if (log_update_1) or (temperature_sensor_1_change == True):
                    # Write temperature from probe 1.
                    file.write('1, '+temperature_sensor_1+','+str(dt.now().strftime('%Y-%m-%d %H:%M:%S'))+'\n')
                if (log_update_2) or (temperature_sensor_2_change == True):
                    # Write temperature from probe 2.
                    file.write('2, '+temperature_sensor_2+','+str(dt.now().strftime('%Y-%m-%d %H:%M:%S'))+'\n')
                file.close()
            #
            # Publish temperature data on slack.
            #
            # Make sure channel (and likely slack as well) are defined.
            try: channel
            except NameError: print("Missing slack credentials.\n")
            else: 
                if (log_update_slack) and ((temperature_sensor_1 < 40) or (temperature_sensor_2 < 40)):
                    # We are updating slack so reset the back off timer.
                    seconds_interval_slack = seconds + datetime.timedelta(seconds = 3600)
                    # Send freeze warning to slack.
                    temp_slack_string = "FREEZE WARNING!!!\n"
                    slack.chat.post_message(channel, temp_slack_string)
                    temp_slack_string = "(Autonomous message from Laser Nanny.)\n"
                    slack.chat.post_message(channel, temp_slack_string)
                    temp_slack_string = "Temperature near laser: %s F  Date Time: %s\n"%(temperature_sensor_1, str(dt.now().strftime('%Y-%m-%d %H:%M:%S')))
                    slack.chat.post_message(channel, temp_slack_string)
                    temp_slack_string = "Temperature behind blast gate: %s F  Date Time: %s\n"%(temperature_sensor_2, str(dt.now().strftime('%Y-%m-%d %H:%M:%S')))
                    slack.chat.post_message(channel, temp_slack_string)

            #
            #  Manage reporting temperature on web page.
            #
            if (web_update) or (temperature_sensor_1_change) or (temperature_sensor_2_change):
                # We are updating the web information so reset the back off timer.
                seconds_interval_web = seconds + datetime.timedelta(seconds = 300)
                data_string = 'temperature_sensor_1+','+temperature_sensor_2+','+time_string+','+str(temperature_sensor_1_max_all_time)+','+str(temperature_sensor_1_min_all_time)+','+str(temperature_sensor_2_max_all_time)+','+str(temperature_sensor_2_min_all_time)+','+str(lasercutter_state)'
                data = urllib.urlencode({'feed_name':data_string})
                full_url = url + '?' + data
##                print("url:", full_url)
                response = urllib2.urlopen(full_url)
##                print (full_url)

            #
            # Manage dynamic LCD information.
            # 
            # Top Page.
            # 
            if menu_current == 1:
                # Manage reporting temperature on LCD.
                if temperature_sensor_1_new == True:
#                     temperature_sensor_1_new = False
##                    print("Sensor 1: " + data_list[1])
                    lcd_1.set_xy(20, 1)
                    lcd_1.stream(data_list[1])
                    lcd_update = True
                if temperature_sensor_2_new == True:
#                     temperature_sensor_2_new = False
##                    print("Sensor 2: " + data_list[1])
                    lcd_1.set_xy(20, 2)
                    lcd_1.stream(data_list[1])
                    lcd_update = True
                if lasercutter_state == True:
                    lcd_1.set_xy(20, 3)
                    lcd_1.stream("Open ")
                    lcd_update = True
                else:
                    lcd_1.set_xy(20, 3)
                    if(blast_gate_state_open == True):
                        lcd_1.stream("Open")
                    else:
                        lcd_1.stream("Close")
                    lcd_1.set_xy(32, 2)
                    lcd_1.stream(time_string)
                    lcd_1.set_xy(30, 3)
                    lcd_1.stream(date_string)
                    lcd_update = True
            # 
            # Manual Control Page.
            # 
            elif menu_current == 3:
                if(blast_gate_state_open == True):
                    lcd_1.set_xy(20, 0)
                    lcd_1.stream("<===")
                    lcd_1.set_xy(20, 1)
                    lcd_1.stream("    ")
                else:
                    lcd_1.set_xy(20, 0)
                    lcd_1.stream("    ")
                    lcd_1.set_xy(20, 1)
                    lcd_1.stream("<===")
                    lcd_update = True
            # 
            # Status Time Page.
            # 
            elif menu_current == 5:
                lcd_1.set_xy(20, 0)
                # Decide if reporting current interval time or total time.
                if time_on_report_function_flag == True:
                    # Report current interval time.
                    if lasercutter_state == True:
                        # Laser cutter is on so report now_time - start_time.
                        datetime_elasped_time = dt.now() - datetime_last_start
                        str_elasped_time = "(Current) "+str(datetime_elasped_time)
                    else:
                         # Laser cutter is off so report off_time - start_time.
                         datetime_elasped_time = datetime_last_end - datetime_last_start
                         str_elasped_time = "(Last Time) "+str(datetime_elasped_time)
                    lcd_1.stream(str_elasped_time)
                else:
                    # Report total time.
                    str_elasped_time = "(Total) "+str(datetime_elasped_total.strftime('%H:%M:%S'))
                    lcd_1.stream(str_elasped_time)
                lcd_1.set_xy(20, 1)
                if next_time_report_index == 0:
                    lcd_1.stream("Last Interval")
                else:
                    str_interval_time = "Back " + str(next_time_report_index) + " Intervals"
                    lcd_1.stream(str_interval_time)
                lcd_1.set_xy(20, 2)
                if lasercutter_state == True:
                    lcd_1.stream(str(history_time[next_time_report_index]))
                else:
                    lcd_1.stream(str(history_time[next_time_report_index]))
                lcd_update = True
            # 
            # Status Temperature Page.
            # 
            elif menu_current == 6:
                if temperature_sensor_1_new == True:
                    lcd_update = True
                if temperature_sensor_2_new == True:
                    lcd_update = True
                lcd_1.set_xy(20, 0)
                if temper_probe_1_active == True:
                    lcd_1.stream("Duct: "+str(temperature_sensor_1))
                else:
                    lcd_1.stream("Cutter: "+str(temperature_sensor_2))
                lcd_1.set_xy(20, 1)
                if temper_probe_1_active == True:
                    if temper_probe_1_switch_average == 0:
                        lcd_1.stream("Long Term: "+str(temperature_sensor_1_long_term_average / 1024))
                    else: 
                        lcd_1.stream("Short Term: "+str(temperature_sensor_1_short_term_average / 32))
                else:
                    if temper_probe_2_switch_average == 0:
                        lcd_1.stream("Long Term: "+str(temperature_sensor_2_long_term_average / 1024))
                    else: 
                        lcd_1.stream("Short Term: "+str(temperature_sensor_2_short_term_average / 32))
                lcd_1.set_xy(20, 2)
                if temper_probe_1_active == True:
                    if temper_probe_1_switch_events == 0:
                        lcd_1.stream("All Time Max: "+str(temperature_sensor_1_max_all_time))
                    elif temper_probe_1_switch_events == 1:
                        lcd_1.stream("All Time Min: "+str(temperature_sensor_1_min_all_time))
                    elif temper_probe_1_switch_events == 2:
                        lcd_1.stream("48 Hour Max: "+"n/a")
                    else: 
                        lcd_1.stream("48 Hour Min: "+"n/a")
                else:
                    if temper_probe_2_switch_events == 0:
                        lcd_1.stream("All Time Max: "+str(temperature_sensor_2_max_all_time))
                    elif temper_probe_2_switch_events == 1:
                        lcd_1.stream("All Time Min: "+str(temperature_sensor_2_min_all_time))
                    elif temper_probe_2_switch_events == 2:
                        lcd_1.stream("48 Hour Max: "+"n/a")
                    else: 
                        lcd_1.stream("48 Hour Min: "+"n/a")



            #
            # Only update the LCD here to save time.
            #
            if lcd_update:
                lcd_update = False
                lcd_1.flush()

            # End of executive loop.
            # Clear out any flags that only need to be set once per loop.
            if temperature_sensor_1_new == True:
                temperature_sensor_1_first_run = False
            if temperature_sensor_2_new == True:
                temperature_sensor_2_first_run = False
            temperature_sensor_1_new = False
            temperature_sensor_2_new = False
            temperature_sensor_1_change = False
            temperature_sensor_2_change = False
            web_update = False
            log_update_1 = False
            log_update_2 = False
            log_update_slack = False
            first_run_after_bootup = False

    # Catch a keyboard ctrl-c and exit cleanly by giving up the GPIO pins.
    except KeyboardInterrupt:
##        print("\rCtrl-C detected.  Cleaning up and exiting ws88_laser_nanny.")
        GPIO.cleanup()
        sys.exit()

#
# Function to open blast gate.
#
def blast_gate_open():
    global blast_gate_state_open
    blast_gate_state_open = True
    servo_blast_gate = GPIO.PWM(18, 50)
    for i in range(1, 20):
        # Where argument is the duty cycle (0.0 <= duty cycle <= 100.0)
        servo_blast_gate.start(8)
        time.sleep(.03)
    servo_blast_gate.stop()

#
# Function to close blast gate.
#
def blast_gate_close():
    global blast_gate_state_open
    blast_gate_state_open = False
    servo_blast_gate = GPIO.PWM(18, 50)
    for i in range(1, 20):
        # Where argument is the duty cycle (0.0 <= duty cycle <= 100.0)
        servo_blast_gate.start(2)
        time.sleep(.03)
    servo_blast_gate.stop()


def push_report_to_web():
    web_update = True

def time_on_report_function():
    global time_on_report_function_flag
    if time_on_report_function_flag == True:
        time_on_report_function_flag = False
    else:
        time_on_report_function_flag = True

def last_time_report_function():
    global next_time_report_index
    global history_time
    if next_time_report_index < (len(history_time) - 1):
        next_time_report_index = next_time_report_index + 1
    else:
        next_time_report_index = (len(history_time) - 1)

def next_time_report_function():
    global next_time_report_index
    if next_time_report_index > 0:
        next_time_report_index = next_time_report_index - 1
    else:
        next_time_report_index = 0

def temper_probe_switch():
    global temper_probe_1_active
    if temper_probe_1_active == True:
        temper_probe_1_active = False
    else: 
        temper_probe_1_active = True

def temper_probe_switch_average():
    global temper_probe_1_active
    global temper_probe_1_switch_average
    global temper_probe_2_switch_average
    if temper_probe_1_active == True:
        temper_probe_1_switch_average = temper_probe_1_switch_average + 1
        if temper_probe_1_switch_average > 1:
            temper_probe_1_switch_average = 0
    else:
        temper_probe_2_switch_average = temper_probe_2_switch_average + 1
        if temper_probe_2_switch_average > 1:
            temper_probe_2_switch_average = 0

def temper_probe_switch_events():
    global temper_probe_1_active
    global temper_probe_1_switch_events
    global temper_probe_2_switch_events
    if temper_probe_1_active == True:
        temper_probe_1_switch_events = temper_probe_1_switch_events + 1
        if temper_probe_1_switch_events > 3:
            temper_probe_1_switch_events = 0
    else:
        temper_probe_2_switch_events = temper_probe_2_switch_events + 1
        if temper_probe_2_switch_events > 3:
            temper_probe_2_switch_events = 0

# This function should never be called.
def null_function():
    print("Something called the NULL Function: This function should never be called.")

# Decide if we are the child or the parent.
def main():
    newpid = os.fork()
    if newpid == 0:
        child()
    else:
##        print("Parent: ", os.getpid(), "Child: ", newpid)
        parent()
   

# Call main.
main()




