from threading import Lock
from time import sleep
from bluepy.sensortag import SensorTag
from bluepy.sensortag import KeypressDelegate as _KeypressDelegate
from bluepy.btle import BTLEException

from nio.block.base import Block
from nio.block.terminals import output
from nio.signal.base import Signal
from nio.properties import PropertyHolder, ObjectProperty, ListProperty, \
    StringProperty, BoolProperty, VersionProperty
from nio.util.threading.spawn import spawn

SENSOR_MAPPINGS = {
    'IRTemperatureSensor': 'IRtemperature',
    'AccelerometerSensor': 'accelerometer',
    'HumiditySensor': 'humidity',
    'MagnetometerSensor': 'magnetometer',
    'BarometerSensor': 'barometer',
    'GyroscopeSensor': 'gyroscope',
    'KeypressSensor': 'keypress',
    'AccelerometerSensorMPU9250': 'accelerometer',
}

AVAIL_SENSORS = {
    'IRtemperature': ['ambient_temp_degC', 'target_temp_degC'],
    'accelerometer': ['x_accel_g', 'y_accel_g', 'z_accel_g'],
    'humidity': ['ambient_temp_degC', 'relative_humidity'],
    'magnetometer': ['x_uT', 'y_uT', 'z_uT'],
    'barometer': ['ambient_temp_degC', 'pressure_millibars'],
    'gyroscope': ['x_deg_per_sec', 'y_deg_per_sec', 'z_deg_per_sec'],
    'keypress': []
}


class Sensors(PropertyHolder):
    IRtemperature = BoolProperty(title="IR Temperature", default=True)
    accelerometer = BoolProperty(title="Accelerometer", default=False)
    humidity = BoolProperty(title="Humidity", default=False)
    magnetometer = BoolProperty(title="Magnetometer", default=False)
    barometer = BoolProperty(title="Barometer", default=False)
    gyroscope = BoolProperty(title="Gyroscope", default=False)
    keypress = BoolProperty(title="Keypress", default=False)


class SensorTagMeta(PropertyHolder):
    name = StringProperty(title='Name (human readable)', default='SensorTag')
    sensors = ObjectProperty(Sensors, title="Sensors", default=Sensors())


class SensorTagInfo(PropertyHolder):
    address = StringProperty(title='Device Address', default='')
    meta = ObjectProperty(
        SensorTagMeta, title="Sensors", default=SensorTagMeta())


class KeypressDelegate(_KeypressDelegate):
    """ Handle SensorTag button presses """

    BUTTON_L = 0x02
    BUTTON_R = 0x01
    ALL_BUTTONS = (BUTTON_L | BUTTON_R)

    _button_desc = {
        BUTTON_L: "Left",
        BUTTON_R: "Right",
        ALL_BUTTONS: "Both"
    }

    def __init__(self, logger, notify_signals):
        super().__init__()
        self.logger = logger
        self.notify_signals = notify_signals

    def onButtonUp(self, but):
        self.logger.debug("** " + self._button_desc[but] + " UP")
        self.notify_signals(
            [Signal({'button': self._button_desc[but], 'direction': 'Up'})],
            output_id='keypress'
        )

    def onButtonDown(self, but):
        self.logger.debug("** " + self._button_desc[but] + " DOWN")
        self.notify_signals(
            [Signal({'button': self._button_desc[but], 'direction': 'Down'})],
            output_id='keypress'
        )


@output("status")
@output("keypress")
@output("sensors")
class SensorTagRead(Block):

    device_info = ListProperty(SensorTagInfo, title="Sensor Tag Config")
    version = VersionProperty("1.0.0")

    def __init__(self):
        super().__init__()
        self._configs = {}
        self._tags = {}
        self._read_lock = Lock()

    def configure(self, context):
        super().configure(context)
        self._read_counter = 0
        for dev_info in self.device_info():
            self._configs[dev_info.address()] = \
                self._cfg_from_device_info(dev_info)

    def _cfg_from_device_info(self, device_info):
        return {
            'address': device_info.address(),
            'name': device_info.meta().name(),
            'sensors': {
                sensor: getattr(device_info.meta().sensors(), sensor)()
                for sensor in AVAIL_SENSORS
            }
        }

    def process_signals(self, signals, input_id='default'):
        self.logger.debug('Processing Signals: {}'.format(len(signals)))
        for signal in signals:
            for addy in self._tags:
                self._read_from_tag(addy)

    def start(self):
        super().start()
        self.connect()

    def stop(self):
        super().stop()

    def connect(self):
        connecting_to = []
        for addr in self._configs:
            if addr not in self._tags:
                connecting_to.append(addr)
                spawn(self._connect_tag, self._configs[addr])
        return connecting_to

    def _connect_tag(self, cfg, read_on_connect=False):
        addy = cfg["address"]
        name = cfg["name"]
        try:
            self.logger.info("Push {} side button NOW".format(name))
            self.logger.info("Connecting to device {}".format(addy))
            self._notify_status_signal('Connecting', addy)
            tag = SensorTag(addy)
            self._enable_sensors(addy, tag)
            # Save the tag to the list after connection and sensors enabled.
            self._tags[addy] = tag
        except Exception as e:
            self.logger.exception(
                "Failed to connect to {} ({}). Retrying...".format(name, addy))
            self._notify_status_signal('Retrying', addy)
            # Make sure to remove tag if connect fails
            self._tags.pop(addy, None)
            sleep(5)
            self._connect_tag(cfg)
        else:
            self.logger.info("Connected to device {}".format(addy))
            self._notify_status_signal('Connected', addy)
            self._read_counter = 0
            if cfg["sensors"].get('keypress', False):
                self.logger.info(
                    "Enabling notification listening for keypress")
                spawn(self._listen_for_notifications, addy)
            if read_on_connect:
                self.logger.debug(
                    "Reading from sensors on reconnect")
                self._read_from_tag(addy)

    def _enable_sensors(self, addy, tag):
        self.logger.info("Enabling sensors: {}".format(addy))
        self._notify_status_signal('Enabling', addy)
        sensors = self._get_sensors(addy, tag)
        for s in sensors:
            s.enable()
            if s.__class__.__name__ == 'KeypressSensor':
                tag.setDelegate(
                    KeypressDelegate(self.logger, self.notify_signals))
        self.logger.info("Sensors enabled: {}".format(addy))

    def _listen_for_notifications(self, addy):
        tag = self._tags[addy]
        reconnect = False
        while True:
            try:
                with self._read_lock:
                    self.logger.debug("Waiting for notification")
                    notification = tag.waitForNotifications(1)
                    self.logger.debug("Notification: {}".format(notification))
            except BTLEException:
                self.logger.exception('Error while waiting for notification')
                reconnect = True
                break
        if reconnect:
            self._reconnect(addy, False)

    def _get_sensors(self, addy, tag=None):
        settings = self._configs[addy]["sensors"]
        tag = tag or self._tags[addy]
        return [getattr(tag, s) for s in AVAIL_SENSORS if settings.get(s)]

    def _read_from_tag(self, addy):
        """ Reads from sensors notify a Signal. """
        # Don't let too many reads queue up when sensor reads are slow
        if self._read_counter > 5:
            self.logger.debug(
                "Skipping read. Too many in progress: {}".format(addy))
            return
        try:
            self._read_counter += 1
            cfg = self._configs[addy]
            sensors = self._get_sensors(addy)
            with self._read_lock:
                self.logger.debug("Reading from {}...".format(cfg["name"]))
                # Don't read from 'keypress'
                data = {
                    SENSOR_MAPPINGS[s.__class__.__name__]:
                        self._read_and_process(s) for s in sensors
                        if s.__class__.__name__ != 'KeypressSensor'
                }
                self.logger.debug(
                    "Finished reading from {}".format(cfg["name"]))
            data['sensor_tag_name'] = cfg["name"]
            data['sensor_tag_address'] = cfg["address"]
            sig = Signal(data)
            self.notify_signals([sig], 'sensors')
        except Exception:
            self.logger.exception(
                "Error reading from {}. Reconnecting...".format(cfg["name"]))
            self._reconnect(addy)
        finally:
            self._read_counter -= 1

    def _reconnect(self, addy, read_on_connect=True):
        spawn(self._reconnect_thread, addy, read_on_connect)

    def _reconnect_thread(self, addy, read_on_connect=True):
        cfg = self._configs[addy]
        if cfg["address"] in self._tags:
            self._notify_status_signal('Disconnected', addy)
            # this next line is temporary.
            try:
                self._tags[cfg["address"]].disconnect()
            except:
                pass
            self._tags.pop(cfg["address"], None)
            # Connect to this tag again and read right away
            self._connect_tag(cfg, read_on_connect)
        else:
            self.logger.exception(
                "Lost connection to {}...consider reschedule".format(
                    cfg["name"]))

    def _read_and_process(self, sensor):
        data = sensor.read()
        attributes = AVAIL_SENSORS[SENSOR_MAPPINGS[sensor.__class__.__name__]]
        return {attr: data[idx] for idx, attr in enumerate(attributes)}

    def _notify_status_signal(self, status, addy):
        data = {'status': status}
        cfg = self._configs[addy]
        data['name'] = cfg["name"]
        data['address'] = cfg["address"]
        self.notify_signals([Signal(data)], output_id='status')
