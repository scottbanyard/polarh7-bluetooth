import sys
sys.dont_write_bytecode = True

import pyble
from pyble.handlers import PeripheralHandler, ProfileHandler
import time
import struct
import threading

# MAC ADDRESS of Polar H7: A0-9E-1A-2D-04-CD

# Global Variables
firebaseHandler = ""
finishedRecording = False
testConnection = False
rr_intervals_backup = []

class HR(ProfileHandler):
    """ Setup profile for Bluetooth Heart Rate Service, which holds the characteristics
        of the HR measurement and the sensor body location

        :returns:
            Nothing
    """

    # UUID of HR service
    UUID = "0000180d-0000-1000-8000-00805f9b34fb"

    # Some reason DefaultProfileHandler is picked instead of this, so overwrite their UUID (current solution)
    UUID = "*"
    _AUTOLOAD = True

    # Characteristics of HR Service
    names = {
        "0000180d-0000-1000-8000-00805f9b34fb": "Polar H7 Profile",
        "00002a37-0000-1000-8000-00805f9b34fb": "Heart Rate",
        "00002a38-0000-1000-8000-00805f9b34fb": "Body Location"
    }

    def on_read(self, characteristic, data):
        """ Parse hex into a data array

            :returns:
                Data array of hex
        """
        ans = []
        for b in data:
            ans.append("0x%02X" % ord(b))
        return ans


    def on_notify(self, characteristic, data):
        """ Hook that is called every notification, reads data from chest strap.
            Reading of 0x04 and 0x06 indicate that strap isn't providing valid data.
            Reading of 0x16 means that strap is working correctly.

            :returns:
                Nothing
        """
        global testConnection
        global finishedRecording
        result = self.on_read(characteristic, data)
        print(result)
        # If testing connection, ensure strap is secure and valid data is being retrieved
        if testConnection:
            if result[0] == "0x04" or result[0] == "0x06":
                print("Polar Chest Strap is not tightened or the strap needs moisture.")
            elif result[0] == "0x16":
                print("Strap is working!")
                testConnection = False
        # Else if recording is still conitinuing, push result to Firebase
        elif finishedRecording == False:
            (hr, rr_intervals) = self.split_result(result)
            print (hr, rr_intervals)
            for rr in rr_intervals:
                rr_intervals_backup.append(rr)
            # Start Firebase upload thread
            # rr_upload_thread = RRUploader(upload_rr, (hr, rr_intervals))
            # rr_upload_thread.start()

    def split_result(self, data):
        """ Data received is formed as such: 0x16 HR (RR RR)+, found
            For example, 0x16 0x53 0x16 0x03, where:
                HR (UINT8) = 0x53 in decimal is 83 BPM.
                RR-interval (UINT16) = 0x16 0x03 swapped = 0x0316 in decimal is 790ms.
                RR-intervals are a resolution of 1/1024 second, thus 790/1024 = 0.7715 seconds = 772ms.

            Some packets come with extra RR-intervals e.g. 0x16 0x53 0x16 0x03 0xE4 0x02

            :returns:
                Tuple of HR and list of RR-intervals
        """
        # RR-interval pair indices (never have seen 6, 7 but just in case)
        indices = [(2, 3), (4, 5), (6, 7), (8, 9)]
        rr_intervals = []
        # Heart Rate (bpm) converted from hex to decimal
        hr = int(data[1], 16)
        try:
            # Go through possible number of RR-intervals in the data packet
            for index_tuple in indices:
                # Swap 3rd and 2nd hex and combine
                rr_hex = data[index_tuple[1]] + data[index_tuple[0]].split('0x')[1]
                # Convert to decimal and divide by 1024, the convert to milliseconds
                rr_interval = (int(rr_hex, 16) / 1024.0) * 1000
                rr_intervals.append(rr_interval)
        except:
            pass
        return (hr, rr_intervals)


class RRUploader(threading.Thread):
    """ Setup RR-interval uploader that will push intervals to Firebase in another thread
        so it can keep receiving notifications from the Polar H7

        :returns:
            Nothing
    """

    def __init__(self, target, *args):
        self._target = target
        self._args = args
        threading.Thread.__init__(self)

    def run(self):
        self._target(*self._args)

def upload_rr(tuple):
    """ Pushes each rr_interval in real-time to Firebase

        :returns:
            Nothing
    """
    (hr, rr_intervals) = tuple
    for rr in rr_intervals:
        firebaseHandler.save_rr_interval(rr)
        firebaseHandler.save_hr(hr)
        # firebaseHandler.save_calculated_hr(int(60 / rr))

class Peripheral(PeripheralHandler):
    """ Setup peripheral handler for Bluetooth Polar H7 Chest Strap

        :returns:
            Nothing
    """

    def initialize(self):
        self.addProfileHandler(HR)
        print(self.profile_handlers)

    def on_connect(self):
        print(self.peripheral, "connect")

    def on_disconnect(self):
        print(self.peripheral, "disconnect")

    def on_rssi(self, value):
        print(self.peripheral, " update RSSI:", value)

class PolarH7:

    def startPolarConnection(self):
        print("Starting Polar H7 connection...")
        """ Start the Polar H7 connection process and only proceed once connected
            properly

            :returns:
                Nothing
        """
        global testConnection
        testConnection = True
        self.cm, self.p = self.connectToPolarH7()
        self.setNotifyOfHR(True)
        while testConnection:
            pass

    def startPolarRecording(self, duration=None):
        """ Start the RR-interval recordings

            :returns:
                Nothing
        """
        # Keep Python program running so notifications are read - if duration not defined, run forever
        if duration == None:
            self.cm.loop()
            print("Printing locally stored (in variable) RR intervals.")
            print(rr_intervals_backup)
        else:
            global finishedRecording
            finishedRecording = False
            print("Starting recording!")
            self.cm.loop(duration=duration)
            finishedRecording = True
            print("Finished recording!")

    def connectToPolarH7(self):
        """ Initialise a Bluetooth Low Energy Central Manager, continuously scan
            for Polar H7 chest strap, and connect to this peripheral

            :returns:
                cm - Bluetooth Low Energy Central Manager
                p  - Polar H7 Peripheral
        """
        self.cm = pyble.CentralManager()
        if not self.cm.ready:
            return
        self.target = None
        while True:
            try:
                self.target = self.cm.startScan(withServices=["180D"])
                if self.target and "Polar" in self.target.name:
                    print(self.target)
                    break
            except Exception as e:
                print(e)
        self.target.delegate = Peripheral
        self.p = self.cm.connectPeripheral(self.target)
        self.battery_level = self.get_battery_level()
        return self.cm, self.p

    def get_battery_level(self):
        """ Uses Battery Service (180F) to get the Battery Level characteristic
            value (2A19) and converts hex to int

            :returns:
                Battery Level
        """
        for service in self.p:
            if service.UUID == "180F":
                for c in service:
                    if c.UUID == "2A19":
                        self.battery_level = str(int(c.value[0], 16))
                        print("Battery Level: " + self.battery_level + "%")
                        return self.battery_level

    def setNotifyOfHR(self, boolean):
        """ If boolean : True
            Sets NOTIFY to True for Heart Rate Measurement characteristic to get real-time
            data. According to the specification of the characteristic, notifications are
            mandatory.
            If boolean : False
            Turning off NOTIFY as values still come in after cm.loop duration has finished.

            :returns:
                Nothing
        """
        for service in self.p:
            for c in service:
                # UUID of HR Measurement characteristic is 2A37
                if c.UUID == "2A37":
                    c.notify = boolean


def main():
    p = PolarH7()
    p.connectToPolarH7()
    p.setNotifyOfHR()
    # Keep Python program running so notifications are read
    p.cm.loop()

if __name__ == "__main__":
    main()
