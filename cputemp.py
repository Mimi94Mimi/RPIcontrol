#!/usr/bin/python3

"""Copyright (c) 2019, Douglas Otwell

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import dbus
import threading
import sys
import lirc
from os import system

from advertisement import Advertisement
from service import Application, Service, Characteristic, Descriptor
from repeated_timer import RepeatedTimer

GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
NOTIFY_TIMEOUT = 50
DELAY_DETECT_MANUAL_SHUTDOWN = 1.0

time_interval = 10.0  # default
app_running = False
app_shutdown = False
is_shooting_multi_photos = False
camera_shooting = False
photos_left = 0
should_take_photo = False


class CameraAdvertisement(Advertisement):
    def __init__(self, index):
        Advertisement.__init__(self, index, "peripheral")
        self.add_local_name("CameraController")
        self.include_tx_power = True

class CameraService(Service):
    CAMERA_SVC_UUID = "187f0000-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, index):
        self.mode = "fixed_time_interval"
        self.num_of_photos = 5
        self.time_interval = 1.0
        self.angle = 3
        self.camera_state = "idle"
        self.should_take_photo = "false"

        Service.__init__(self, index, self.CAMERA_SVC_UUID, True)
        self.add_characteristic(ModeCharacteristic(self))
        self.add_characteristic(NumOfPhotosCharacteristic(self))
        self.add_characteristic(TimeIntervalCharacteristic(self))
        self.add_characteristic(AngleCharacteristic(self))
        self.add_characteristic(CameraStateCharacteristic(self))
        self.add_characteristic(ShouldTakePhotoCharacteristic(self))
    
    def set_mode(self, val):
        self.mode = val

    def set_num_of_photos(self, val):
        self.num_of_photos = val

    def set_time_interval(self, val):
        self.time_interval = val

    def set_angle(self, val):
        self.angle = val

    def get_camera_state(self):
        return self.camera_state
    
    def set_camera_state(self, val):
        self.camera_state = val

    def get_should_take_photo(self):
        return self.should_take_photo

class ModeCharacteristic(Characteristic):
    MODE_CHARACTERISTIC_UUID = "187f0001-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        Characteristic.__init__(
                self, self.MODE_CHARACTERISTIC_UUID,
                ["write"], service)
        # self.add_descriptor(UnitDescriptor(self))

    def WriteValue(self, value, options):
        val = str(value)
        if(val == "fixed_angle"):
            print("Mode has changed to 'fixed_angle'.")
            self.service.set_mode(val)
        elif(val == "fixed_time_interval"):
            print("Mode has changed to 'fixed_time_interval'.")
            self.service.set_mode(val)
        else:
            print("Invalid mode input.")

class NumOfPhotosCharacteristic(Characteristic):
    NUMOFPHOTOS_CHARACTERISTIC_UUID = "187f0002-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        Characteristic.__init__(
                self, self.NUMOFPHOTOS_CHARACTERISTIC_UUID,
                ["write"], service)
        # self.add_descriptor(UnitDescriptor(self))

    def WriteValue(self, value, options):
        try:
            val = int(str(value))
            if(val < 1 or val > 200):
                print("Number of photos should be in range 1-200.")

            self.service.set_num_of_photos(val)

        except ValueError:
            print("Invalid value (cannot convert to <int>).")
        

class TimeIntervalCharacteristic(Characteristic):
    TIMEINTERVAL_CHARACTERISTIC_UUID = "187f0003-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        Characteristic.__init__(
                self, self.TIMEINTERVAL_CHARACTERISTIC_UUID,
                ["write"], service)
        # self.add_descriptor(UnitDescriptor(self))

    def WriteValue(self, value, options):
        try:
            val = float(str(value))
            if(val < 0.2 or val > 20.0):
                print("Time interval should be in range 0.2-20.0 .")

            self.service.set_time_interval(val)

        except ValueError:
            print("Invalid value (cannot convert to <float>).")

class AngleCharacteristic(Characteristic):
    ANGLE_CHARACTERISTIC_UUID = "187f0004-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        Characteristic.__init__(
                self, self.ANGLE_CHARACTERISTIC_UUID,
                ["write"], service)
        # self.add_descriptor(UnitDescriptor(self))

    def WriteValue(self, value, options):
        try:
            val = int(str(value))
            if(val < 1 or val > 45):
                print("The angle should be in range 1-45.")

            self.service.set_angle(val)

        except ValueError:
            print("Invalid value (cannot convert to <int>).")

class CameraStateCharacteristic(Characteristic):
    CAMERA_STATE_CHARACTERISTIC_UUID = "187f0005-44ad-4f56-bee4-23b6cac3fe46"
    def __init__(self, service):
        self.notifying = False

        Characteristic.__init__(
                self, self.CAMERA_STATE_CHARACTERISTIC_UUID,
                ["notify", "read", "write"], service)
        #self.add_descriptor(TakePhotoDescriptor(self))

    def get_camera_state(self):
        value = []
        camera_state = self.service.get_camera_state()
        data = camera_state
        print('get_camera_state is called: ', data, flush=True)

        for c in data:
            value.append(dbus.Byte(c.encode()))

        return value

    def set_camera_state_callback(self):
        if self.notifying:
            value = self.get_camera_state()
            self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])

        return self.notifying

    def StartNotify(self):
        if self.notifying:
            return

        self.notifying = True

        value = self.get_camera_state()
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])
        self.add_timeout(NOTIFY_TIMEOUT, self.set_camera_state_callback())

    def StopNotify(self):
        self.notifying = False

    def ReadValue(self, options):
        value = self.get_camera_state()

        return value
    
    def WriteValue(self, value, options):
        val = str(value)
        if(val == "idle"):
            print("Camera state has changed to 'idle'.")
            self.service.set_camera_state(val)
        elif(val == "shooting"):
            print("Camera state has changed to 'shooting'.")
            self.service.set_camera_state(val)
        else:
            print("Invalid camera state input.")

class ShouldTakePhotoCharacteristic(Characteristic):
    ...
        
class ShouldTakePhotoCharacteristic(Characteristic):
    SHOULDTAKEPHOTO_CHARACTERISTIC_UUID = "187f0006-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        self.notifying = False

        Characteristic.__init__(
                self, self.SHOULDTAKEPHOTO_CHARACTERISTIC_UUID,
                ["notify", "read"], service)
        #self.add_descriptor(TakePhotoDescriptor(self))

    def get_should_take_photo(self):
        value = []
        should_take_photo = self.service.get_should_take_photo()
        data = should_take_photo
        print('get_should_take_photo is called: ', data, flush=True)

        for c in data:
            value.append(dbus.Byte(c.encode()))

        return value

    def set_should_take_photo_callback(self):
        if self.notifying:
            value = self.get_should_take_photo()
            self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])

        return self.notifying

    def StartNotify(self):
        if self.notifying:
            return

        self.notifying = True

        value = self.get_should_take_photo()
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])
        self.add_timeout(NOTIFY_TIMEOUT, self.set_should_take_photo_callback())

    def StopNotify(self):
        self.notifying = False

    def ReadValue(self, options):
        value = self.get_should_take_photo()

        return value

"""class TakePhotoDescriptor(Descriptor):
    TAKE_PHOTO_DESCRIPTOR_UUID = "0001"
    TAKE_PHOTO_VALUE = "should take photo"

    def __init__(self, characteristic):
        Descriptor.__init__(
                self, self.TAKE_PHOTO_DESCRIPTOR_UUID,
                ["read"],
                characteristic)

    def ReadValue(self, options):
        value = []
        desc = self.TAKE_PHOTO_VALUE

        for c in desc:
            value.append(dbus.Byte(c.encode()))

        return value"""

"""class CameraShootingCharacteristic(Characteristic):
    CAMERA_SHOOTING_CHARACTERISTIC_UUID = "187f0002-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        Characteristic.__init__(
                self, self.CAMERA_SHOOTING_CHARACTERISTIC_UUID,
                ["write"], service)
        # self.add_descriptor(UnitDescriptor(self))

    def WriteValue(self, value, options):
        val = str(value)
        self.service.set_camera_shooting(val)
        if(val == "false"):
            print("a picture has taken.")"""

"""class CameraShootingDescriptor(Descriptor):
    CAMERA_SHOOTING_DESCRIPTOR_UUID = "0002"
    CAMERA_SHOOTING_VALUE = "camera shooting"

    def __init__(self, characteristic):
        Descriptor.__init__(
                self, self.CAMERA_SHOOTING_DESCRIPTOR_UUID,
                ["read"],
                characteristic)

    def ReadValue(self, options):
        value = []
        desc = self.CAMERA_SHOOTING_VALUE

        for c in desc:
            value.append(dbus.Byte(c.encode()))

        return value"""
    
# def shutdown():
#     if not timer_update is None and timer_update.isRunning():
#         timer_update.stop()
#     if not timer_system is None and timer_system.isRunning():
#         timer_system.stop()
#     print('Shutdown system.')
#     system("sudo shutdown -h now")
    
# def shot_event():
#     global photos_left
#     if(is_shooting_multi_photos and photos_left > 0):
#         should_take_photo = True
#         camera_shooting = True
#         should_take_photo = False
#         photos_left -= 1
#         if(photos_left == 0):
#             is_shooting_multi_photos = False

# def event_loop():
    
#     global client
#     global lock1
#     global photos_left
#     cmds = ['rot', 'trot', 'shot', 'stpshot']
#     while(1):
#         if(app_shutdown):
#             return

#         print("\
#             COMMANDS:                                                                 /n\
#             rot <degree>            rotate the plate by 1/45/90/180 degrees once      /n\
#             trot                    continue or stop rotating                         /n\
#             shot                    shot a photo once                                 /n\
#             shot <n> <t>            shot n photos every t seconds                     /n\
#             stpshot                 stop shooting photos                              /n\
#         ")

#         input = input("Please enter any commands stated above:")
#         cmd = input.split()[0] 
#         args = input.split()[1:] if len(input.split()) > 1 else []
#         if(cmd not in cmds):
#             print("Invalid command.")
#             continue

#         if(cmd == 'rot'):
#             try:
#                 degree = int(args[0])
#             except ValueError:
#                 print("Invalid degree data type.")
#                 continue
#             else:
#                 if degree not in [1, 45, 90, 180]:
#                     print("Invalid angle (1/45/90/180 only).")
#                     continue
#                 #  rotate
#                 if degree == 1:
#                     # client.send_once("rotplate", "")
#                     ...
#                 elif degree == 45:
#                     # client.send_once("rotplate", "")
#                     ...
#                 elif degree == 90:
#                     # client.send_once("rotplate", "")
#                     ...
#                 elif degree == 180: 
#                     # client.send_once("rotplate", "")
#                     ... 

#         if(cmd == 'trot'):
#             # continue or stop rotate
#             # client.send_once("rotplate", "")
#             ...

#         if(cmd == 'shot'):
#             if(not args):  
#                 # shot once
#                 if(is_shooting_multi_photos):
#                     print('Please stop current shooting task with "stpshot" command.')
#                     continue
#                 should_take_photo = True
#                 should_take_photo = False
#             else:
#                 try:
#                     num_of_photos, time_interval = int(args[0]), float(args[1])
#                 except ValueError:
#                     print("Invalid argument data type.")
#                     continue
#                 else:
#                     if(is_shooting_multi_photos):
#                         print('Please stop current shooting task with "stpshot" command.')
#                         continue
#                     if time_interval < 0.1 or time_interval > 20:
#                         print('Time interval should be in range 0.1 ~ 20')
#                         continue
#                     else:
#                         #  shot n photos
#                         lock1.acquire()
#                         is_shooting_multi_photos = True
#                         timer_update.set_interval(time_interval)
#                         photos_left = num_of_photos
#                         lock1.release()

#         if(cmd == 'stpshot'):
#             if(is_shooting_multi_photos):
#                 is_shooting_multi_photos = False
#                 photos_left = 0

app = Application()
app.add_service(CameraService(0))
app.register()

adv = CameraAdvertisement(0)
adv.register()

# timer_update = RepeatedTimer(time_interval, shot_event)
# timer_system = RepeatedTimer(DELAY_DETECT_MANUAL_SHUTDOWN, shutdown)

# client = lirc.Client()
# lock1 = threading.Lock()
# th = threading.Thread(target = event_loop)

try:
    app_running = True
    app.run()

except KeyboardInterrupt:
    # app_running = False
    # app_shutdown = True
    # th.join()
    app.quit()
