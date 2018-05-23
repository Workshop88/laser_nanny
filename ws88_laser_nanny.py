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
import datetime;

import urllib
import urllib2

from time import sleep
from charlcd.drivers.gpio import Gpio
from charlcd import lcd_buffered as lcd
from charlcd.drivers.i2c import I2C #pylint: disable=I0011,F0401
from socket import error as socket_error

GPIO.setmode(GPIO.BCM)

from pad4pi import rpi_gpio

KEYPAD = [
        [1,2,3],
        [4,5,6],
        [7,8,9],
        ["*",0,"#"]
]

ROW_PINS = [23,24,25,27] # BCM numbering
COL_PINS = [9,10,22] # BCM numbering

factory = rpi_gpio.KeypadFactory()

keypad = factory.create_keypad(keypad=KEYPAD, row_pins=ROW_PINS, col_pins=COL_PINS)

global key_value
global key_press

url = 'http://www.xnet.com/~stuart/ws88/save.cgi/'

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
    lcd_1 = lcd.CharLCD(40, 4, drv, 0, 0)
    lcd_1.init()
    lcd_1.set_xy(0,0)
    lcd_1.stream('WorkShop88 LaserCutter Monitor V1.0')
    lcd_1.set_xy(0,1)
    lcd_1.write('Duct Temperature:')
    lcd_1.set_xy(0,2)
    lcd_1.write('Cutter Temperature:')
    lcd_1.set_xy(0,3)
    lcd_1.write('Blastgate:')
    lcd_1.set_xy(20,1)
    lcd_1.write('--.-')
    lcd_1.set_xy(20,2)
    lcd_1.write('--.-')
    lcd_1.set_xy(12,3)
    lcd_1.write('-----')
    lcd_1.flush()


    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', 6000))
    server_socket.listen(5)
    print "Listening on port 6000"

    read_list = [server_socket]
    lcd_update = False
    web_update = False

    seconds = datetime.datetime.now()
    seconds_interval = seconds + datetime.timedelta(seconds = 10)


    print seconds
    print seconds_interval

    try:
        while True:
            time_string = datetime.datetime.now().time().strftime('%H:%M:%S')
            date_string = datetime.datetime.now().date().strftime('%Y-%m-%d')
            seconds = datetime.datetime.now()
            if seconds > seconds_interval:
                seconds_interval = seconds + datetime.timedelta(seconds = 10)
                web_update = True
            lcd_1.set_xy(20, 3)
            lcd_1.stream(time_string)
            lcd_1.set_xy(30, 3)
            lcd_1.stream(date_string)

            # Process the keyparesses here.
            if key_press == True:
                key_press = False
                string_to_lcd = str(key_value)
                lcd_1.set_xy(15, 3)
                lcd_1.stream(string_to_lcd)
                lcd_update = True

            # Check for new temperature data.  This only blocks for 1/10 of a second.
            # The "0.1" is the 100ms timeout.  We only want 1/10 of a second then
            # proceed to other things.
            readable, writable, errored = select.select(read_list, [], [], 0.1)
            for s in readable:
### don't think this is necesssary ###            s.setblocking(0)
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
                            print("Sensor 1: " + data_list[1])
                            lcd_1.set_xy(20, 1)
                            lcd_1.stream(data_list[1])
                            temperature_sensor_1 = data_list[1]
                        else:
                            # This is temperature sensor 2.
                            print("Sensor 2: " + data_list[1])
                            lcd_1.set_xy(20, 2)
                            lcd_1.stream(data_list[1])
                            temperature_sensor_2 = data_list[1]
                        lcd_update = True
                    else:
                        s.close()
                        read_list.remove(s)

            # Only update the LCD here to save time.
            if lcd_update:
                lcd_update = False
                lcd_1.flush()

            # Only update the web page when temperature changes.
            if web_update:
                web_update = False
                data_string = temperature_sensor_1+','+temperature_sensor_2+','+time_string
#                data_string = "temp1="+temperature_sensor_1+"&temp2="+temperature_sensor_2
                data = urllib.urlencode({'feed_name':data_string})
#                data = urllib.unquote({'feed_name':data_string})
                full_url = url + '?' + data
                response = urllib2.urlopen(full_url)
                print full_url

    # Catch a keyboard ctrl-c and exit cleanly by giving up the GPIO pins.
    except KeyboardInterrupt:
        print("\rCtrl-C detected.  Cleaning up and exiting ws88_laser_nanny.")
        GPIO.cleanup()
        sys.exit()


def main():
    newpid = os.fork()
    if newpid == 0:
        child()
    else:
        print("Parent: ", os.getpid(), "Child: ", newpid)
        parent()
   

main()




