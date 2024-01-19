from machine import ADC
import urequests
import network
import time
import math
from breakout_bme280 import BreakoutBME280
from pimoroni_i2c import PimoroniI2C
import os
logfile = open('log.txt', 'a')
# duplicate stdout and stderr to the log file
os.dupterm(logfile)


PINS_BREAKOUT_GARDEN = {"sda": 4, "scl": 5}
PINS_PICO_EXPLORER = {"sda": 20, "scl": 21}

i2c = PimoroniI2C(**PINS_BREAKOUT_GARDEN)
bme = BreakoutBME280(i2c)

wind_speed_sensor = machine.Pin(9, machine.Pin.IN, machine.Pin.PULL_UP)
rain_sensor = machine.Pin(10, machine.Pin.IN, machine.Pin.PULL_UP)
wind_direction_sensor = ADC(1)

ssid = 'myWifi'
password = 'myPassword'
 
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.config(pm = 0xa11140)
wlan.connect(ssid, password)


url = "https://us-east-1-1.aws.cloud2.influxdata.com/api/v2/write?org=Dev&bucket=WeatherStation&precision=ns"


headers = {
  'Authorization': 'Token myToken',
  'Content-Type': 'text/plain; charset=utf-8',
  'Accept': 'application/json'
}


led = machine.Pin("LED", machine.Pin.OUT)

max_wait = 60
while max_wait > 0:
  if wlan.status() < 0 or wlan.status() >= 3:
    break
  max_wait -= 1
  print('waiting for connection...')
  time.sleep(1)
 
# Handle connection error
if wlan.status() != 3:
   raise RuntimeError('network connection failed')
else:
  print('connected')
  status = wlan.ifconfig()
  print( 'ip = ' + status[0] )
  led.on()
  
height = 420
inhgConstant = 33.863886666667
wind_speed_mph_per_pulse = 1.492
rain_in_per_tick = 0.011
amount = 0
last_interrupt = 0
debounce_delay = 50  # debounce delay in milliseconds
wind_interval = 5  # changed to 5 seconds
total_duration = 120  # 3 minutes in seconds
store_speeds = []  # moved outside of the loop

junkReading = bme.read()

time.sleep(1.0)

def rainfall(pin):
    global amount
    global last_interrupt
    now = time.ticks_ms()
    if now - last_interrupt > debounce_delay:
        amount += rain_in_per_tick
        print(amount)
    last_interrupt = now
    return amount
# function to count wind speed sensor pulses
def spin(pin):
    global wind_count
    wind_count += 1
    return wind_count


rain_sensor.irq(trigger=machine.Pin.IRQ_FALLING, handler=rainfall)

def wind_direction():
    ADC_TO_DEGREES = (1.62, 2.93, 2.85, 3.27, 3.23, 3.18, 3.22, 0.41, 3.07, 3.12, 2.42, 2.52, 0.54, 1.34, 0.94, 2.11)
    degree_list = (360, 22.5, 45, 67.5, 90, 112.5, 135, 157.5, 180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5)
    closest_index = -1
    last_index = None
    while True:
        value = round(wind_direction_sensor.read_u16() * 3.3 / 65535, 2)
        closest_index = -1
        closest_value = float('inf')
        for i in range(16):
            distance = abs(ADC_TO_DEGREES[i] - value)
            if distance < closest_value:
                closest_value = distance
                closest_index = i
        if last_index == closest_index:
            break
        last_index = closest_index
    degrees = degree_list[closest_index]
    return degrees

def cardinal_direction(average_direction):
    ADC_TO_DEGREES = (360, 22.5, 45, 67.5, 90, 112.5, 135, 157.5, 180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5)
    CARDINAL_DIRECTIONS = ('N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW')
    closest_index = -1
    last_index = None
    while True:
        value = average_direction
        closest_index = -1
        closest_value = float('inf')
        for i in range(16):
            distance = abs(ADC_TO_DEGREES[i] - value)
            if distance < closest_value:
                closest_value = distance
                closest_index = i
        if last_index == closest_index:
            break
        last_index = closest_index
    cardinal_direction = CARDINAL_DIRECTIONS[closest_index]
    return cardinal_direction

# function to calculate wind speed in mph
def calculate_speed(wind_count):
    dist_miles = wind_count * wind_speed_mph_per_pulse
    speed_mph = dist_miles / wind_interval
    return speed_mph


# main loop to measure wind speed every 5 seconds over 5 minutes
while True:
    print(time.time())
    start_time = time.time()
    store_speeds = []
    store_directions = []
    store_rainfall = []
    while time.time() - start_time <= total_duration:
        wind_count = 0
        amount = 0
        start_interval = time.time()
        while time.time() - start_interval <= wind_interval:
            wind_speed_sensor.irq(trigger=machine.Pin.IRQ_FALLING, handler=spin)
        final_speed = calculate_speed(wind_count)
        new_direction = wind_direction()
        store_speeds.append(final_speed)
        store_directions.append(new_direction)
        store_rainfall.append(amount)
        wind_count = 0
        amount = 0

    # calculate average speed and max gust
    wind_speed = sum(store_speeds) / len(store_speeds)
    wind_gust = max(store_speeds)
    total_rainfall = sum(store_rainfall)
    rainfall_rate = total_rainfall * 12
    average_direction = sum (store_directions) / len(store_directions)
    word_direction = cardinal_direction(average_direction)
    word_direction = f'"{word_direction}"'
    reading = bme.read()
    temperature = reading[0]
    temperature = (temperature * 1.8) + 32
    pressure = reading[1]
    pressure = pressure/100
    convertedPressure = pressure/(1-(height/44330))**5.255
    BarometricPressure = convertedPressure/inhgConstant
    humidity = reading[2]
    payload=f"Weather,Device=Pico1,Location=Backyard Temperature={temperature},Humidity={humidity},Pressure={pressure},ConvertedPressure={convertedPressure},BarometricPressure={BarometricPressure},WindSpeed={wind_speed},WindGust={wind_gust},WindDirection={average_direction},CardinalDirection={word_direction},Rainfall={total_rainfall},RainfallRate={rainfall_rate}"
    try:
        print("sending...")
        response = urequests.post(url, headers=headers, data=payload)
        print("sent (" + str(response.status_code) + "), status = " + str(wlan.status()) )
        response.close()
    except:
        print("could not connect (status =" + str(wlan.status()) + ")")
        if wlan.status() < 0 or wlan.status() >= 3:
            print("trying to reconnect...")
            wlan.disconnect()
            wlan.connect(ssid, password)
            if wlan.status() == 3:
                print('connected')
            else:
                print('failed')
    time.sleep(0.1)