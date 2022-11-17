#!/usr/bin/env python3

"""
A class to put a simple service on the dbus, according to victron standards, with constantly updating
paths. See example usage below. It is used to generate dummy data for other processes that rely on the
dbus. See files in dbus_vebus_to_pvinverter/test and dbus_vrm/test for other usage examples.

To change a value while testing, without stopping your dummy script and changing its initial value, write
to the dummy data via the dbus. See example.

https://github.com/victronenergy/dbus_vebus_to_pvinverter/tree/master/test
"""
from asyncio import exceptions
import gettext
from webbrowser import get
from gi.repository import GLib
import dbus
import dbus.service
import platform
import argparse
import logging
import sys
import os
import minimalmodbus
import serial

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), './ext/velib_python'))
from vedbus import VeDbusService

#Variablen
softwareversion = '0.8'
serialnumber = '0000000000000000'
productname='TriRonXXXX'
hardwareversion = '00.00'
firmwareversion = '00.00'
connection = 'USB'
servicename = 'com.victronenergy.solarcharger.tty'
deviceinstance = 290    #VRM instanze
exceptionCounter = 0
state = [0,5,3,6]

if len(sys.argv) > 1:
    controller = minimalmodbus.Instrument(sys.argv[1], 1)
    servicename = 'com.victronenergy.solarcharger.' + sys.argv[1].split('/')[2]
else:
    sys.exit()

#controller = minimalmodbus.Instrument('/dev/ttyUSB0', 1)
controller.serial.baudrate = 115200
controller.serial.bytesize = 8
controller.serial.parity = serial.PARITY_NONE
controller.serial.stopbits = 1
controller.serial.timeout = 0.2
controller.mode = minimalmodbus.MODE_RTU
controller.clear_buffers_before_each_transaction = True



print(__file__ + " is starting up, use -h argument to see optional arguments")

class DbusEpever(object):
    def __init__(self, paths):
        self._dbusservice = VeDbusService(servicename)
        self._paths = paths

        _kwh = lambda p, v: (str(v) + 'kWh')
        _a = lambda p, v: (str(v) + 'A')
        _w = lambda p, v: (str(v) + 'W')
        _v = lambda p, v: (str(v) + 'V')
        _c = lambda p, v: (str(v) + '°C')

        logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))
        
        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._dbusservice.add_path('/Mgmt/ProcessVersion', softwareversion)
        self._dbusservice.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', 1)
        self._dbusservice.add_path('/ProductName', productname)
        self._dbusservice.add_path('/FirmwareVersion', firmwareversion)
        self._dbusservice.add_path('/HardwareVersion', hardwareversion)
        self._dbusservice.add_path('/Connected', 1)
        self._dbusservice.add_path('/Serial', serialnumber)
        self._dbusservice.add_path('/CustomName', None, writeable=True)

        self._dbusservice.add_path('/Link/NetworkMode', 0)
        self._dbusservice.add_path('/Link/NetworkStatus', 4)
        self._dbusservice.add_path('/Settings/BmsPresent', 0)
        #self._dbusservice.add_path('/Link/ChargeVoltage', 0)
        #self._dbusservice.add_path('/Link/ChargeCurrent', 10)
        #self._dbusservice.add_path('/Settings/ChargeCurrentLimit', None)     
        #self._dbusservice.add_path('/DeviceOffReason', 1)

        self._dbusservice.add_path('/Dc/0/Current', None, gettextcallback=_a)
        self._dbusservice.add_path('/Dc/0/Voltage', None, gettextcallback=_v)
        self._dbusservice.add_path('/Dc/0/Temperature', None, gettextcallback=_c)
        self._dbusservice.add_path('/State',None)
        self._dbusservice.add_path('/Pv/V', None, gettextcallback=_v)
        self._dbusservice.add_path('/Yield/Power', None, gettextcallback=_w)
        self._dbusservice.add_path('/Yield/User', None, gettextcallback=_kwh)
        self._dbusservice.add_path('/Load/State',None, writeable=True)
        self._dbusservice.add_path('/Load/I',None, gettextcallback=_a)
        self._dbusservice.add_path('/ErrorCode',0)
     

        self._dbusservice.add_path('/History/Daily/0/Yield', 0)
        self._dbusservice.add_path('/History/Daily/0/MaxPower',0)
        self._dbusservice.add_path('/History/Daily/1/Yield', 0)
        self._dbusservice.add_path('/History/Daily/1/MaxPower', 0)

        #self._dbusservice.add_path('/100/Relay/0/State', 1, writeable=True)
        
        GLib.timeout_add(1000, self._update)
        
    def _update(self):

        def getBit(num, i):
            return ((num & (1 << i)) != 0)

        global exceptionCounter
        try:
            c3100 = controller.read_registers(0x3100,18,4)
            c3200 = controller.read_registers(0x3200,3,4)
            c3300 = controller.read_registers(0x3300,20,4)
        except:
            print(exceptions)
            exceptionCounter +=1
            if exceptionCounter  >= 3:   
                exit()       
        else:
            exceptionCounter = 0
            if c3100[0] < 1:            #PV Voltage min 0.01 damit PV Current berechnet werden kann
                c3100[0] = 1

            self._dbusservice['/Dc/0/Voltage'] = c3100[4]/100
            self._dbusservice['/Dc/0/Current'] = (c3100[5]-c3100[9])/100.0
            self._dbusservice['/Dc/0/Temperature'] = c3100[16]/100
            self._dbusservice['/Pv/V'] = c3100[0]/100
            self._dbusservice['/Yield/Power'] =round((c3100[2] | c3100[3] << 8)/100)
            self._dbusservice['/Load/I'] = c3100[13]/100
            self._dbusservice['/State'] = state[getBit(c3200[1],3)* 2 + getBit(c3200[1],2)]
            self._dbusservice['/Load/State'] = c3200[2]
            self._dbusservice['/Yield/User'] =(c3300[18] | c3300[19] << 8)/100
            self._dbusservice['/History/Daily/0/Yield'] =(c3300[12] | c3300[13] << 8)/100
            
            if self._dbusservice['/Yield/Power'] > self._dbusservice['/History/Daily/0/MaxPower']:
                self._dbusservice['/History/Daily/0/MaxPower'] = self._dbusservice['/Yield/Power']

        return True




def main():
    logging.basicConfig(level=logging.DEBUG)

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    epever = DbusEpever(paths = None)

    logging.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()