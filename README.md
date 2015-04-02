SensorTagRead
=============

Block (and supporting library) for discovering, connecting to, and reading from TI SensorTags.

SenorTags are read from, and the block notifies a signal, each time a signal is processed by SensorTagRead.

*keypress* can be turned on to read button presses from the SensorTag. Note that a SensorTag can not be configured to use *keypress* if other sensors are also being used. Any input signal into the block will break the block if *keypress* is enabled.

**NOTA BENE:** This block require root/sudo access when using 'scan'. Instead of `run_nio`, use `sudo run_nio` when starting an instance which contains a service making use of SensorTagRead.

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
4. Bring up the local Bluetooth interface:

        $ sudo hciconfig hci0 up
        $ sudo hciconfig hci0 leadv 3
        $ sudo hciconfig hci0 piscan
        
5. Build **bluepy**:

        $ cd /path/to/sensor_tag/bluepy/bluepy
        $ sudo make
        
And you're ready to rock. You'll find the usual block documentation below.

## Method to connect to SensorTag and configure the SensorTagRead block in the Service Builder

Steps **A** and **B** must be done during a reboot/power cycle of the Raspberry Pi. Step **C** is neccesary every time you start a service using a SensorTag.

### A) Configuring Bluetooth Adapter

By default, the Raspberry Pi will not have it's Blue Tooth adapter on. To enable it, you must cycle the Blue Tooth adapter using the following commands in the command line:

        $ sudo hciconfig hci0 down
        $ sudo hciconfig hci0 up
        $ sudo hciconfig hci0 leadv 3
        $ sudo hciconfig hci0 piscan

### B) Finding SensorTag using Bluetooth advertise and discovery

The next step will help with obtaining the MAC address of the Sensor Tag. It is neccesary to verify that the Raspberry Pi can find the Sensor Tag first. Steps 1 and 2 will accomplish this:

1. Press the side button to enter into 'advertising' mode, it will stay in this mode for 30 seconds after being pressed.
2. In the command line, enter the following:
        
        $ sudo hcitool lescan

In the command line, you should now see a list of MAC addresses, one of which will be followed by 'sensortag' - **_this is the MAC address you will need for configuring the Sensor Tag block in the Address field_**.

**_Note:_** If you fail to see a MAC address show up with 'sensortag' following it

1. It is possible that the 30 second window has elapsed from pressing the button, to performing the 'lescan'
  1. Repeat steps 1 and 2 above, making sure to perform both within a 30 second window or less.
2. It is possible that the battery in the Sensor Tag is dead
  1. Replace the CR2032 battery in the SensorTag with a new one.
3. Beyond this - [resort to the manual from Texas Instruments](http://www.ti.com/lit/ml/swru324b/swru324b.pdf)

### C) Configuring Service builder, and performing HTTP connect command

In the service builder, drag a **SensorTagRead** block onto the workspace. The **Address** field will be filled in with the MAC address you recorded in step **B**. Configure the block to record any data parameter you want by selecting them. After saving the block and service proceed to the following steps.

1. Start service
2. After succesful start (and within 3 seconds of eachother)
  1. press *Advertise* button on the side of the SensorTag
  2. visit the following URL in browser: http://[[NIOHOST]]:[[NIOPORT]]/services/{{service_name}}/{{block_name}}/connect
    * [[NIOHOST]] - the Rasperry Pi's service builder IPv4 Address
    * [[NIOPORT]] - the port the service builder is open to - *usually 8181 by default*.
    * {{service_name}} - the service name in which the **SensorTagRead** block is in.
    * {{block_name}} - the name given to the **SensorTagRead** block being configuring right now.
    * An example is as follows: http://192.168.100.72:8181/services/BlueTooth_SensorTag/Test1/connect 

If succesful, you should see the output of the sensor tag show up in a log (assuming you are running the output of the **SensorTagRead** block into a logger). If you do not see anything showing up in the log, repeat steps 2-1 and 2-2 again. If you do not see anything showing up in the logger block try the following steps:

1. Make sure the MAC address entered in the **SensorTagRead** block matches the MAC address of the SensorTag itself. 
2. Press the *Advertise* a few more times.
3. Restart service, and proceed to steps 2-1 and 2-2 again.

## Bring up Bluetooth when starting Raspberry Pi

The easiest way to automatically bring up Bluetooth when booting the Raspberry Pi is to modify `/etc/rc.local`.

```
# Start Bluetooth
sudo hciconfig hci0 down
sudo hciconfig hci0 up
```

Properties
----------

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
            
-   **default_metadata**: SensorTag metadata object which will be any for any SensorTags discovered after block configuration.

-   **scan_length**: IntProperty that controls the length of each device scan.


Dependencies
------------

-   [bluez](bluez.org/download)
-   [bluepy](github.com:nio-blocks/bluepy.git)

Commands
--------
-   **scan**: Scan for (advertising) SensorTags within range. Before initiating a scan, it is a good idea to hit the side button on each of the SensorTags you want to discover; this tells the Tag device to start broadcasting its unique identification data, making it available for discovery. Discovered SensorTags are named iteratively based on the number of SensorTags already in the system (i.e. SensorTag-0, SensorTag-1, etc).
-   **connect**: Connect to all discovered/configured SensorTag devices and schedule readings based on configured/default values.
-   **scan_and_connect**: Perform both of the above actions, synchronously.
-   **tag_config**: Add a SensorTag to the list of connectable devices. Alternatively, this command can be used to update the configuration of a device already in the system. Parameters:
    * **address**: The MAC address of the SensorTag in question.
    * **name**: Arbitrary name. For your reference.
    * **seconds**: An integer representing the read interval (in seconds).
    * **sensors**: A list of sensors (strings) to read from. Should be taken from the list above. Case sensitive.
-   **list**: Return a list of all the SensorTags currently loaded in the block.

Input
-----
Sensor reads are triggered by every input signal.

Output
------
A signal for each SensorTag reading. Here's an example, for reference:

    {
        "sensor_tag_name": "SensorTag-0",
        "sensor_tag_address": "B4:99:4C:64:30:9F",
        "IRtemperature": { <data> },
        "gyroscope": { <data> },
    }

Keypress:

* button: "Left button", "Right button", or "Both Buttons"
* direction: "up" or "down

    {
        "button": "Left button",
        "direction": "down",
    }



