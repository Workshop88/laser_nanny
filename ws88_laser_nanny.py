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

global key_value
global key_press

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

def child():
    print("Starting child: ", os.getpid())

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



def parent():
    global key_value
    global key_press

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
        'Menu002Item003':("Settings", 5, null_function),
        'Menu002Item004':("Back", 1, null_function),
        'Menu002Item005':("About", 6, null_function),

        # Manual control.
        'Menu003Type':'Menu',
        'Menu003Item001':("Open Blast Gate", 3, blast_gate_open),
        'Menu003Item002':("Close Blast Gate", 3, blast_gate_close),
        'Menu003Item003':("Push report to web", 3, push_report_to_web),
        'Menu003Item004':("Back", 2, null_function),

        # Status.
        'Menu004Type':'Menu',
        'Menu004Item001':("Elasped On Time:", 4, null_function),
        'Menu004Item002':("On Time Stamp:", 4, null_function),
        'Menu004Item003':("Off Time Stamp:", 4, null_function),
        'Menu004Item004':("Back", 2, null_function),

        # Settings.
        'Menu005Type':'Menu',
        'Menu005Item001':("Publish on temp change.", 5, null_function),
        'Menu005Item002':("Publish on time change.", 5, null_function),
        'Menu005Item003':("Publish on temp or time change.", 5, null_function),
        'Menu005Item004':("Back", 2, null_function),

        'Menu006Type':'Info',
        'Menu006Item001':("The LaserCutter laser nanny project is ", 2, null_function),
        'Menu006Item002':("hosted at: https://github.com/Workshop88", 2, null_function),
        'Menu006Item003':("/laser_nanny", 2, null_function),
        'Menu006Item004':("", 2, null_function),
    }
    menu_current = 1

    # Initialize LCD.
    lcd_1 = lcd.CharLCD(40, 4, drv, 0, 0)
    lcd_1.init()

    # Render menus.
    for item in menus:
        if item.startswith("Menu"+"{:03n}".format(menu_current)+"Item"):
            print(menus.get(item)[0])
            lcd_1.set_xy(0,((int(item[11:14])) - 1))
            lcd_1.stream(menus.get(item)[0])
    lcd_1.flush()

    # Setup to listen for child process temperature readings.
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', 6000))
    server_socket.listen(5)
    print "Listening on port 6000"

    read_list = [server_socket]
    lcd_update = False
    web_update = False
    lasercutter_state = False

    seconds = dt.now()
    seconds_interval = seconds + datetime.timedelta(seconds = 10)
    # rbf  Should get these from history file.
    time_string_last_start = dt.now().time().strftime('%H:%M:%S')
    time_string_last_end = dt.now().time().strftime('%H:%M:%S')

    print seconds
    print seconds_interval

    screen_lcd_current = screen_lcd.info

    temperature_sensor_1_change = False
    temperature_sensor_2_change = False

    try:
        while True:
            time_string = dt.now().time().strftime('%H:%M:%S')
#            time_string = dt.now().time().strftime('%Y-%m-%d %H:%M:%S')
            date_string = dt.now().date().strftime('%Y-%m-%d')
#            seconds = datetime.datetime.now()
            seconds = dt.now()
            timestamp = int(time.mktime(dt.now().timetuple()))
            print("timestamp:", timestamp)
            now = dt.fromtimestamp(timestamp)
            print("now:", now)
            if seconds > seconds_interval:
                seconds_interval = seconds + datetime.timedelta(seconds = 10)
                web_update = True
            lcd_1.set_xy(32, 2)
            lcd_1.stream(time_string)
            lcd_1.set_xy(30, 3)
            lcd_1.stream(date_string)

            # Process LaserCutter power On/Off here.
            if GPIO.input(17) == True:
                if lasercutter_state == False:
                    lasercutter_state = True
                    blast_gate_open()
#                    time_string_last_start = datetime.datetime.now().time().strftime('%H:%M:%S')
                    time_string_last_start = dt.now().time().strftime('%H:%M:%S')
                    print("LaserCutter is On.")
            else:
                if lasercutter_state == True:
                    lasercutter_state = False
                    blast_gate_close()
#                    time_string_last_end = datetime.datetime.now().time().strftime('%H:%M:%S')
                    time_string_last_end = dt.now().time().strftime('%H:%M:%S')
                    print("LaserCutter is Off.")

            # Process key presses & menu changes here.
            if key_press == True:
                # Clear out the keypress flag.
                key_press = False
                # Find the menu we will display next.
                print("Before:",menu_current)
                item =  "Menu"+"{:03n}".format(menu_current)+"Item"+"{:03n}".format(key_value)
                item_save_for_later = item
#                print("using key:", item)
                if item in menus:
                    menu_current = menus.get(item)[1]
                else:
                    print("key not found in dictionary")
                print("After:",menu_current)
                # Render menu.
                lcd_1.buffer_clear()
                for item in menus:
                    if item.startswith("Menu"+"{:03n}".format(menu_current)+"Item"):
                        print(menus.get(item)[0])
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
#                item =  "Menu"+"{:03n}".format(menu_current)+"Item"+"{:03n}".format(key_value)
                if item_save_for_later in menus:
                    if menus.get(item_save_for_later)[2] != null_function:
                        print("===>", item_save_for_later)
                        print("===>", menus.get(item_save_for_later)[2])
                        menus.get(item_save_for_later)[2]()
                

            # Check for new temperature data.  This only blocks for 1/10 of a second.
            # The "0.1" is the 100ms timeout.  We only wait 1/10 of a second then
            # proceed to other things.
            readable, writable, errored = select.select(read_list, [], [], 0.1)
            for s in readable:
            ### rbf   Don't think this is necesssary ###            s.setblocking(0)
                if s is server_socket:
                    client_socket, address = server_socket.accept()
                    read_list.append(client_socket)
                    print "Connection from", address
                else:
                    data = s.recv(1024)
                    if data:
                        # Temperature process is sending data: "<probe_number>, <temperature>"
                        data_list = data.split(",")
                        if data_list[0] == "1":
                            # This is temperature sensor 1.
                            temperature_sensor_1 = data_list[1]
                            temperature_sensor_1_change = True
                        else:
                            # This is temperature sensor 2.
                            temperature_sensor_2 = data_list[1]
                            temperature_sensor_2_change = True
                    else:
                        s.close()
                        read_list.remove(s)

            # Manage dynamic LCD information.
            if menu_current == 1:
                # Manage reporting temperature on LCD.
                 if temperature_sensor_1_change == True:
                     temperature_sensor_1_change = False
                     print("Sensor 1: " + data_list[1])
                     lcd_1.set_xy(20, 1)
                     lcd_1.stream(data_list[1])
                     lcd_update = True
                 if temperature_sensor_2_change == True:
                     temperature_sensor_2_change = False
                     print("Sensor 2: " + data_list[1])
                     lcd_1.set_xy(20, 2)
                     lcd_1.stream(data_list[1])
                     lcd_update = True
                 if lasercutter_state == True:
                     lcd_1.set_xy(20, 3)
                     lcd_1.stream("Open ")
                     lcd_update = True
                 else:
                     lcd_1.set_xy(20, 3)
                     lcd_1.stream("Close")
                     lcd_update = True
            elif menu_current == 4:
                     lcd_1.set_xy(20, 0)
                     if lasercutter_state == True:
                         print("111", dt.now().time().strftime('%H:%M:%S'))
                         print("222", time_string_last_start)
                         print("333", dt.strptime(time_string_last_start,'%H:%M:%S'))
                         time_string_elasped_time = dt.strptime(dt.now().time().strftime('%H:%M:%S'), '%H:%M:%S') - dt.strptime(time_string_last_start,'%H:%M:%S')
                     else:
                         time_string_elasped_time = dt.strptime(time_string_last_end, '%H:%M:%S') - dt.strptime(time_string_last_start,'%H:%M:%S')
                     str_elasped_time = str(time_string_elasped_time)
                     lcd_1.stream(str_elasped_time)
                     lcd_1.set_xy(20, 1)
                     lcd_1.stream(time_string_last_start)
                     lcd_1.set_xy(20, 2)
                     lcd_1.stream(time_string_last_end)
                     lcd_update = True


            # Only update the LCD here to save time.
            if lcd_update:
                lcd_update = False
                lcd_1.flush()

            #  Manage reporting temperature on web page.
            if web_update:
                web_update = False
                data_string = temperature_sensor_1+','+temperature_sensor_2+','+time_string
#                data_string = "temp1="+temperature_sensor_1+"&temp2="+temperature_sensor_2
                data = urllib.urlencode({'feed_name':data_string})
#                data = urllib.unquote({'feed_name':data_string})
                full_url = url + '?' + data
                print("url:", full_url)
                response = urllib2.urlopen(full_url)
                print full_url

    # Catch a keyboard ctrl-c and exit cleanly by giving up the GPIO pins.
    except KeyboardInterrupt:
        print("\rCtrl-C detected.  Cleaning up and exiting ws88_laser_nanny.")
        GPIO.cleanup()
        sys.exit()

# Function to open blast gate.
def blast_gate_open():
    print("Code to open blast gate goes here.")
    servo_blast_gate = GPIO.PWM(18, 50)
    for i in range(1, 20):
        # Where argument is the duty cycle (0.0 <= duty cycle <= 100.0)
        servo_blast_gate.start(8)
        time.sleep(.03)
    servo_blast_gate.stop()

# Function to close blast gate.
def blast_gate_close():
    print("Code to close blast gate goes here.")
    servo_blast_gate = GPIO.PWM(18, 50)
    for i in range(1, 20):
        # Where argument is the duty cycle (0.0 <= duty cycle <= 100.0)
        servo_blast_gate.start(2)
        time.sleep(.03)
    servo_blast_gate.stop()


def push_report_to_web():
    web_update = True

# This function should never be called.
def null_function():
    print("Something called the NULL Function: This function should never be called.")

# Decide if we are the child or the parent.
def main():
    newpid = os.fork()
    if newpid == 0:
        child()
    else:
        print("Parent: ", os.getpid(), "Child: ", newpid)
        parent()
   

# Call main.
main()




