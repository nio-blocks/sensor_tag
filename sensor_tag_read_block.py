from datetime import timedelta
from .bluepy.bluepy.sensortag import SensorTag
from .bluepy.bluepy.btle import LEScanner
from nio.common.block.base import Block
from nio.common.signal.base import Signal
from nio.common.command import command
from nio.common.discovery import Discoverable, DiscoverableType
from nio.metadata.properties.holder import PropertyHolder
from nio.metadata.properties.object import ObjectProperty
from nio.metadata.properties.list import ListProperty
from nio.metadata.properties.string import StringProperty
from nio.metadata.properties.timedelta import TimeDeltaProperty
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
    'gyroscope': ['x_deg_per_sec', 'y_deg_per_sec', 'z_deg_per_sec']
}


class Sensors(PropertyHolder):
    IRtemperature = BoolProperty(name="IR Temperature", default=True)
    accelerometer = BoolProperty(name="Accelerometer", default=False)
    humidity = BoolProperty(name="Humidity", default=False)
    magnetometer = BoolProperty(name="Magnetometer", default=False)
    barometer = BoolProperty(name="Barometer", default=False)
    gyroscope = BoolProperty(name="Gyroscope", default=False)
    # keys = BoolProperty(name="Keypress", default=False)


class SensorTagInfo(PropertyHolder):
    address = StringProperty(title='Device Address', default='')
    name = StringProperty(title='Name (human readable)', default='')
    read_interval = TimeDeltaProperty(title="Device Read Interval")
    sensors = ObjectProperty(Sensors)

@command("discover",
         StringParameter('address', default=''),
         StringParameter('name', default=''),
         IntParameter('seconds', default=1),
         ListParameter('sensors', default=['IRtemperature']))
@command("connect")
@command("reschedule")
@command("scan")
@Discoverable(DiscoverableType.block)
class SensorTagRead(Block):

    device_info = ListProperty(SensorTagInfo, title="Sensor Tag Config")
    
    def __init__(self):
        super().__init__()
        self._scanner = LEScanner('SensorTag')
        self._tags = {}
        self._sensors = {}
        self._read_jobs = []

    def configure(self, context):
        super().configure(context)
        
    def start(self):
        super().start()
        self._schedule_read_jobs()

    def stop(self):
        super().stop()
        self._cancel_existing_jobs()

    def discover(self, address, name, seconds, sensors):
        if address:
            spawn(self._discover_new, address, name, seconds, sensors)
        else:
            spawn(self._scan_and_disco, name, seconds, sensors)

    def connect(self):
        spawn(self._connect_configured)
        
    def reschedule(self):
        self._schedule_read_jobs()

    def _scan_and_disco(self, base_name, seconds, sensors):
        existing = [t._addr for t in self._tags]
        self._scanner.scan()
        devices = [d for d in self._scanner._devices if d not in existing]
        for idx, addr in enumerate(devices):
            self._discover_new(addr,
                               "{}-{}".format(base_name, idx),
                               seconds,
                               sensors)

    def _discover_new(self, address, name, seconds, sensors):
        cfg = AttributeDict({
            'address': address,
            'name': name,
            'read_interval': timedelta(seconds=seconds),
            'sensors': AttributeDict({
                s: (s in sensors) for s in AVAIL_SENSORS
            })
        })
        self._connect_tag(cfg)
        cfg, tag = self._tags.get(address, (None, None))
        if tag is not None:
            sensors = self._get_sensors(cfg, tag)
            [s.enable() for s in sensors]
            self._sensors[address] = sensors
            job = Job(self._read_from_tag, cfg.read_interval,
                      True, cfg, self._sensors[address])
            self._read_jobs.append(job)

    def _connect_configured(self):
        for cfg in self.device_info:
            self._connect_tag(cfg)

        self._logger.info(
            "Successfully connected to {} SensorTags".format(
                len(self._tags.keys()))
        )

        for addy in self._tags:
            cfg, tag = self._tags[addy]
            sensors = self._get_sensors(cfg, tag)
            [s.enable() for s in sensors]
            self._sensors[addy] = sensors

        self._schedule_read_jobs()

    def _connect_tag(self, cfg):
        result = None
        addy = cfg.address
        name = cfg.name
        try:
            self._logger.info("Push {} side button NOW".format(name))
            self._tags[addy] = (cfg, SensorTag(addy))
        except Exception as e:
            self._logger.error(
                "Failed to connect to {} ({}): {}: {}".format(
                    name, addy, type(e).__name__, str(e))
            )
        else:
            self._logger.info("Connected to device {}".format(addy))

    def _schedule_read_jobs(self):
        self._cancel_existing_jobs()
        self._logger.debug("Scheduling {} read jobs now...".format(len(self._tags)))
        for addy in self._tags:
            cfg, _ = self._tags[addy]
            job = Job(self._read_from_tag, cfg.read_interval,
                      True, cfg, self._sensors[addy])
            self._read_jobs.append(job)

    def _cancel_existing_jobs(self):
        [job.cancel() for job in self._read_jobs]

    def _get_sensors(self, cfg, tag):
        settings = cfg.sensors
        return [getattr(tag, s) for s in AVAIL_SENSORS \
                if getattr(settings, s)]

    def _read_from_tag(self, cfg, sensors):
        try:
            self._logger.debug("Reading from {}...".format(cfg.name))
            data = {s.ident: self._read_and_process(s) for s in sensors}
            data['sensor_tag_name'] = cfg.name
            data['sensor_tag_address'] = cfg.address
            sig = Signal(data)
            self.notify_signals([sig])
        except Exception as e:
            if cfg.address in self._tags:
                del self._tags[cfg.address]
                self._logger.error(
                    "Error reading from {}: {}: {}".format(
                        cfg.name, type(e).__name__, str(e))
                    )
            else:
                self._logger.error(
                    "Lost connection to {}...consider reschedule".format(
                        cfg.name))

    def _read_and_process(self, sensor):
        data = sensor.read()
        attributes = AVAIL_SENSORS[sensor.ident]
        return {attr: data[idx] for idx, attr in enumerate(attributes)}
