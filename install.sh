#!/bin/bash

cp -r usr/pytts/watchdog.py /usr

crontab -l | egrep -v 'watchdog|^$' > /tmp/mycron
echo '@reboot  /usr/pytts/watchdog.py' >> /tmp/mycron
echo '' >> /tmp/mycron
crontab /tmp/mycron
rm /tmp/mycron
crontab -l