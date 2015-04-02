from datetime import timedelta
from time import sleep
from .bluepy.bluepy.sensortag import SensorTag
from .bluepy.bluepy.sensortag import KeypressDelegate as _KeypressDelegate
from .bluepy.bluepy.btle import LEScanner, BTLEException
from nio.common.block.base import Block
from nio.common.signal.base import Signal
from nio.common.command import command
from nio.common.discovery import Discoverable, DiscoverableType
from nio.metadata.properties.holder import PropertyHolder
from nio.metadata.properties.object import ObjectProperty
from nio.metadata.properties.list import ListProperty
from nio.metadata.properties.string import StringProperty
from nio.metadata.properties.int import IntProperty
from nio.metadata.properties.bool import BoolProperty
from nio.common.command.params.int import IntParameter
from nio.common.command.params.list import ListParameter
from nio.common.command.params.string import StringParameter
from nio.modules.scheduler import Job
from nio.modules.threading import spawn
from nio.util.attribute_dict import AttributeDict

AVAIL_SENSORS = {
    'IRtemperature': ['ambient_temp_degC', 'target_temp_degC'],
    'accelerometer': ['x_accel_g', 'y_accel_g', 'z_accel_g'],
    'humidity': ['ambient_temp_degC', 'relative_humidity'],
    'magnetometer': ['x_uT', 'y_uT', 'z_uT'],
    'barometer': ['ambient_temp_degC', 'pressure_millibars'],
    'gyroscope': ['x_deg_per_sec', 'y_deg_per_sec', 'z_deg_per_sec'],
    'keypress': ['keys']
}


class Sensors(PropertyHolder):
    IRtemperature = BoolProperty(name="IR Temperature", default=True)
    accelerometer = BoolProperty(name="Accelerometer", default=False)
    humidity = BoolProperty(name="Humidity", default=False)
    magnetometer = BoolProperty(name="Magnetometer", default=False)
    barometer = BoolProperty(name="Barometer", default=False)
    gyroscope = BoolProperty(name="Gyroscope", default=False)
    keypress = BoolProperty(name="Keypress", default=False)


class SensorTagMeta(PropertyHolder):
    name = StringProperty(title='Name (human readable)', default='SensorTag')
    sensors = ObjectProperty(Sensors)


class SensorTagInfo(PropertyHolder):
    address = StringProperty(title='Device Address', default='')
    meta = ObjectProperty(SensorTagMeta)


class KeypressDelegate(_KeypressDelegate):
    """ Handle SensorTag button presses """

    def __init__(self, logger, notify_signals):
        super().__init__()
        self._logger = logger
        self.notify_signals = notify_signals

    def onButtonUp(self, but):
        self._logger.debug( "** " + self._button_desc[but] + " UP")
        self.notify_signals(
            [Signal({'button': self._button_desc[but], 'direction': 'up'})])

    def onButtonDown(self, but):
        self._logger.debug( "** " + self._button_desc[but] + " DOWN")
        self.notify_signals(
            [Signal({'button': self._button_desc[but], 'direction': 'down'})])


@command("scan")
@command("connect")
@command("scan_and_connect")
@command("tag_config",
         StringParameter('address', default=''),
         StringParameter('name', default=''),
         IntParameter('seconds', default=0),
         ListParameter('sensors', default=[]))
@command("list")
@Discoverable(DiscoverableType.block)
class SensorTagRead(Block):

    device_info = ListProperty(SensorTagInfo, title="Sensor Tag Config")
    default_metadata = ObjectProperty(SensorTagMeta)
    scan_length = IntProperty(title="BLE Scan Length", default=5)

    def __init__(self):
        super().__init__()
        self._scanner = LEScanner('SensorTag', 5)
        self._configs = {}
        self._tags = {}

    def configure(self, context):
        super().configure(context)
        for dev_info in self.device_info:
            self._configs[dev_info.address] = self._cfg_from_device_info(dev_info)

    def _cfg_from_device_info(self, device_info):
        return AttributeDict({
            'address': device_info.address,
            'name': device_info.meta.name,
            'sensors': AttributeDict({
                sensor: getattr(device_info.meta.sensors, sensor) \
                for sensor in AVAIL_SENSORS
            })
        })

    def process_signals(self, signals, input_id='default'):
        self._logger.debug('Processing Signals: {}'.format(len(signals)))
        for signal in signals:
            for addy in self._tags:
                self._read_from_tag(addy)

    def start(self):
        super().start()
        self.connect()

    def stop(self):
        super().stop()
        self._scanner.stop()

    def tag_config(self, address, name, seconds, sensors):
        cfg = AttributeDict({
            'address': address,
            'name': name,
            'sensors': self._sensor_list_to_attr_dict(sensors) or \
                       self.default_metadata.sensors
        })

        # if we're already aware of this device, amend the existing
        # configuration
        if address in self._configs:
            cfg = self._configs[address]

        cfg.name = name if name else cfg.name
        cfg.sensors = AttributeDict({
            s: (s in sensors) for s in AVAIL_SENSORS
        }) if sensors else cfg.sensors

        self._configs[address] = cfg

    def _sensor_list_to_attr_dict(self, sensors):
        return {sensor: True for sensor in sensors}

    def scan_and_connect(self):
        spawn(self._scan_connect_help)

    def _scan_connect_help(self):
        self._scan_helper()
        self._connect_tags()

    def scan(self):
        spawn(self._scan_helper)

    def _scan_helper(self):
        timeout = self._scanner.scan()
        devices = [d for d in self._scanner._devices if d not in self._configs]
        self._logger.info(
            "{} new devices discovered in {} seconds".format(len(devices),
                                                         timeout))
        for addr in devices:
            self._configs[addr] = AttributeDict({
                'address': addr,
                'name': "{}-{}".format(self.default_metadata.name, len(self._configs)),
                'sensors': self.default_metadata.sensors
            })

    def connect(self):
        connecting_to = []
        for addr in self._configs:
            if addr not in self._tags:
                connecting_to.append(addr)
                spawn(self._connect_tag, self._configs[addr])
        return connecting_to

    def _connect_tag(self, cfg, read_on_connect=False):
        result = None
        addy = cfg.address
        name = cfg.name
        try:
            self._logger.info("Push {} side button NOW".format(name))
            tag = SensorTag(addy)
            self._enable_sensors(addy, tag)
            # Save the tag to the list after connection and sensors enabled.
            self._tags[addy] = tag
        except Exception as e:
            self._logger.exception(
                "Failed to connect to {} ({}). Retrying...".format(name, addy))
            # Make sure to remove tag if connect fails
            self._tags.pop(addy, None)
            sleep(5)
            self._connect_tag(cfg)
        else:
            self._logger.info("Connected to device {}".format(addy))
            if cfg.sensors.get('keypress', False):
                self._logger.debug(
                    "Enabling notification listening for keypress")
                spawn(self._listen_for_notifications, addy)
            if read_on_connect:
                self._logger.debug(
                    "Reading from sensors on reconnect")
                self._read_from_tag(addy)

    def _enable_sensors(self, addy, tag):
        self._logger.debug("Enabling sensors: {}".format(addy))
        sensors = self._get_sensors(addy, tag)
        for s in sensors:
            s.enable()
            if s.__class__.__name__ == 'KeypressSensor':
                self._tags[addy].setDelegate(
                    KeypressDelegate(self._logger, self.notify_signals))
        self._logger.debug("Sensors enabled: {}".format(addy))

    def _listen_for_notifications(self, addy):
        tag = self._tags[addy]
        reconnect = False
        while True:
            self._logger.debug("Waiting for notification")
            try:
                notification = tag.waitForNotifications(10)
                self._logger.debug("Notification: {}".format(notification))
            except BTLEException:
                self._logger.exception('Error while waiting for notification')
                reconnect = True
                break
        if reconnect:
            self._reconnect(addy, False)


    def list(self):
        return self._configs

    def _get_sensors(self, addy, tag=None):
        settings = self._configs[addy].sensors
        tag = tag or self._tags[addy]
        return [getattr(tag, s) for s in AVAIL_SENSORS \
                if getattr(settings, s)]

    def _read_from_tag(self, addy):
        try:
            cfg = self._configs[addy]
            sensors = self._get_sensors(addy)
            self._logger.debug("Reading from {}...".format(cfg.name))
            data = {s.ident: self._read_and_process(s) for s in sensors}
            data['sensor_tag_name'] = cfg.name
            data['sensor_tag_address'] = cfg.address
            sig = Signal(data)
            self.notify_signals([sig])
        except Exception:
            self._logger.exception(
                "Error reading from {}. Reconnecting...".format(cfg.name))
            self._reconnect(addy)

    def _reconnect(self, addy, read_on_connect=True):
        spawn(self._reconnect_thread, addy, read_on_connect)

    def _reconnect_thread(self, addy, read_on_connect=True):
        cfg = self._configs[addy]
        if cfg.address in self._tags:
            # this next line is temporary.
            try:
                self._tags[cfg.address].disconnect()
            except:
                pass
            self._tags.pop(cfg.address, None)
            # Connect to this tag again and read right away
            self._connect_tag(cfg, read_on_connect)
        else:
            self._logger.exception(
                "Lost connection to {}...consider reschedule".format(
                    cfg.name))

    def _read_and_process(self, sensor):
        data = sensor.read()
        attributes = AVAIL_SENSORS[sensor.ident]
        return {attr: data[idx] for idx, attr in enumerate(attributes)}
