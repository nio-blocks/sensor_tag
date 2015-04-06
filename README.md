SensorTagRead
=============

Block (and supporting library) for discovering, connecting to, and reading from TI SensorTags.

SenorTags are read from, and the block notifies a signal, each time a signal is processed by SensorTagRead.

*keypress* can be turned on to read button presses from the SensorTag. Note that a SensorTag can not be configured to use *keypress* if other sensors are also being used. Any input signal into the block will break the block if *keypress* is enabled.

## Bluetooth Setup

This block makes use of our fork of **bluepy**, a Python library which makes Pythonic communication with Bluetooth Low Energy devices transparent and smooth. Due to some limitations of the Linux bluetooth stack, direct communication with BLE devices is accomplished via a monolithic C executable which pipes data into our Python programs. Furthermore, **bluepy** is built for Linux (specifically targeting Raspberry Pi), so don't expect it to play nice with either the OSX or Windows Bluetooth infrastructure.

Users of this block should follow the following steps to get everything up and running:

Install bluetooth and bring up local device:

1. Make sure supporting libraries are installed:

        $ sudo apt-get install libusb-dev libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev
    
2. Install bluez:

        $ sudo mkdir bluez ; cd bluez
        $ sudo wget www.kernel.org/pub/linux/bluetooth/bluez-5.24.tar.xz
        $ sudo unxz bluez-5.24.tar.xz
        $ cd bluez-5.24
        $ sudo ./configure --disable-systemd
        $ sudo make
        $ sudo make install
 
3. If your linux computer has a built-in bluetooth device, you may skip this step. Shut down the computer with `sudo shutdown -h now`, insert your USB Bluetooth dongle, and power up the computer.

4. Bring up the local Bluetooth interface. The following command needs to be executed every time the Raspberry Pi is rebooted. Add this line to `/etc/rc.local` for it to happen automatically on system startup:

        $ sudo hciconfig hci0 up

5. Build **bluepy**. Any time you update your block, this step needs to be run again if any changes were made to bluepy:

        $ cd /path/to/sensor_tag/bluepy/bluepy
        $ sudo make
        
And you're ready to rock. You'll find the usual block documentation below.

### Finding SensorTag using Bluetooth advertise and discovery

The next step will help with obtaining the MAC address of the Sensor Tag. It is neccesary to verify that the Raspberry Pi can find the Sensor Tag first. Steps 1 and 2 will accomplish this:

1. In the command line, enter the following:
        
        $ sudo hcitool lescan

2. Press the side button to enter into 'advertising' mode, it will stay in this mode for 30 seconds after being pressed.

In the command line, you should now see a list of MAC addresses, one of which will be followed by 'SensorTag' - **_this is the MAC address you will need for configuring the Sensor Tag block in the Address field_**.

**_Note:_** If you fail to see a MAC address show up with 'sensortag' following it

1. It is possible that the 30 second window has elapsed from pressing the button, to performing the 'lescan'
  1. Repeat steps 1 and 2 above, making sure to perform both within a 30 second window or less.
2. It is possible that the battery in the Sensor Tag is dead
  1. Replace the CR2032 battery in the SensorTag with a new one.
3. Beyond this - [resort to the manual from Texas Instruments](http://www.ti.com/lit/ml/swru324b/swru324b.pdf)

Properties
-----------

-   **device_info**: A list of SensorTag configuration objects, which contain the following fields:   
    * **address**: The MAC address of the SensorTag device.
    * **meta**: SensorTag metadata object, containing the following fields:
        + **name**: Arbitrary human-readable name of the device. For your reference.
        + **sensors**: A list of BoolProperties corresponding to the each of the sensors on the SensorTag:
            * **IRtemperature**
            * **accelerometer**
            * **humidity**
            * **magnetometer**
            * **barometer**
            * **gyroscope**
            * **keypress**

Dependencies
------------

-   [bluez](bluez.org/download)
-   [bluepy](github.com:nio-blocks/bluepy.git)

Commands
--------

None

Input
-----

Input signals trigger the sensor reads. One signal will be notified for each input signals for each connected SensorTag.

Output
------

### default

A signal for each SensorTag reading. Here's an example, for reference:

    {
        "sensor_tag_name": "SensorTag-0",
        "sensor_tag_address": "B4:99:4C:64:30:9F",
        "IRtemperature": { <data> },
        "gyroscope": { <data> },
    }

### keypress

* button: "Left", "Right", or "Both"
* direction: "Up" or "Down"

    {
        "button": "Left",
        "direction": "Down",
    }
