#! /usr/bin/python
# -*- coding: utf-8 -*-
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

#   Xbee to MQTT gateway
#   Copyright (C) 2012 by Xose Pérez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

__author__ = "Xose Pérez"
__contact__ = "xose.perez@gmail.com"
__copyright__ = "Copyright (C) 2013 Xose Pérez"
__license__ = 'GPL v3'

import os
import re
import glob
import time
import binascii
import logging
from xbee import ZigBee as XBee

class XBeeWrapper(object):
    """
    Helper class for the python-xbee module.
    It processes API packets into simple address/port/value groups.
    See https://python-xbee.readthedocs.io/
    """

    default_port_name = 'serial'

    serial = None
    xbee = None
    logger = None

    sample_rate = 0
    change_detection = False

    _change_detection_masks = {}

    buffer = dict()

    def errorlog(self, e):
        logging.exception(e)

    def log(self, level, message):
        if self.logger:
            self.logger.log(level, message)

    def disconnect(self):
        """
        Closes serial port
        """
        self.xbee.halt()
        self.serial.close()
        return True

    def connect(self):
        """
        Creates an Xbee instance
        """
        try:
            self.log(logging.INFO, "Connecting to Xbee")
            self.xbee = XBee(self.serial, callback=self.process, error_callback=self.errorlog)
        except:
            return False
        return True

    def process(self, packet):
        """
        Processes an incoming packet, supported packet frame ids:
            0x90: Zigbee Receive Packet (rx)
            0x92: ZigBee IO Data Sample Rx Indicator (rx_io_data_long_addr)
            0x95: ZigBee Node Identification Indicator (node_id_indicator)
            0x88: ZigBee AT Command Response (at_response)
            0x97: ZigBee Remote Command Response (remote_at_response)
        """

        self.log(logging.DEBUG,  "xbee-wrapper.process - packet:%s"%( packet))

        try:
            address = binascii.hexlify(packet['source_addr_long'])
        except:
            pass

        id = packet.get('id', None)

        # Data sent through the serial connection of the remote radio
        if (id == "rx"):

            # Some streams arrive split in different packets
            # we buffer the data until we get an EOL
            self.buffer[address] = self.buffer.get(address,'') + packet['rf_data']
            count = self.buffer[address].count('\n')
            self.log(logging.DEBUG, "xbee-wrapper.process (rx) count: %s " % (count))
            if (count):
                lines = self.buffer[address].splitlines()
                try:
                    self.buffer[address] = lines[count:][0]
                    self.log(logging.DEBUG, "xbee-wrapper(rx) ---try :lines[count:][0]: %s " % (lines[count:][0]))
                except:
                    self.buffer[address] = ''
                for line in lines[:count]:
                    line = line.rstrip()
                    try:
                        port, value = line.split(':', 1)
                    except:
                        value = line
                        port = self.default_port_name
                        self.log(logging.DEBUG, "xbee-wrapper(rx) ---except :line: %s port: %s value:%s" % (line, port, value))
                    self.log(logging.DEBUG, "xbee-wrapper(rx) line: %s port: %s value:%s" % (line, port, value))
                    self.on_message(address, port, value)

        # Data received from an IO data sample
        elif (id == "rx_io_data_long_addr"):
            for sample in packet['samples']:
                for port, value in sample.iteritems():
                    if port[:4] == 'dio-':
                        value = 1 if value else 0
                    self.on_message(address, port, value)

        # Node Identification Indicator received
        elif (id == "node_id_indicator"):
            self.log(logging.DEBUG, "xbee-wrapper(rx node_id_indicator) packet:%s"%( packet))
            alias = packet.get('node_id', None)
            self.on_identification(address, alias)

        # Response received after a local command request
        elif (id == "at_response"):
            status = packet.get('status', None)
            command = packet.get('command', None)
            response = packet.get('parameter', None)
            self.on_response(status, command, response, "local")

        # Response received after a remote command request
        elif (id == "remote_at_response"):
            status = packet.get('status', None)
            command = packet.get('command', None)
            response = packet.get('parameter', None)
            self.on_response(status, command, response, address)

    def on_identification(self, address, alias):
        """
        Hook for node identification message.
        """
        None

    def on_node_discovery(self, address, alias):
        """
        Hook for node discovery
        """
        None

    def on_response(self, status, command, response, address):
        """
        Hook for command responses.
        """
        if (status == '\x00'):
            status_msg = "OK"
        elif (status == '\x01'):
            status_msg = "ERROR"
        elif (status == '\x02'):
            status_msg = "Invalid Command"
        elif (status == '\x03'):
            status_msg = "Invalid Parameter"
        elif (status == '\x04'):
            status_msg = "Tx Failure"
        else:
            status_msg = "Unknown"

        self.log(logging.INFO,
            "AT response for command: %s, status: %s" % (command, status_msg)
        )

        if (status != '\x00'):
            return

        # Process Node Discovery Command
        if (command == 'ND'):
            alias = response['node_identifier']
            address = binascii.hexlify(response['source_addr_long'])

            self.log(logging.DEBUG, "Setting IO Sample Rate to %s seconds for address %s" % (self.sample_rate, address))

            milliseconds = str(hex(self.sample_rate * 1000))[2:]
            milliseconds = '0' * (len(milliseconds) % 2) + milliseconds
            milliseconds = binascii.unhexlify(milliseconds)
            source_addr_long = response['source_addr_long']
            self.xbee.remote_at(dest_addr_long = source_addr_long, command = 'IR', parameter = milliseconds)

            self.on_node_discovery(address, alias)

        # Update IO Digital Change Detection mask
        elif (command == 'IC'):
            current_mask = int(binascii.hexlify(response), 16)
            new_mask = self._change_detection_masks.get(address, current_mask)
            if self.change_detection and current_mask != new_mask:
                self.log(logging.DEBUG,
                     "Applying new IC mask to address: %s, value: %s" % (address, '{:012b}'.format(new_mask))
                )
                new_mask = str(hex(new_mask))[2:]
                new_mask = '0' * (len(new_mask) % 2) + new_mask
                new_mask = binascii.unhexlify(new_mask)
                source_addr_long = binascii.unhexlify(address)
                self.xbee.remote_at(dest_addr_long = source_addr_long, command = 'IC', parameter = new_mask)
                self.xbee.remote_at(dest_addr_long = source_addr_long, command = 'WR')

        # Process retrieved pin status
        elif (re.match('[DP]\d', command)):
            prefix, number = command[:1], command[1:]
            port = 'pin-1%s' % number if (prefix == 'P') else 'pin-%s' % number
            value = int(binascii.hexlify(response), 16)
            self.on_message(address, port, value)
        else:
            self.log(logging.WARNING, "Command response (%s) not implemented." % command)

    def on_message(self, address, port, value):
        """
        Hook for outgoing messages.
        """
        None

    def send_query(self, address, ports = None):
        """
        Request current configuration of given ports
        """
        if ports is None:
            ports = [ "pin-%s" % x for x in range(13) ]

        if not isinstance(ports, list):
            ports = [ports]

        self.log(logging.INFO, "Request configuration for %s at %s" % (ports, address))
        address = binascii.unhexlify(address)

        for port in ports:

            if port[:4] not in [ 'adc-', 'dio-', 'pin-' ]:
                continue

            number = int(port[4:])

            command = 'P%d' % (number - 10) if number>9 else 'D%d' % number
            self.xbee.remote_at(dest_addr_long = address, command = command, frame_id="A")
            time.sleep(1)

    def send_message(self, address, port, value, permanent = True):
        """
        Sends a message to a remote radio
        Currently, this only supports setting a digital output pin LOW (4) or HIGH (5)
        and setting a raw configuration for any pin of remote radio.
        """
        self.log(logging.DEBUG,
            "Sending message to address: %s, port: %s, value: %s" % (address, port, value)
        )

        try:

            prefix = port[:4]
            if prefix in ['dio-', 'pin-']:
                address = binascii.unhexlify(address)
                number = int(port[4:])
                command = 'P%d' % (number - 10) if number>9 else 'D%d' % number
                value = int(value) % 10 if prefix == 'pin-' else (int(value) > 0) + 4
                value = binascii.unhexlify('0' + str(value))
                self.xbee.remote_at(dest_addr_long = address, command = command, parameter = value)
                self.xbee.remote_at(dest_addr_long = address, command = 'WR' if permanent else 'AC')
                self.xbee.remote_at(dest_addr_long = address, command = command, frame_id = 'A')
                if self.change_detection:
                    address = binascii.hexlify(address)
                    self.issue_change_detection(address, port, value == '\x03')

                return True
        except:
            pass

        return False

    def issue_change_detection(self, address, port, enabled = True):
        """
        Sends IC command to check the response and change if it differs
        """
        self.log(logging.DEBUG,
            "Sending IC command to address: %s, port: %s, enabled: %s" % (address, port, enabled)
        )
        offset = int(port[4:]) % 12
        mask = int(self._change_detection_masks.get(address, 0))
        if enabled:
            self._change_detection_masks[address] = mask | 1 << offset
        else:
            self._change_detection_masks[address] = mask & ~(1 << offset)

        address = binascii.unhexlify(address)
        self.xbee.remote_at(dest_addr_long = address, command = 'IC', frame_id = 'A')

    def find_devices(self, vendor_id = None, product_id = None):
        """
        Looks for USB devices
        optionally filtering by with the provided vendor and product IDs
        """
        devices = []

        for dn in glob.glob('/sys/bus/usb/devices/*'):
            try:
                vid = int(open(os.path.join(dn, "idVendor" )).read().strip(), 16)
                pid = int(open(os.path.join(dn, "idProduct")).read().strip(), 16)
                if ((vendor_id is None) or (vid == vendor_id)) and ((product_id is None) or (pid == product_id)):
                    dns = glob.glob(os.path.join(dn, os.path.basename(dn) + "*"))
                    for sdn in dns:
                        for fn in glob.glob(os.path.join(sdn, "*")):
                            if  re.search(r"\/ttyUSB[0-9]+$", fn):
                                devices.append(os.path.join("/dev", os.path.basename(fn)))
                            pass
                        pass
                    pass
                pass
            except ( ValueError, TypeError, AttributeError, OSError, IOError ):
                pass
            pass

        return devices

