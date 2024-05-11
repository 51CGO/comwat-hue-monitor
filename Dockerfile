FROM python:3.11-bookworm

RUN apt update && apt install -y firefox-esr
RUN python3 -m venv /comwatt_hue_monitor
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.34.0/geckodriver-v0.34.0-linux64.tar.gz -O /tmp/geckodriver.tar.gz && \
    tar xzf /tmp/geckodriver.tar.gz -C /comwatt_hue_monitor/bin

RUN /comwatt_hue_monitor/bin/python3 -m pip install --upgrade pip
RUN /comwatt_hue_monitor/bin/python3 -m pip install requests rgbxy csscolors hue-color-converter pythonhuecontrol python-dateutil suntime

VOLUME /mnt
WORKDIR /mnt

RUN /comwatt_hue_monitor/bin/python3 -m pip install comwatt==0.8.0
COPY monitor.py /comwatt_hue_monitor/bin/
RUN chmod +x /comwatt_hue_monitor/bin/monitor.py

ENV LOG_LEVEL="ERROR"

CMD /comwatt_hue_monitor/bin/python3 /comwatt_hue_monitor/bin/monitor.py --log-level $LOG_LEVEL /mnt/monitor.json
