#!/usr/bin/python

import sys

import RPi.GPIO as GPIO #pylint: disable=I0011,F0401

from time import sleep
from w1thermsensor import W1ThermSensor
sensor = W1ThermSensor()


from charlcd.drivers.gpio import Gpio
from charlcd import lcd_direct as lcd
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
    lcd_1.write('WorkShop88 LaserCutter Monitor V1.0', 0, 0)
    lcd_1.write('Duct Temperature:', 0, 1)
    lcd_1.write('Cutter Temperature:', 0, 2)
    lcd_1.write('Blastgate:', 0, 3)
    lcd_1.write('--.-', 20, 1)
    lcd_1.write('--.-', 20, 2)
    lcd_1.write('-----', 20, 3)

    # Identify sensors and remember their purposes.
    sensor_list = W1ThermSensor.get_available_sensors();
    sensor01_id = sensor_list[0].id;
    sensor02_id = sensor_list[1].id;

#    print 'Sensor 01 ID:{0}'.format(sensor01_id)
#    print 'Sensor 02 ID:{0}'.format(sensor02_id)

    while True:
        for x in range (0,100):
            if key_press == True:
                key_press = False
                string_to_lcd = str(key_value)
                lcd_1.write(string_to_lcd, 23, 3)
        temperature_in_fahrenheit = sensor_list[0].get_temperature(W1ThermSensor.DEGREES_F)
        string_to_lcd = str(temperature_in_fahrenheit)
        lcd_1.write(string_to_lcd, 20, 1)
        temperature_in_fahrenheit = sensor_list[1].get_temperature(W1ThermSensor.DEGREES_F)
        string_to_lcd = str(temperature_in_fahrenheit)
        lcd_1.write(string_to_lcd, 20, 2)


main()

GPIO.cleanup()



