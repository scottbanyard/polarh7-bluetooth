# Polar H7 Bluetooth Handler

Written in Python. Connects to a Polar H7 chest strap using Bluetooth Low Energy (BLE). Transfers heartbeat & RR interval data in real-time.

Within the source code, Firebase uploads are commented out. These can be uncommented back in if necessary - each result in real-time is pushed to Firebase using threading.

## Installation

- Pull / clone this repository.
- Install Python2.7 and install the `pyble` module using pip, i.e. `pip install pyble`.
- Ensure your Bluetooth is turned on your laptop / PC, and run `python2.7 polarhandler.py`.
- Tip: to ensure the Polar H7 chest strap is active, conduct the electrodes with some water.
- Results of each heartbeat and RR intervals should print out once connected.
