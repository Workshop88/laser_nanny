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



import sys

import RPi.GPIO as GPIO #pylint: disable=I0011,F0401

import datetime;

from time import sleep
from w1thermsensor import W1ThermSensor
sensor = W1ThermSensor()


from charlcd.drivers.gpio import Gpio
from charlcd import lcd_buffered as lcd
from charlcd.drivers.i2c import I2C #pylint: disable=I0011,F0401

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

# Need to set an initial value of no key press.
key_press = False

def printKey(key):
    global key_value
    global key_press
    key_value = key
    key_press = True

# printKey will be called each time a keypad button is pressed
keypad.registerKeyPressHandler(printKey)

def key_press_check():
    global key_press
    if key_press == True:
        key_press = False
        string_to_lcd = str(key_value)
        lcd_1.set_xy(15, 3)
        lcd_1.stream(string_to_lcd)

def main():
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

    # Identify sensors and remember their purposes.
    sensor_list = W1ThermSensor.get_available_sensors();
    sensor01_id = sensor_list[0].id;
    sensor02_id = sensor_list[1].id;

#    print 'Sensor 01 ID:{0}'.format(sensor01_id)
#    print 'Sensor 02 ID:{0}'.format(sensor02_id)

    while True:
        temperature_in_fahrenheit = sensor_list[0].get_temperature(W1ThermSensor.DEGREES_F)
        print(datetime.datetime.now().time().strftime('%H:%M:%S'))
        lcd_1.set_xy(20, 3)
        lcd_1.stream(datetime.datetime.now().time().strftime('%H:%M:%s'))
        key_press_check()
        string_to_lcd = str(temperature_in_fahrenheit)
        lcd_1.set_xy(20, 1)
        lcd_1.stream(string_to_lcd)
        temperature_in_fahrenheit = sensor_list[1].get_temperature(W1ThermSensor.DEGREES_F)
        print(datetime.datetime.now().time().strftime('%H:%M:%S'))
        lcd_1.set_xy(20, 3)
        lcd_1.stream(datetime.datetime.now().time().strftime('%H:%M:%s'))
        key_press_check()
        string_to_lcd = str(temperature_in_fahrenheit)
        lcd_1.set_xy(20, 2)
        lcd_1.stream(string_to_lcd)
        lcd_1.flush()


main()

GPIO.cleanup()



