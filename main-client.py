import network
import ubinascii as binascii
import urandom as random
import ustruct as struct
import usocket as socket
from ucollections import namedtuple
import re
import time
from machine import Pin,SPI,PWM
import framebuf

BL = 13
DC = 8
RST = 12
MOSI = 11
SCK = 10
CS = 9

class LCD_1inch3(framebuf.FrameBuffer):
    def __init__(self):
        self.width = 240
        self.height = 240
        
        self.cs = Pin(CS,Pin.OUT)
        self.rst = Pin(RST,Pin.OUT)
        
        self.cs(1)
        self.spi = SPI(1)
        self.spi = SPI(1,1000_000)
        self.spi = SPI(1,100000_000,polarity=0, phase=0,sck=Pin(SCK),mosi=Pin(MOSI),miso=None)
        self.dc = Pin(DC,Pin.OUT)
        self.dc(1)
        self.buffer = bytearray(self.height * self.width * 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)
        self.init_display()
        
        self.red   =   0x07E0
        self.green =   0x001f
        self.blue  =   0xf800
        self.white =   0xffff
        
    def write_cmd(self, cmd):
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, buf):
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(bytearray([buf]))
        self.cs(1)

    def init_display(self):
        """Initialize dispaly"""  
        self.rst(1)
        self.rst(0)
        self.rst(1)
        
        self.write_cmd(0x36)
        self.write_data(0x70)

        self.write_cmd(0x3A) 
        self.write_data(0x05)

        self.write_cmd(0xB2)
        self.write_data(0x0C)
        self.write_data(0x0C)
        self.write_data(0x00)
        self.write_data(0x33)
        self.write_data(0x33)

        self.write_cmd(0xB7)
        self.write_data(0x35) 

        self.write_cmd(0xBB)
        self.write_data(0x19)

        self.write_cmd(0xC0)
        self.write_data(0x2C)

        self.write_cmd(0xC2)
        self.write_data(0x01)

        self.write_cmd(0xC3)
        self.write_data(0x12)   

        self.write_cmd(0xC4)
        self.write_data(0x20)

        self.write_cmd(0xC6)
        self.write_data(0x0F) 

        self.write_cmd(0xD0)
        self.write_data(0xA4)
        self.write_data(0xA1)

        self.write_cmd(0xE0)
        self.write_data(0xD0)
        self.write_data(0x04)
        self.write_data(0x0D)
        self.write_data(0x11)
        self.write_data(0x13)
        self.write_data(0x2B)
        self.write_data(0x3F)
        self.write_data(0x54)
        self.write_data(0x4C)
        self.write_data(0x18)
        self.write_data(0x0D)
        self.write_data(0x0B)
        self.write_data(0x1F)
        self.write_data(0x23)

        self.write_cmd(0xE1)
        self.write_data(0xD0)
        self.write_data(0x04)
        self.write_data(0x0C)
        self.write_data(0x11)
        self.write_data(0x13)
        self.write_data(0x2C)
        self.write_data(0x3F)
        self.write_data(0x44)
        self.write_data(0x51)
        self.write_data(0x2F)
        self.write_data(0x1F)
        self.write_data(0x1F)
        self.write_data(0x20)
        self.write_data(0x23)
        
        self.write_cmd(0x21)

        self.write_cmd(0x11)

        self.write_cmd(0x29)

    def show(self):
        self.write_cmd(0x2A)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0xef)
        
        self.write_cmd(0x2B)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0xEF)
        
        self.write_cmd(0x2C)
        
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buffer)
        self.cs(1)

# Opcodes
OP_CONT = const(0x0)
OP_TEXT = const(0x1)
OP_BYTES = const(0x2)
OP_CLOSE = const(0x8)
OP_PING = const(0x9)
OP_PONG = const(0xa)

# Close codes
CLOSE_OK = const(1000)

# URL parsing
URL_RE = re.compile(r'ws://([A-Za-z0-9\-\.]+)(?:\:([0-9]+))?(/.+)?')
URI = namedtuple('URI', ('hostname', 'port', 'path'))

def urlparse(uri):
    match = URL_RE.match(uri)
    if match:
        return URI(match.group(1), int(match.group(2)), match.group(3))
    else:
        raise ValueError("Invalid URL: %s" % uri)

class Websocket:
    is_client = False

    def __init__(self, sock):
        self._sock = sock
        self.open = True

    def settimeout(self, timeout):
        self._sock.settimeout(timeout)

    def read_frame(self, max_size=None):
        byte1, byte2 = struct.unpack('!BB', self._sock.read(2))
        fin = bool(byte1 & 0x80)
        opcode = byte1 & 0x0f
        mask = bool(byte2 & (1 << 7))
        length = byte2 & 0x7f

        if length == 126:
            length, = struct.unpack('!H', self._sock.read(2))
        elif length == 127:
            length, = struct.unpack('!Q', self._sock.read(8))

        if mask:
            mask_bits = self._sock.read(4)

        try:
            data = self._sock.read(length)
        except MemoryError:
            self.close(code=CLOSE_TOO_BIG)
            return True, OP_CLOSE, None

        if mask:
            data = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(data))

        return fin, opcode, data

    def write_frame(self, opcode, data=b''):
        fin = True
        mask = self.is_client
        length = len(data)

        byte1 = 0x80 if fin else 0
        byte1 |= opcode
        byte2 = 0x80 if mask else 0

        if length < 126:
            byte2 |= length
            self._sock.write(struct.pack('!BB', byte1, byte2))
        elif length < (1 << 16):
            byte2 |= 126
            self._sock.write(struct.pack('!BBH', byte1, byte2, length))
        elif length < (1 << 64):
            byte2 |= 127
            self._sock.write(struct.pack('!BBQ', byte1, byte2, length))
        else:
            raise ValueError()

        if mask:
            mask_bits = struct.pack('!I', random.getrandbits(32))
            self._sock.write(mask_bits)
            data = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(data))

        self._sock.write(data)

    def recv(self):
        
        if not self.open:
            return 1
        assert self.open
        while self.open:
            try:
                fin, opcode, data = self.read_frame()
            except ValueError:
                self._close()
                return

            if not fin:
                raise NotImplementedError()

            if opcode == OP_TEXT:
                return data.decode('utf-8')
            elif opcode == OP_BYTES:
                return data
            elif opcode == OP_CLOSE:
                self._close()
                return
            elif opcode == OP_PONG:
                continue
            elif opcode == OP_PING:
                self.write_frame(OP_PONG, data)
                continue
            else:
                raise ValueError(opcode)

    def send(self, buf):
        assert self.open
        if isinstance(buf, str):
            opcode = OP_TEXT
            buf = buf.encode('utf-8')
        elif isinstance(buf, bytes):
            opcode = OP_BYTES
        else:
            raise TypeError()

        self.write_frame(opcode, buf)

    def close(self, code=CLOSE_OK, reason=''):
        if not self.open:
            return
        buf = struct.pack('!H', code) + reason.encode('utf-8')
        self.write_frame(OP_CLOSE, buf)
        self._close()

    def _close(self):
        self.open = False
        self._sock.close()

class WebsocketClient(Websocket):
    is_client = True

def connect(uri):
    uri = urlparse(uri)
    assert uri
    sock = socket.socket()
    addr = socket.getaddrinfo(uri.hostname, uri.port)
    try:
        sock.connect(addr[0][4])
    except OSError:
        return 1
    def send_header(header, *args):
        sock.send(header % args + '\r\n')
    clientId = '12341234134'
    key = binascii.b2a_base64(bytes(random.getrandbits(8) for _ in range(16)))[:-1]
    send_header(b'GET %s HTTP/1.1', uri.path or '/')
    send_header(b'Host: %s:%s', uri.hostname, uri.port)
    send_header(b'Connection: Upgrade')
    send_header(b'Upgrade: websocket')
    send_header(b'Sec-WebSocket-Key: %s', key)
    send_header(b'Sec-WebSocket-Version: 13')
    send_header(b'Origin: http://localhost')
    
    send_header(b'client-id: %s', clientId)
    
    send_header(b'')
    header = sock.readline()[:-2]
    print(header)
    assert header == b'HTTP/1.1 101 ', header
    while header:
        header = sock.readline()[:-2]

    return WebsocketClient(sock)

def connect_to_wifi():
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print("Connecting to the network...")
        sta_if.active(True)
        sta_if.connect("TP-Link_819F", "73849971")  # Тут замінити
        while not sta_if.isconnected():
            pass
    print("Connected to IP:", sta_if.ifconfig()[0])

joystick_center = machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_UP)
joystick_up = machine.Pin(2, machine.Pin.IN, machine.Pin.PULL_UP)
joystick_down = machine.Pin(18, machine.Pin.IN, machine.Pin.PULL_UP)
joystick_left = machine.Pin(16, machine.Pin.IN, machine.Pin.PULL_UP)
joystick_right = machine.Pin(20, machine.Pin.IN, machine.Pin.PULL_UP)

def read_temperature_celsius():
    # Read raw temperature from the sensor (ADC4 on Raspberry Pi Pico)
    sensor = machine.ADC(4)
    reading = sensor.read_u16()
    # Convert to Celsius using Pico's formula
    voltage = reading * (3.3 / 65535)
    temperature_c = 27 - (voltage - 0.706) / 0.001721
    return temperature_c

def setupButtons():
    pwm = PWM(Pin(BL))
    pwm.freq(1000)
    pwm.duty_u16(32768)#max 65535

    LCD = LCD_1inch3()
    #color BRG
    LCD.fill(LCD.white)
    LCD.show()
    return LCD
    
def check_winter(text):
    if text.startswith("Looks like winter is coming"):
        return "blue"
    else:
        return "red"
    
def draw_large_number(lcd, number, x, y, color, spacing=5):
    """
    Draws a large number on the LCD screen by filling rectangles for each part of the digit.
    
    Parameters:
        lcd (LCD_1inch3): The LCD object.
        number (int): The number to draw (0-9).
        x (int): The x-coordinate for the number's top-left corner.
        y (int): The y-coordinate for the number's top-left corner.
        color (int): Color code for the number.
        spacing (int): Space between two numbers if drawing multiple.
    """
    # Define rectangle patterns for each digit (0 to 9)
    patterns = {
        '0': [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6), (1, 0), (2, 0), (2, 1),  (2, 2),  (2, 3),  (2, 4),  (2, 5),  (2, 6),  (1, 6)],
        '1': [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6)],
        '2': [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (0, 3), (1, 3), (2, 3), (0, 4), (0, 5), (0, 6), (1, 6), (2, 6)], 
        '3': [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (0, 3), (1, 3), (2, 3), (2, 4), (2, 5), (0, 6), (1, 6), (2, 6)],
        '4': [(0, 0), (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6)],
        '5': [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (2, 4), (2, 5), (0, 6), (1, 6), (2, 6)], 
        '6': [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (2, 4), (2, 5), (0, 6), (1, 6), (2, 6), (0, 5), (0, 4)], 
        '7': [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6)],
        '8': [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (2, 4), (2, 5), (0, 6), (1, 6), (2, 6), (0, 5), (0, 4), (2, 1), (2, 2)], 
        '9': [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (2, 4), (2, 5), (0, 6), (1, 6), (2, 6), (2, 1), (2, 2)], 
    }

    # Draw each digit in the number
    digits = str(number)  # Convert the number to a string to iterate over each digit
    for index, digit in enumerate(digits):
        if digit in patterns:
            for block in patterns[digit]:
                lcd.fill_rect(x + block[0] * 10 + index * (10 + spacing), y + block[1] * 10, 10, 10, color)

def main():
    connect_to_wifi()
    LCD = setupButtons()
    keyA = Pin(15,Pin.IN,Pin.PULL_UP)
    LCD.fill_rect(208,15,30,30,LCD.red)
    LCD.show()
    while True:
        #if keyA.value() == 0:
        print("Trying to connect to websocket...")
        main2(LCD)
        time.sleep(0.5)
        LCD.fill_rect(208,15,30,30,LCD.white)
        LCD.show()
        time.sleep(0.5)
        LCD.fill_rect(208,15,30,30,LCD.red)
        LCD.show()
        
def spam_messages(ws, message, delay=0.001):
    """
    Функція для спаму повідомленнями на сервер через WebSocket.

    Аргументи:
        ws: Об'єкт WebSocket, що забезпечує з'єднання.
        message: Повідомлення для спаму (рядок).
        delay: Час між повідомленнями в секундах (може бути 0 для максимальної швидкості).
    """
    try:
        while True:
            ws.send(message)
            print(f"Sent: {message}")
            time.sleep(delay)  # Затримка між повідомленнями
    except KeyboardInterrupt:
        print("Спам завершено користувачем.")
        ws.close()
        print("WebSocket з'єднання закрите.")          

def main2(LCD):
    
    ws = connect("ws://192.168.0.104:8080/ws")  # WebSocket server IP and path
    if ws == 1:
        return
    print("Connected to WebSocket server.")
    LCD.fill_rect(208,15,30,30,LCD.green)
    LCD.show()
    # Set socket timeout for non-blocking receive
    ws.settimeout(0.01)  # Adjust as needed for responsiveness
    #spam_messages(ws, "Testing spam")
    try:
        temperature_set = 30
        keyA = Pin(15,Pin.IN,Pin.PULL_UP)
        keyB = Pin(17,Pin.IN,Pin.PULL_UP)
        keyX = Pin(19 ,Pin.IN,Pin.PULL_UP)
        keyY = Pin(21 ,Pin.IN,Pin.PULL_UP)
        while True:
            if(keyB.value() == 0):
                LCD.fill_rect(208,75,30,30,LCD.red)
                print("B")
            else :
                LCD.fill_rect(208,75,30,30,LCD.white)
                LCD.rect(208,75,30,30,LCD.green)
     
            if(keyX.value() == 0):
                LCD.fill_rect(208,135,30,30,LCD.blue)
                first_digit = (temperature_set - 1) // 10
                second_digit = (temperature_set - 1) % 10
                
                draw_large_number(LCD, first_digit, 50, 100, LCD.red)
                draw_large_number(LCD, second_digit, 90, 100, LCD.blue)
                temperature_set = temperature_set - 1
                time.sleep(0.1)
                print("C")
            elif(keyY.value() == 0):
                LCD.fill_rect(208,195,30,30,LCD.red)
                first_digit = (temperature_set + 1) // 10
                second_digit = (temperature_set + 1) % 10
                
                draw_large_number(LCD, first_digit, 50, 100, LCD.red)
                draw_large_number(LCD, second_digit, 90, 100, LCD.blue)
                temperature_set = temperature_set + 1
                time.sleep(0.1)
                print("D")
            else :
                LCD.fill_rect(208,195,30,30,LCD.white)
                LCD.fill_rect(208,135,30,30,LCD.white)
                LCD.fill_rect(40,90,100,100,LCD.white)
                LCD.rect(208,195,30,30,LCD.green)
                LCD.rect(208,135,30,30,LCD.green)

                
            LCD.show()
            temperature = read_temperature_celsius()
            
            if temperature < temperature_set:
                ws.send(f"Looks like winter is coming, Temperature: {temperature:.2f} °C")
                time.sleep(0.1)

            # Check for joystick input and send message if pressed
            if not joystick_center.value():
                ws.send(f"Joystick center pressed, Temperature alarm set to: {temperature_set:.2f} °C")
                LCD.fill_rect(208,15,30,30,LCD.blue)
                LCD.show()
                time.sleep(0.5)
                LCD.fill_rect(208,15,30,30,LCD.green)
                LCD.show()
                time.sleep(0.5)
                LCD.fill_rect(208,15,30,30,LCD.blue)
                LCD.show()
                time.sleep(0.5)
                LCD.fill_rect(208,15,30,30,LCD.green)
                LCD.show()
            elif not joystick_up.value():
                ws.send(f"Joystick up pressed, Temperature: {temperature:.2f} °C")
            elif not joystick_down.value():
                ws.send(f"Joystick down pressed, closing connection")
                LCD.fill_rect(208,15,30,30,LCD.blue)
                LCD.show()
                time.sleep(0.5)
                ws.close()
            elif not joystick_left.value():
                ws.send(f"Joystick left pressed, Temperature: {temperature:.2f} °C")
            elif not joystick_right.value():
                ws.send(f"Joystick right pressed, Temperature: {temperature:.2f} °C")

            # Try to receive a message from the WebSocket server
            try:
                response = ws.recv()
                if response:
                    if response == 1:
                        LCD.fill_rect(208,15,30,30,LCD.blue)
                        LCD.show()
                        time.sleep(0.5)
                        LCD.fill_rect(208,15,30,30,LCD.red)
                        LCD.show()
                        return
                        
                    print(f"Server response: {response}")
                    if response.startswith("Looks like winter is coming"):
                        LCD.fill_rect(208,75,30,30,LCD.blue)
                    elif response.startswith("Hello"):
                        LCD.fill_rect(208,75,30,30,LCD.green)
                        temperature_set = 30
                    else:
                        LCD.fill_rect(208,75,30,30,LCD.red)
                    
                    LCD.show()
                    time.sleep(1)
                    LCD.fill_rect(208,75,30,30,LCD.white)
                    LCD.rect(208,15,30,30,LCD.green)
                    LCD.show()
            except OSError:
                # No message received; ignore and continue looping
                pass

            # Small delay to reduce CPU usage
            time.sleep(0.1)

    finally:
        # Close the WebSocket connection on exit
        ws.close()
        print("WebSocket connection closed.")

if __name__ == "__main__":
    main()


