#!/usr/bin/python3

import argparse
import datetime
import json
import logging
import logging.handlers
import signal
import time

import comwatt
import csscolors
import dateutil
import hue_color_converter
import pythonhuecontrol.v1.bridge
import suntime


class Monitor(object):

    def __init__(self, comwatt_email=None, comwatt_password=None, hue_bridge=None, hue_key=None, hue_light=None):

        self.comwatt_email = comwatt_email
        self.comwatt_password = comwatt_password

        self.hue_bridge = hue_bridge
        self.hue_key = hue_key
        self.hue_light = hue_light

        self.do_run = False

        self.logger = logging.getLogger("Monitor")

        self.previous_state = -1000000000
        self.same_state_count = 0

        self.threshold_sun = -1000000000
        self.thresholds = []

        self.latitude = 0
        self.longitude = 0

        self.sun_tool = None
        self.day = None
        self.sunrise = None
        self.sunset = None

    def initialize(self):

        self.bridge = pythonhuecontrol.v1.bridge.Bridge(self.hue_bridge, "http://" + self.hue_bridge + "/api/" + self.hue_key)

        # self.comwatt = comwatt.PowerGEN4(args.debug)
        # self.comwatt.login(self.comwatt_email, self.comwatt_password)

        self.comwatt = comwatt.PowerGEN4(self.comwatt_email, self.comwatt_password, args.debug)

        self.light_monitor = None

        for light_id in self.bridge.light_ids:
            light = self.bridge.light(light_id)

            if light.name == self.hue_light:
                self.light_monitor = light
                break

        assert self.light_monitor is not None

        self.do_run = True

        self.logger.debug("Initialized")

    def load(self, config):

        self.comwatt_email = config["comwatt"]["email"]
        self.comwatt_password = config["comwatt"]["password"]

        self.hue_bridge = config["hue"]["bridge"]
        self.hue_key = config["hue"]["key"]
        self.hue_light = config["hue"]["light"]

        self.threshold_sun = config["thresholds"]["sun"]["min"]

        list_thresholds = [ v for v in config["thresholds"]["delta"] ]

        conv = hue_color_converter.Converter("C")

        for key in list_thresholds:
            value = config["thresholds"]["delta"][key]

            xyy = conv.hex_to_xyy(csscolors.__getattribute__(value.upper()).lstrip("#"))
            color = [xyy[0][0], xyy[0][1]]

            self.thresholds.append((int(key), color))

        self.sun_tool = suntime.Sun(config["location"]["latitude"], config["location"]["longitude"])


    def stop(self, signum, frame):
        self.logger.info("Stop")
        self.do_run = False


    def check_state(self, state):
         
        self.logger.debug("Check state: New=%d, Previous=%d" % (state, self.previous_state))

        if state == self.previous_state:
            self.same_state_count += 1
            if self.same_state_count >= 10:
                self.logger.info("Refreshing Commwatt")
                self.comwatt.refresh()
                self.same_state_count = 0
        else:
            self.previous_state = state
            self.same_state_count = 0

    def run(self, count=0, delay=5):

        self.logger.info("Run")

        signal.signal(signal.SIGTERM, self.stop)

        count = 0

        while self.do_run:
            
            self.logger.info(" Loop ".center(10, "="))

            loop = 0
            while self.do_run and loop < delay:
                time.sleep(1)
                loop += 1

            today = datetime.datetime.now()

            if not self.day or self.day != today.strftime("%d"):

                self.day = today.strftime("%d")
                self.sunrise = self.sun_tool.get_sunrise_time(today, dateutil.tz.gettz()).time()
                self.sunset = self.sun_tool.get_sunset_time(today, dateutil.tz.gettz()).time()

                self.logger.info("Day %s" % self.day)
                self.logger.info("Sunrise %s" % self.sunrise)
                self.logger.info("Sunset %s" % self.sunset)

            time_now = datetime.datetime.today().time()
            self.logger.info("Now %s" % time_now)

            if time_now < self.sunrise or time_now > self.sunset:
                self.logger.warn("Sun is not raised")
                continue

            try:
                #self.comwatt.devices()

                list_injection = self.comwatt.get_devices("injection")
                device_injection = list_injection[0]
                list_withdrawal = self.comwatt.get_devices("withdrawal")
                device_withdrawal = list_withdrawal[0] 
                list_sun = self.comwatt.get_devices("sun")
                device_sun = list_sun[0] 
            except:
                # Sometimes connection to Comwatt is lost so we need to reset connection
                self.initialize()
                continue

            if not device_sun.initialized:
                self.logger.warning("Sun: Not initialized (count=%d)" % self.same_state_count)
                self.check_state(-1000000000)
                time.sleep(args.delay)
                continue

            self.logger.info("Sun: %d" % device_sun.value_instant)

            if device_sun.value_instant < self.threshold_sun : 
                # Sun is not sufficient -> Off
                self.light_monitor.switch_off()

            else:

                delta = device_injection.value_instant - device_withdrawal.value_instant

                self.logger.info("Injection: %s" % device_injection.value_instant)
                self.logger.info("Withdrawal: %s" % device_withdrawal.value_instant)
                self.logger.info("Delta: %s" % delta)

                self.check_state(delta)

                if device_sun.value_instant < self.threshold_sun:
                    self.set("off")

                else:
                     
                    color = None
                    i = 0
                    while i < len(self.thresholds):
                        if delta > self.thresholds[i][0]:
                            color = self.thresholds[i][1]
                        else:
                            break
                        i += 1

                    self.light_monitor.switch_on()
                    self.light_monitor.state.set(xy=color)  

            if args.count :

                count += 1

                if count >= args.count:
                    break

    def __del__(self):
         
        self.comwatt.quit()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--delay", type=int, default=5)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--log")
    args = parser.parse_args()
    
    log_level = logging.INFO

    if args.log:
        log_handler = logging.handlers.RotatingFileHandler(filename=args.log, mode="a", maxBytes=1024 * 1024, backupCount=5)
        logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=log_level, handlers=[log_handler])
    else:
        logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=log_level)


    fd = open(args.config)
    config = json.load(fd)
    fd.close()

    m = Monitor()
    m.load(config)
    m.initialize()
    m.run()
