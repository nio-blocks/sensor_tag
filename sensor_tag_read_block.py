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
from nio.metadata.properties.int import IntProperty
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


class SensorTagMeta(PropertyHolder):
    name = StringProperty(title='Name (human readable)', default='SensorTag')
    read_interval = TimeDeltaProperty(
        title="Device Read Interval", default=timedelta(seconds=10))
    sensors = ObjectProperty(Sensors)


class SensorTagInfo(PropertyHolder):
    address = StringProperty(title='Device Address', default='')
    meta = ObjectProperty(SensorTagMeta)


@command("scan")
@command("connect")
@command("scan_and_connect")
@command("tag_config",
         StringParameter('address', default=''),
         StringParameter('name', default=''),
         IntParameter('seconds', default=0),
         ListParameter('sensors', default=[]))
@command("reschedule")
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
        self._sensors = {}
        self._read_jobs = []
        
    def configure(self, context):
        super().configure(context)
        self._configs = self.persistence.load('configs') or self._configs
        for dev_info in self.device_info:
            self._configs[cfg.address] = self._cfg_from_device_info(dev_info)

    def _cfg_from_device_info(self, device_info):
        return AttributeDict({
            'address': device_info.address,
            'name': device_info.meta.name,
            'read_interval': device_info.meta.read_interval,
            'sensors': [sensor for sensor in AVAIL_SENSORS \
                        if getattr(device_info.meta.sensors, sensor)]
        })

    def stop(self):
        super().stop()
        self._scanner.stop()
        self.persistence.store('configs', self._configs)
        self.persistence.save()
        self._cancel_existing_jobs()

    def tag_config(self, address, name, seconds, sensors):
        cfg = AttributeDict({
            'address': address,
            'name': name,
            'read_interval': timedelta(seconds=seconds) if seconds else \
                self.default_metadata.read_interval,
            'sensors': sensors or self.default_metadata.sensors
        })
 
        # if we're already aware of this device, amend the existing
        # configuration
        if address in self._configs:
            cfg = self._configs[address]

        cfg.name = name if name else cfg.name
        cfg.read_interval = timedelta(seconds) if seconds > 0 \
                            else cfg.read_interval
        cfg.sensors = AttributeDict({
            s: (s in sensors) for s in AVAIL_SENSORS
        }) if sensors else cfg.sensors

        self._configs[address] = cfg

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
                'read_interval': self.default_metadata.read_interval,
                'sensors': self.default_metadata.sensors
            })

    def connect(self):
        spawn(self._connect_tags)
        
    def _connect_tags(self):
        for addr in self._configs:
            if addr not in self._tags:
                self._connect_tag(self._configs[addr])
            if addr not in self._sensors:
                sensors = self._get_sensors(*self._tags[addr])
                [s.enable() for s in sensors]
                self._sensors[addr] = sensors
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
            
    def reschedule(self):
        self._schedule_read_jobs()

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

    def list(self):
        return self._configs

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
