import sys
from unittest.mock import MagicMock
from nio.signal.base import Signal
from nio.testing.block_test_case import NIOBlockTestCase


class TestSensorTagRead(NIOBlockTestCase):

    def setUp(self):
        super().setUp()
        self.mock_tag = MagicMock()
        sys.modules['bluepy'] = MagicMock()
        sys.modules['bluepy.sensortag'] = self.mock_tag
        sys.modules['bluepy.btle'] = MagicMock()
        self.mock_tag.SensorTag.return_value.keypress.__class__.__name__ = 'KeypressSensor'
        self.mock_tag.SensorTag.return_value.IRtemperature.__class__.__name__ = 'IRTemperatureSensor'
        # mock this as an object since we want to actually use the
        # KeypressDelegate object defined in the block code, but not the one
        # in the bluepy code.
        self.mock_tag.KeypressDelegate = object
        # now that everything is mocked, import the objects and let them mock
        # themselves. Make global here to avoid importing the library at the
        # top, which will auto-fail because we can't install this library.
        from ..sensor_tag_read_block import SensorTagRead, KeypressDelegate
        global SensorTagRead, KeypressDelegate

    def test_sensors_signals(self):
        """Each processed signal results in one notified 'sensors' signal"""
        # wait for a notification but never actually handle one
        blk = SensorTagRead()
        addy = '12:34:56:78:12:34'
        self.configure_block(blk, {
            'device_info': [
                {
                    'address': addy,
                    'meta': {
                        'sensors': {'IRtemperature': True}
                    }
                }
            ],
            'log_level': 'DEBUG'
        })
        blk.start()
        # wait for _connect_tag to finish
        from time import sleep; sleep(0.1)
        # process signals and assert here
        blk._read_and_process = MagicMock(side_effect=[42, 314])
        # read from sensors
        blk.process_signals([Signal()])
        from time import sleep; sleep(1)
        self.assertEqual(1, blk._read_and_process.call_count)
        self.assertEqual(1, len(self.last_notified['sensors']))
        self.assertDictEqual({'sensor_tag_address': addy,
                              'sensor_tag_name': 'SensorTag',
                              'IRtemperature': 42},
                             self.last_notified['sensors'][0].to_dict())
        # read from sensors again
        blk.process_signals([Signal()])
        self.assertEqual(2, blk._read_and_process.call_count)
        self.assertEqual(2, len(self.last_notified['sensors']))
        self.assertDictEqual({'sensor_tag_address': addy,
                              'sensor_tag_name': 'SensorTag',
                              'IRtemperature': 314},
                             self.last_notified['sensors'][1].to_dict())
        blk.stop()

    def test_status_signals(self):
        """Connecting to the sensor tag notifies 'status' signals"""
        # wait for a notification but never actually handle one
        blk = SensorTagRead()
        addy = '12:34:56:78:12:34'
        self.configure_block(blk, {
            'device_info': [
                {
                    'address': addy,
                    'meta': {
                        'sensors': {'keypress': True,
                                    'IRtemperature': False}
                    }
                }
            ],
            'log_level': 'DEBUG'
        })
        blk.start()
        # wait for tag to connect and sensors to enable
        from time import sleep; sleep(0.1)
        # Connected status is emitted on successful start.
        self.assertEqual(3, len(self.last_notified['status']))
        self.assertEqual('SensorTag',
                         self.last_notified['status'][0].to_dict()["name"])
        self.assertEqual('Connecting',
                         self.last_notified['status'][0].to_dict()["status"])
        self.assertEqual('Enabling',
                         self.last_notified['status'][1].to_dict()["status"])
        self.assertEqual('Connected',
                         self.last_notified['status'][2].to_dict()["status"])
        self.assertEqual('12:34:56:78:12:34',
                         self.last_notified['status'][0].to_dict()["address"])
        # Connected status is emitted on successful start.
        blk._reconnect_thread(addy, read_on_connect=False)
        from time import sleep; sleep(0.1)
        self.assertEqual(7, len(self.last_notified['status']))
        self.assertEqual('Disconnected',
                         self.last_notified['status'][3].to_dict()["status"])
        self.assertEqual('Connecting',
                         self.last_notified['status'][4].to_dict()["status"])
        self.assertEqual('Enabling',
                         self.last_notified['status'][5].to_dict()["status"])
        self.assertEqual('Connected',
                         self.last_notified['status'][6].to_dict()["status"])
        blk.stop()
        # Should stop emit a disconnect signal? What if we aad a feature in
        # the future where block can stop without stopping the service?
        self.assertEqual(7, len(self.last_notified['status']))
        self.assertEqual(0, len(self.last_notified['sensors']))

    def test_keypress_delegate(self):
        """Button presses notify 'keypress' signals"""
        # wait for a notification but never actually handle one
        blk = SensorTagRead()
        self.configure_block(blk, {
            'device_info': [
                {
                    'address': '12:34:56:78:12:34',
                    'meta': {
                        'sensors': {'keypress': True,
                                    'IRtemperature': False}
                    }
                }
            ],
            'log_level': 'DEBUG'
        })
        blk.start()
        from time import sleep; sleep(0.1)
        delegate = KeypressDelegate(blk.logger, blk.notify_signals)
        delegate.onButtonDown(0x02)
        self.assertEqual(1, len(self.last_notified['keypress']))
        self.assertEqual(
            'Left',
            self.last_notified['keypress'][0].to_dict()["button"]
        )
        self.assertEqual(
            'Down',
            self.last_notified['keypress'][0].to_dict()["direction"]
        )
        delegate.onButtonUp(0x01)
        self.assertEqual(2, len(self.last_notified['keypress']))
        self.assertEqual(
            'Right',
            self.last_notified['keypress'][1].to_dict()["button"]
        )
        self.assertEqual(
            'Up',
            self.last_notified['keypress'][1].to_dict()["direction"]
        )
        delegate.onButtonUp(0x02 | 0x01)
        self.assertEqual(3, len(self.last_notified['keypress']))
        self.assertEqual(
            'Both',
            self.last_notified['keypress'][2].to_dict()["button"]
        )
        self.assertEqual(
            'Up',
            self.last_notified['keypress'][2].to_dict()["direction"]
        )
        # Make sure no signals notified from default sensors output
        self.assertEqual(0, len(self.last_notified['sensors']))
