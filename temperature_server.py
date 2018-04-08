import socket
import errno

from socket import error as socket_error

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
        # Check if unexpected error.
        if serr.errno != errno.ECONNREFUSED:
            # There are not the errors (111) we are looking for.  
            # So raise the error again.
            raise serr
        # Else this must be the error we are looking for.  
        # So stay in loop until it goes away.
    

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

