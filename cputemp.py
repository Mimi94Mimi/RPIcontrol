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
import time
import lirc
from os import system

from advertisement import Advertisement
from service import Application, Service, Characteristic, Descriptor
from repeated_timer import RepeatedTimer
from lirc import LircdConnection

GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
NOTIFY_TIMEOUT = 50
DELAY_DETECT_MANUAL_SHUTDOWN = 1.0
CONNECT_COUNTER_INTERVAL = 0.1

MODE = "fixed_angle"
NUM_OF_PHOTOS = 5
TIME_INTERVAL = 1.5
ANGLE = 3
CAMERA_STATE = "idle"
SHOULD_TAKE_PHOTO = "false"
CONNECTED = 0
COUNT_DOWN_TIME = 3
POSTPONE_TH_CD = 0.3
START_ROTATING_CD = 2.0
STOP_ROTATING_CD = 2.0
ROT1DEG_CD = 1.0
WAITING_HANDLER_CD = 0.3

# time_interval = 10.0  # default
# app_running = False
# app_shutdown = False
# is_shooting_multi_photos = False
# camera_shooting = False
# photos_left = 0
# should_take_photo = False


class CameraAdvertisement(Advertisement):
    def __init__(self, index):
        Advertisement.__init__(self, index, "peripheral")
        self.add_local_name("CameraController")
        self.include_tx_power = True
        self.add_service_uuid("187f0000-44ad-4f56-bee4-23b6cac3fe46")

class CameraService(Service):
    CAMERA_SVC_UUID = "187f0000-44ad-4f56-bee4-23b6cac3fe46"

    def reset_characteristics(self):
        self.mode = MODE
        self.num_of_photos = NUM_OF_PHOTOS
        self.time_interval = TIME_INTERVAL
        self.angle = ANGLE
        self.camera_state = CAMERA_STATE
        self.should_take_photo = SHOULD_TAKE_PHOTO
        self.connected = CONNECTED
        self.lastConnected = CONNECTED

    def __init__(self, index):
        self.reset_characteristics()
        self.waitingHandler_th = threading.Timer(WAITING_HANDLER_CD, self.waitingHandler)
        self.waitingHandler_th.start()
        self.connectState = "waiting"

        Service.__init__(self, index, self.CAMERA_SVC_UUID, True)
        self.add_characteristic(ModeCharacteristic(self))
        self.add_characteristic(NumOfPhotosCharacteristic(self))
        self.add_characteristic(TimeIntervalCharacteristic(self))
        self.add_characteristic(AngleCharacteristic(self))
        self.add_characteristic(CameraStateCharacteristic(self))
        self.add_characteristic(ShouldTakePhotoCharacteristic(self))
        self.add_characteristic(ConnectedCharacteristic(self))
    
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
        if val == "shooting":
            self.start_shooting()
        if val == "idle":
            ...

    def get_should_take_photo(self):
        return self.should_take_photo
    
    def set_should_take_photo(self, val):
        self.should_take_photo = val

    def get_connected(self):
        return self.connected

    def set_connected(self, val):
        self.connected = val
        if (val == "connected"):
            print("central has connected.")
            print("reset characteristics to default value.")
            self.reset_characteristics()
        if (val == "waiting"):
            print("waiting to reconnect.")
        if (val == "disconnected"):
            print("central has disconnected.")


    def count_down(self, cd_time):
        if self.camera_state == "idle":
            return
        if self.connectState == "waiting":
            self.cd_th = threading.Timer(POSTPONE_TH_CD, self.count_down, [cd_time])
            self.cd_th.start()
            return
        if cd_time > 0:
            print(cd_time)
            self.cd_th = threading.Timer(1, self.count_down, [cd_time-1])
            self.cd_th.start()
        if cd_time <= 0:
            if self.mode == "fixed_angle":
                self.shooting_th = threading.Thread(target=self.shooting_fixed_angle, args=(0, 0))
                self.shooting_th.start()
            elif self.mode == "fixed_time_interval":
                self.shooting_th = threading.Thread(target=self.shooting_fixed_time_interval, args=(0, "start"))
                self.shooting_th.start()

    def start_shooting(self):
        self.cd_th = threading.Thread(target=self.count_down, args=(COUNT_DOWN_TIME,))
        self.cd_th.start()

    def shooting_fixed_angle(self, photo_cnt, angle_cnt):
        if self.camera_state == "idle":
            return 
        if self.connectState == "waiting":
            self.shooting_th = threading.Timer(POSTPONE_TH_CD, self.shooting_fixed_angle, [photo_cnt, angle_cnt])
            self.shooting_th.start()
            return
        if photo_cnt >= self.num_of_photos:
            self.camera_state = "idle"
            print("camera state to idle")
            return
        if angle_cnt >= self.angle:
            print("a photo has been shot.")
            self.should_take_photo = "true"
            self.shooting_th = threading.Timer(ROT1DEG_CD, self.shooting_fixed_angle, [photo_cnt+1, 0])
            self.shooting_th.start()
        else:
            print("rotate the plate by 1 degree.")
            system('irsend SEND_ONCE light KEY_1')
            self.shooting_th = threading.Timer(ROT1DEG_CD, self.shooting_fixed_angle, [photo_cnt, angle_cnt+1])
            self.shooting_th.start()

    def shooting_fixed_time_interval(self, photo_cnt, state):
        if self.camera_state == "idle":
            return 
        if self.connectState == "waiting":
            self.shooting_th = threading.Timer(POSTPONE_TH_CD, self.shooting_fixed_time_interval, [photo_cnt, state])
            self.shooting_th.start()
            return
        if state == "start":
            print("start rotating...")
            system('irsend SEND_ONCE light KEY_RESTART')
            self.shooting_th = threading.Timer(START_ROTATING_CD, self.shooting_fixed_time_interval, [photo_cnt, "normal"])
            self.shooting_th.start()
            return
        if state == "end":
            self.camera_state = "idle"
            print("camera state to idle")
            return
        if photo_cnt >= self.num_of_photos:
            print("stop rotating...")
            system('irsend SEND_ONCE light KEY_STOP')
            self.shooting_th = threading.Timer(STOP_ROTATING_CD, self.shooting_fixed_time_interval, [photo_cnt, "end"])
            self.shooting_th.start()
            return
        if photo_cnt == 0:
            self.fixed_time_start = time.time()
        print("a photo has been shot.")
        self.should_take_photo = "true"
        print(f"{time.time() - self.fixed_time_start:.3f}s after starting shooting_time_interval.")
        self.shooting_th = threading.Timer(self.time_interval, self.shooting_fixed_time_interval, [photo_cnt+1, "normal"])
        self.shooting_th.start()

    def waitingHandler(self):
        counter_diff = WAITING_HANDLER_CD * 10 - 1
        if (self.connectState == "connected" and self.connected - self.lastConnected < counter_diff):
            #print("wait begin")
            print("waiting to reconnect...")
            self.connectState = "waiting"
        if (self.connectState == "waiting" and self.connected - self.lastConnected >= counter_diff):
            #print("wait end")
            self.connectState = "connected"
        self.lastConnected = self.connected
        self.waitingHandler_th = threading.Timer(WAITING_HANDLER_CD, self.waitingHandler)
        self.waitingHandler_th.start()

    def cancel_threads(self):
        try:
            if self.cd_th is not None:
                self.cd_th.cancel()
        except AttributeError:
            pass
        try:
            if self.shooting_th is not None:
                self.shooting_th.cancel()
        except AttributeError:
            pass
        try:
            if self.waitingHandler_th is not None:
                self.waitingHandler_th.cancel()
        except AttributeError:
            pass

class ModeCharacteristic(Characteristic):
    MODE_CHARACTERISTIC_UUID = "187f0001-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        Characteristic.__init__(
                self, self.MODE_CHARACTERISTIC_UUID,
                ["write"], service)
        # self.add_descriptor(UnitDescriptor(self))

    def WriteValue(self, value, options):
        val = ''.join([str(v) for v in value])
        print(f"'{val}' has been written")
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
            val = int(''.join([str(v) for v in value]))
            print(f"'{val}' has been written")
            if(val < 1 or val > 200):
                print("Number of photos should be in range 1-200.")
            else:
                print(f"num_of_photos has been set to {val}")

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
            val = float(''.join([str(v) for v in value]))
            print(f"'{val}' has been written")
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
            val = int(''.join([str(v) for v in value]))
            print(f"'{val}' has been written")
            if(val < 1 or val > 45):
                print("The angle should be in range 1-45.")
            else:
                print(f"angle has been set to {val}")

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
        self.add_timeout(NOTIFY_TIMEOUT, self.set_camera_state_callback)

    def StopNotify(self):
        self.notifying = False

    def ReadValue(self, options):
        value = self.get_camera_state()

        return value
    
    def WriteValue(self, value, options):
        val = ''.join([str(v) for v in value])
        # print(f"'{val}' has been written")
        if(val == "idle"):
            print("Camera state has changed to 'idle'.")
            self.service.set_camera_state(val)
        elif(val == "shooting"):
            print("Camera state has changed to 'shooting'.")
            self.service.set_camera_state(val)
        else:
            print("Invalid camera state input.")
        
class ShouldTakePhotoCharacteristic(Characteristic):
    SHOULDTAKEPHOTO_CHARACTERISTIC_UUID = "187f0006-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        self.notifying = False

        Characteristic.__init__(
                self, self.SHOULDTAKEPHOTO_CHARACTERISTIC_UUID,
                ["notify", "read", "write"], service)
        #self.add_descriptor(TakePhotoDescriptor(self))

    def get_should_take_photo(self):
        value = []
        should_take_photo = self.service.get_should_take_photo()
        data = should_take_photo

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
        self.add_timeout(NOTIFY_TIMEOUT, self.set_should_take_photo_callback)

    def StopNotify(self):
        self.notifying = False

    def ReadValue(self, options):
        value = self.get_should_take_photo()

        return value
    
    def WriteValue(self, value, options):
        val = ''.join([str(v) for v in value])
        # print(f"'{val}' has been written")
        if(val == "false"):
            # print("should_take_photo has changed to 'false'.")
            self.service.set_should_take_photo("false")
        elif(val == "true"):
            # print("should_take_photo has changed to 'true'.")
            self.service.set_should_take_photo("true")
        else:
            print("Invalid camera state input.")

class ConnectedCharacteristic(Characteristic):
    CONNECTED_CHARACTERISTIC_UUID = "187f0007-44ad-4f56-bee4-23b6cac3fe46"

    def __init__(self, service):
        Characteristic.__init__(
                self, self.CONNECTED_CHARACTERISTIC_UUID,
                ["read", "write"], service)
        # self.add_descriptor(UnitDescriptor(self))

    def get_connected(self):
        value = []
        connected = self.service.get_connected()
        data = connected

        for c in data:
            value.append(dbus.Byte(c.encode()))

        return value

    def ReadValue(self, options):
        value = self.get_connected()

        return value

    def WriteValue(self, value, options):
        try:
            val = int(''.join([str(v) for v in value]))
            #print(f"{val} has been written")

            self.service.set_connected(val)

        except:
            print("Invalid value.")

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
    app.services[0].cancel_threads()
    app.quit()
