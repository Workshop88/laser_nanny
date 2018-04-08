
import socket

from w1thermsensor import W1ThermSensor
sensor = W1ThermSensor()

# Identify sensors and remember their purposes.
sensor_list = W1ThermSensor.get_available_sensors();
sensor01_id = sensor_list[0].id;
sensor02_id = sensor_list[1].id;

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.connect(('', 6000))

print "Sending on port 6000"

while True:
    temperature_in_fahrenheit = sensor_list[0].get_temperature(W1ThermSensor.DEGREES_F)
    string_temp = "1, " + str(temperature_in_fahrenheit)
    server_socket.send(string_temp)
    print(temperature_in_fahrenheit)

    temperature_in_fahrenheit = sensor_list[1].get_temperature(W1ThermSensor.DEGREES_F)
    string_temp = "2, " + str(temperature_in_fahrenheit)
    server_socket.send(string_temp)
    print(temperature_in_fahrenheit)

