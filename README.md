SensorTagRead
==========

Block (and supporting library) for discovering, connecting to, and reading from TI SensorTags.

**NOTA BENE:** This block require root/sudo access. Instead of `run_nio`, use `sudo run_nio` when starting an instance which contains a service making use of SensorTagRead.

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


Properties
--------------

-   **device_info**: A list of SensorTag configuration objects, which contain the following fields:   
    * **address**: The MAC address of the SensorTag device.
    * **meta**: SensorTag metadata object, containing the following fields:
        + **name**: Arbitrary human-readable name of the device. For your reference.
        + **read_interval**: TimeDeltaProperty. Read this Tag at this interval.
        + **sensors**: A list of BoolProperties corresponding to the each of the sensors on the SensorTag:
            * **IRtemperature**
            * **accelerometer**
            * **humidity**
            * **magnetometer**
            * **barometer**
            * **gyroscope**
            
-   **default_metadata**: SensorTag metadata object which will be any for any SensorTags discovered after block configuration.

-   **scan_length**: IntProperty that controls the length of each device scan.


Dependencies
----------------

-   [bluez](bluez.org/download)
-   [bluepy](github.com:nio-blocks/bluepy.git)

Commands
----------------
-   **scan**: Scan for (advertising) SensorTags within range. Before initiating a scan, it is a good idea to hit the side button on each of the SensorTags you want to discover; this tells the Tag device to start broadcasting its unique identification data, making it available for discovery. Discovered SensorTags are named iteratively based on the number of SensorTags already in the system (i.e. SensorTag-0, SensorTag-1, etc).
-   **connect**: Connect to all discovered/configured SensorTag devices and schedule readings based on configured/default values.
-   **scan_and_connect**: Perform both of the above actions, synchronously.
-   **tag_config**: Add a SensorTag to the list of connectable devices. Alternatively, this command can be used to update the configuration of a device already in the system. Parameters:
    * **address**: The MAC address of the SensorTag in question.
    * **name**: Arbitrary name. For your reference.
    * **seconds**: An integer representing the read interval (in seconds).
    * **sensors**: A list of sensors (strings) to read from. Should be taken from the list above. Case sensitive.
-   **reschedule**: Cancel existing read jobs and reschedule them. Can be done at any time, but is especially useful when one of the SensorTags fails or is disconnected.
-   **list**: Return a list of all the SensorTags currently loaded in the block.

Input
-------

None

Output
---------
A signal for each SensorTag reading. Here's an example, for reference:

    {
        "sensor_tag_name": "SensorTag-0",
        "sensor_tag_address": "B4:99:4C:64:30:9F",
        "IRtemperature": { <data> },
        "gyroscope": { <data> },
    }




